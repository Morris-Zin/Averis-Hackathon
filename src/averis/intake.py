"""Framework-independent email intake and persistence boundary."""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from sqlalchemy import select

from averis.domain import AttachmentView, AuditEntry, CaseView
from averis.persistence import Case, Database, Document, Workspace, uid, utcnow
from averis.storage import Storage
from averis.workflow import create_processing_run, view_of

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportResult:
    """The saved case and optional run to dispatch after commit."""

    view: CaseView
    run_id: str | None


def _import_digest(
    subject: str, sender: str, body: str, attachments: Sequence[tuple[str, bytes]]
) -> str:
    digest = sha256(
        json.dumps(
            {"subject": subject, "sender": sender, "body": body},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    for filename, content in attachments:
        digest.update(filename.encode())
        digest.update(sha256(content).digest())
    return digest.hexdigest()


def import_email(
    db: Database,
    storage: Storage,
    workspace_id: str,
    actor: str,
    subject: str,
    sender: str,
    body: str,
    attachments: Sequence[tuple[str, bytes]],
    *,
    purpose: Literal["demo", "development"] = "development",
) -> ImportResult:
    """Persist one authorized import with deduplication and a durable run.

    The caller owns transport limits and authorization. This module owns the
    workspace lock, content digest, object writes, metadata transaction, outbox
    creation, and cleanup if persistence fails.
    """
    case_id = uid()
    received_at = utcnow().isoformat()
    view = CaseView(
        id=case_id,
        subject=subject,
        sender=sender,
        body=body,
        received_at=received_at,
        revision=1,
        input_revision=1,
        processing="queued",
        stage="imported",
        workflow="open",
        assignee=actor,
        review_reasons=[],
        attachments=[],
        history=[
            AuditEntry(
                at=received_at,
                actor=actor,
                action="imported",
                detail="Original attachments stored",
            )
        ],
    )
    stored: list[str] = []
    try:
        with db.session() as session, session.begin():
            workspace = session.scalar(
                select(Workspace).where(Workspace.id == workspace_id).with_for_update()
            )
            if workspace is None:
                raise KeyError("Workspace not found")
            import_digest = _import_digest(subject, sender, body, attachments)
            existing = session.scalar(
                select(Case).where(
                    Case.workspace_id == workspace_id,
                    Case.import_digest == import_digest,
                )
            )
            if existing:
                return ImportResult(view=view_of(existing), run_id=None)
            for filename, content in attachments:
                document_id = uid()
                object_key, content_digest = storage.put(content)
                stored.append(object_key)
                session.add(
                    Document(
                        id=document_id,
                        workspace_id=workspace_id,
                        case_id=case_id,
                        filename=filename,
                        object_key=object_key,
                        sha256=content_digest,
                        size=len(content),
                    )
                )
                view.attachments.append(
                    AttachmentView(id=document_id, filename=filename)
                )
            row = Case(
                id=case_id,
                workspace_id=workspace_id,
                revision=1,
                input_revision=1,
                import_digest=import_digest,
                state=view.model_dump(mode="json"),
            )
            session.add(row)
            # Meaningful persistence op: create the run, then serialize once.
            run_id = create_processing_run(session, row, view.input_revision, purpose)
            view.processing_run_id = run_id
            row.revision, row.input_revision = view.revision, view.input_revision
            row.state = view.model_dump(mode="json")
    except Exception:
        for object_key in stored:
            storage.delete(object_key)
        raise
    return ImportResult(view=view, run_id=run_id)


@dataclass(frozen=True)
class BulkEmailRequest:
    """One parsed email within a batch; attachments are that email's own."""

    ref: str
    subject: str
    sender: str
    body: str
    attachments: tuple[tuple[str, bytes], ...]
    missing_attachments: tuple[str, ...] = ()


@dataclass(frozen=True)
class BulkItemOutcome:
    """Per-email batch result; missing refs stay visible on every outcome."""

    ref: str
    status: Literal["accepted", "duplicate", "failed"]
    case_id: str | None = None
    subject: str = ""
    attachment_count: int = 0
    missing_attachments: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class BulkOutcome:
    """Partial-success batch result plus accepted runs to dispatch."""

    items: tuple[BulkItemOutcome, ...]
    run_ids: tuple[str, ...]


def import_many(
    db: Database,
    storage: Storage,
    workspace_id: str,
    actor: str,
    requests: Sequence[BulkEmailRequest],
    *,
    purpose: Literal["demo", "development"] = "demo",
) -> BulkOutcome:
    """Persist a parsed batch through single-email intake, reusing its rules.

    This owns batch orchestration: per-email persistence, deduplication and
    partial-success semantics. Validated input failures keep their actionable
    message; unexpected database/storage failures return a stable public
    message while only the error category is logged server-side.
    """
    items: list[BulkItemOutcome] = []
    run_ids: list[str] = []
    for request in requests:
        try:
            result = import_email(
                db,
                storage,
                workspace_id,
                actor,
                request.subject,
                request.sender,
                request.body,
                list(request.attachments),
                purpose=purpose,
            )
        except (ValueError, KeyError) as exc:
            items.append(
                BulkItemOutcome(
                    ref=request.ref,
                    status="failed",
                    subject=request.subject,
                    missing_attachments=request.missing_attachments,
                    error=str(exc) or "The email could not be imported",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - one bad email never blocks the batch
            log.warning(
                "bulk_item_failed",
                extra={"ref": request.ref, "error_type": type(exc).__name__},
            )
            items.append(
                BulkItemOutcome(
                    ref=request.ref,
                    status="failed",
                    subject=request.subject,
                    missing_attachments=request.missing_attachments,
                    error="The email could not be imported. Try again.",
                )
            )
            continue
        if result.run_id is None:
            items.append(
                BulkItemOutcome(
                    ref=request.ref,
                    status="duplicate",
                    case_id=result.view.id,
                    subject=result.view.subject,
                    attachment_count=len(result.view.attachments),
                    missing_attachments=request.missing_attachments,
                )
            )
        else:
            run_ids.append(result.run_id)
            items.append(
                BulkItemOutcome(
                    ref=request.ref,
                    status="accepted",
                    case_id=result.view.id,
                    subject=result.view.subject,
                    attachment_count=len(result.view.attachments),
                    missing_attachments=request.missing_attachments,
                )
            )
    return BulkOutcome(items=tuple(items), run_ids=tuple(run_ids))
