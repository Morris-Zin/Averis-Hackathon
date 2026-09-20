"""Framework-independent email intake and persistence boundary."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from sqlalchemy import select

from averis.domain import AttachmentView, AuditEntry, CaseView
from averis.persistence import Case, Database, Document, Workspace, uid, utcnow
from averis.storage import Storage
from averis.workflow import create_processing_run, view_of


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
