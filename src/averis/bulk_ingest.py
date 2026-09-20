"""Bulk email ingestion without persistence, transport or worker decisions.

The caller receives validated per-email records with their own attachments.
This module owns ZIP safety bounds, organizer-style email JSON validation and
attachment-reference resolution. It never touches the database, object
storage, the worker, budgets or evaluation ground truth.

Supported input (see docs/bulk-import.md):
- An organizer-style ZIP: ``inbox/*.json`` email records plus the attachment
  files they reference (for example ``attachments/email_001_SI.txt``).
- Loose email JSON files in the same shape, optionally accompanied by loose
  attachment files matched by exact filename.
"""

import io
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Parser resource bounds, not usage quotas: the full 520-email organizer set
# fits whenever it stays within the 21 MB transport and 32 MB decompressed
# byte bounds. See docs/bulk-import.md.
MAX_ARCHIVE_ENTRIES = 2000
MAX_ARCHIVE_DECOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 21 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_EMAIL_JSON_BYTES = 2 * 1024 * 1024
MAX_EMAILS_PER_REQUEST = 600
MAX_LOOSE_ATTACHMENTS_PER_REQUEST = 1200
MAX_ATTACHMENT_REFS_PER_EMAIL = 20
MAX_ATTACHMENTS_PER_EMAIL = 8
MAX_ATTACHMENT_BYTES_PER_EMAIL = 20 * 1024 * 1024

ALLOWED_SUFFIXES = frozenset(
    {".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"}
)

_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:)?[\\/]")
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


