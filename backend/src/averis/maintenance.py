"""Workspace lifecycle and scheduled maintenance, separate from run execution."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from averis.persistence import (
    BrowserSession,
    Case,
    Database,
    Document,
    Outbox,
    Run,
    Workspace,
    utcnow,
)
from averis.storage import Storage

if TYPE_CHECKING:
    from averis.processing import Processor
log = logging.getLogger(__name__)


def expire_workspaces(db: Database, storage: Storage) -> int:
    """Remove disposable data after session expiry; keep the spend ledger."""
    count = 0
    with db.session() as session, session.begin():
        expired = session.scalars(
            select(Workspace)
            .where(Workspace.expires_at < utcnow())
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for workspace in expired:
            cases = select(Case.id).where(Case.workspace_id == workspace.id)
            runs = select(Run.id).where(Run.case_id.in_(cases))
            # Keep object rows until deletion succeeds, so a failed delete is retried.
            for document in session.scalars(
                select(Document).where(Document.workspace_id == workspace.id)
            ):
                storage.delete(document.object_key)
            session.execute(delete(Outbox).where(Outbox.run_id.in_(runs)))
            session.execute(delete(Run).where(Run.case_id.in_(cases)))
            session.execute(
                delete(Document).where(Document.workspace_id == workspace.id)
            )
            session.execute(delete(Case).where(Case.workspace_id == workspace.id))
            session.execute(
                delete(BrowserSession).where(
                    BrowserSession.workspace_id == workspace.id
                )
            )
            session.delete(workspace)
            count += 1
    return count


def maintain(processor: "Processor") -> int:
    """Expire disposable workspaces, then recover runs even if cleanup fails."""
    try:
        expire_workspaces(processor.db, processor.storage)
    except Exception as exc:  # noqa: BLE001 - cleanup must not block run recovery
        log.warning("workspace_expiry_failed error_type=%s", type(exc).__name__)
    return processor.reconcile()
