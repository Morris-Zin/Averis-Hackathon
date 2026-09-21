"""Private document reading implementation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePath

from averis.documents.evidence import with_metadata
from averis.documents.images import read_image
from averis.documents.limits import (
    IMAGE_SUFFIXES,
    MAX_DOCUMENT_BYTES,
    check_office_archive,
)
from averis.documents.pdf import read_pdf
from averis.documents.spreadsheet import read_xlsx
from averis.documents.text import read_text
from averis.documents.word import read_docx
from averis.domain import DocumentEvidence


def read_document(document_id: str, filename: str, content: bytes) -> DocumentEvidence:
    """Read one supported attachment into verbatim, source-linked evidence.

    Failure and truncation are part of the result contract.  This function
    never interprets an unreadable or unsupported document as complete.
    For hostile/untrusted inputs, application code should normally call
    :func:`read_document_bounded`, which adds a process time boundary.
    """

    result = DocumentEvidence(document_id=document_id)

    if not content:
        result.issues.append("empty_document")
        return with_metadata(document_id, content, result)
    if len(content) > MAX_DOCUMENT_BYTES:
        result.issues.append(
            f"document_size_limit_exceeded:{len(content)}>{MAX_DOCUMENT_BYTES}"
        )
        return with_metadata(document_id, content, result)

    suffix = PurePath(filename).suffix.lower()
    adapter = FORMAT_READERS.get(suffix)
    if adapter is None:
        result.issues.append(f"unsupported_document_type:{suffix or 'none'}")
        return with_metadata(document_id, content, result)

    try:
        if adapter.office_archive:
            archive_issue = check_office_archive(content)
            if archive_issue:
                result.issues.append(archive_issue)
                return with_metadata(document_id, content, result)
        return with_metadata(
            document_id, content, adapter.read(document_id, content, suffix)
        )
    except Exception as exc:  # noqa: BLE001 - failures are result data at this boundary.
        result.issues.append(f"document_unreadable:{type(exc).__name__}")
        return with_metadata(document_id, content, result)


@dataclass(frozen=True)
class FormatReader:
    """A trusted built-in format adapter behind the bounded document boundary."""

    read: Callable[[str, bytes, str], DocumentEvidence]
    preview: bool = False
    ocr: bool = False
    office_archive: bool = False


FORMAT_READERS = {
    ".txt": FormatReader(lambda doc, content, suffix: read_text(doc, content)),
    ".pdf": FormatReader(
        lambda doc, content, suffix: read_pdf(doc, content), True, True
    ),
    ".docx": FormatReader(
        lambda doc, content, suffix: read_docx(doc, content), office_archive=True
    ),
    ".xlsx": FormatReader(
        lambda doc, content, suffix: read_xlsx(doc, content), office_archive=True
    ),
    **{suffix: FormatReader(read_image, True, True) for suffix in IMAGE_SUFFIXES},
}

SUPPORTED_FORMATS: dict[str, dict[str, object]] = {
    suffix: {"preview": reader.preview, "ocr": reader.ocr}
    for suffix, reader in FORMAT_READERS.items()
}