class _OrganizerEmail(BaseModel):
    """One organizer-style email JSON record; unknown keys are tolerated.

    Only transport fields (identity, subject, sender, body, attachment
    references) are read. Evaluation labels or answer keys are never fields
    here, so ground truth cannot become inference input through this module.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    email_id: str = Field(min_length=1, max_length=256)
    sender: str = Field(default="", max_length=320, alias="from")
    subject: str = Field(min_length=1, max_length=1000)
    body: str = Field(default="", max_length=100_000)
    attachments: list[str] = Field(
        default_factory=list, max_length=MAX_ATTACHMENT_REFS_PER_EMAIL
    )


@dataclass(frozen=True)
class EmailRecord:
    """One importable email with only its own attachments resolved."""

    ref: str
    subject: str
    sender: str
    body: str
    attachments: tuple[tuple[str, bytes], ...]
    missing_attachments: tuple[str, ...]


@dataclass(frozen=True)
class EmailFailure:
    """One email JSON that cannot be imported, with an actionable reason."""

    ref: str
    error: str


@dataclass(frozen=True)
class BulkPlan:
    """Parsed bulk input; failures never block the valid records."""

    records: tuple[EmailRecord, ...]
    failures: tuple[EmailFailure, ...]


def _safe_member_name(raw: str) -> str | None:
    """Normalize one archive member name, rejecting unsafe entries.

    Drive-relative names (``C:foo``) are rejected explicitly: PurePosixPath
    does not treat them as absolute, and members are only ever read into
    memory, never extracted.
    """
    if not raw or _ABSOLUTE.match(raw) or _DRIVE_PREFIX.match(raw):
        return None
    normalized = str(PurePosixPath(raw.replace("\\", "/")))
    if normalized in {".", "/"}:
        return None
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return normalized


def _read_archive_members(data: bytes) -> dict[str, bytes]:
    """Read ZIP members into memory with decompression bounds enforced."""
    if not data or len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive must contain 1 byte to 21 MB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Archive is not a readable ZIP file") from exc
    with archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        if not entries:
            raise ValueError("Archive contains no files")
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValueError(
                f"Archive has more than {MAX_ARCHIVE_ENTRIES} files; "
                "split it into smaller archives"
            )
        members: dict[str, bytes] = {}
        total = 0
        for info in entries:
            name = _safe_member_name(info.filename)
            if name is None:
                raise ValueError(
                    f"Archive member is unsafe: {info.filename!r}; "
                    "absolute paths, drive prefixes and '..' segments "
                    "are rejected"
                )
            if _is_symlink(info):
                raise ValueError(
                    f"Archive member is a symlink: {name!r}; "
                    "include the file contents instead"
                )
            if name in members:
                raise ValueError(f"Archive contains a duplicate member: {name!r}")
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError(
                    f"Archive member exceeds 10 MB: {name!r}; "
                    "attach it through single-email intake instead"
                )
            total += info.file_size
            if total > MAX_ARCHIVE_DECOMPRESSED_BYTES:
                raise ValueError(
                    "Archive decompresses to more than 32 MB; "
                    "split it into smaller archives"
                )
            try:
                members[name] = archive.read(info)
            except (RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
                raise ValueError(
                    f"Archive member cannot be read: {name!r}; "
                    "unsupported compression or encryption"
                ) from exc
    return members


def _resolve_reference(
    reference: str, members: dict[str, bytes]
) -> tuple[str, bytes] | None | str:
    """Resolve one attachment reference to its own bytes.

    Returns the ``(filename, content)`` pair, ``None`` when the reference is
    honestly missing, or an error string when it is unsafe or ambiguous.
    Cross-email guessing is never performed: only an exact relative path or a
    globally unique basename resolves.
    """
    if not reference or _ABSOLUTE.match(reference):
        return f"Attachment reference is unsafe: {reference!r}"
    normalized = str(PurePosixPath(reference.replace("\\", "/")))
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        return f"Attachment reference is unsafe: {reference!r}"
    if normalized in members:
        return (PurePosixPath(normalized).name, members[normalized])
    wanted = PurePosixPath(normalized).name
    candidates = sorted(name for name in members if PurePosixPath(name).name == wanted)
    if len(candidates) == 1:
        return (wanted, members[candidates[0]])
    if len(candidates) > 1:
        return (
            f"Attachment reference {reference!r} matches several archive "
            "files; reference its exact archive path instead"
        )
    return None


def _build_record(
    ref: str, email: _OrganizerEmail, members: dict[str, bytes]
) -> EmailRecord | EmailFailure:
    # Attachments are sorted by filename so the import digest is stable:
    # re-uploading the same files in a different member order reuses the
    # existing case instead of creating a duplicate. Identical repeats of
    # one file (for example exact-path plus basename references) collapse.
    resolved_pairs: set[tuple[str, bytes]] = set()
    missing: list[str] = []
    for reference in email.attachments:
        resolved = _resolve_reference(reference, members)
        if isinstance(resolved, str):
            return EmailFailure(ref=ref, error=resolved)
        if resolved is None:
            if reference not in missing:
                missing.append(reference)
            continue
        filename, content = resolved
        if PurePosixPath(filename).suffix.lower() not in ALLOWED_SUFFIXES:
            return EmailFailure(
                ref=ref, error=f"Unsupported attachment type: {filename!r}"
            )
        if not content or len(content) > MAX_FILE_BYTES:
            return EmailFailure(
                ref=ref, error=f"Attachment must contain 1 byte to 10 MB: {filename!r}"
            )
        resolved_pairs.add((filename, content))
    attachments = sorted(resolved_pairs)
    if len(attachments) > MAX_ATTACHMENTS_PER_EMAIL:
        return EmailFailure(
            ref=ref,
            error="At most eight attachments per email; "
            "attach the remainder through single-email intake",
        )
    if sum(len(content) for _, content in attachments) > MAX_ATTACHMENT_BYTES_PER_EMAIL:
        return EmailFailure(
            ref=ref,
            error="Attachments must total 20 MB or less per email",
        )
    return EmailRecord(
        ref=ref,
        subject=email.subject,
        sender=email.sender,
        body=email.body,
        attachments=tuple(attachments),
        missing_attachments=tuple(missing),
    )


def _parse_email_json(ref: str, data: bytes) -> _OrganizerEmail | EmailFailure:
    if not data or len(data) > MAX_EMAIL_JSON_BYTES:
        return EmailFailure(ref=ref, error="Email JSON must contain 1 byte to 2 MB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return EmailFailure(ref=ref, error="Email JSON must be UTF-8 encoded")
    try:
        return _OrganizerEmail.model_validate_json(text)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, error['loc'])) or 'email'}: {error['msg']}"
            for error in exc.errors()[:2]
        )
        return EmailFailure(ref=ref, error=f"Email JSON is invalid: {details}")


def parse_archive(data: bytes) -> BulkPlan:
    """Parse an organizer-style ZIP into importable records and failures."""
    members = _read_archive_members(data)
    candidates = sorted(name for name in members if name.lower().endswith(".json"))
    if not candidates:
        raise ValueError("Archive contains no email JSON files")
    if len(candidates) > MAX_EMAILS_PER_REQUEST:
        raise ValueError(
            f"Archive has more than {MAX_EMAILS_PER_REQUEST} emails; "
            "split it into smaller archives"
        )
    records: list[EmailRecord] = []
    failures: list[EmailFailure] = []
    for name in candidates:
        parsed = _parse_email_json(name, members[name])
        if isinstance(parsed, EmailFailure):
            failures.append(parsed)
            continue
        built = _build_record(parsed.email_id, parsed, members)
        if isinstance(built, EmailFailure):
            failures.append(built)
        else:
            records.append(built)
    return BulkPlan(records=tuple(records), failures=tuple(failures))


def parse_email_files(
    files: list[tuple[str, bytes]],
    attachments: list[tuple[str, bytes]] | None = None,
) -> BulkPlan:
    """Parse loose email JSON files with an optional loose attachment pool."""
    if not files:
        raise ValueError("Upload at least one email JSON file")
    if len(files) > MAX_EMAILS_PER_REQUEST:
        raise ValueError(f"At most {MAX_EMAILS_PER_REQUEST} email files per request")
    if len(attachments or []) > MAX_LOOSE_ATTACHMENTS_PER_REQUEST:
        raise ValueError(
            f"At most {MAX_LOOSE_ATTACHMENTS_PER_REQUEST} loose attachments per request"
        )
    pool: dict[str, bytes] = {}
    for filename, content in attachments or []:
        if not content or len(content) > MAX_FILE_BYTES:
            raise ValueError(f"Attachment must contain 1 byte to 10 MB: {filename!r}")
        key = PurePosixPath(filename.replace("\\", "/")).name
        if key in pool:
            raise ValueError(f"Duplicate attachment filename: {key!r}")
        pool[key] = content
    records: list[EmailRecord] = []
    failures: list[EmailFailure] = []
    for filename, content in files:
        parsed = _parse_email_json(filename, content)
        if isinstance(parsed, EmailFailure):
            failures.append(parsed)
            continue
        built = _build_record(parsed.email_id, parsed, pool)
        if isinstance(built, EmailFailure):
            failures.append(built)
        else:
            records.append(built)
    return BulkPlan(records=tuple(records), failures=tuple(failures))
