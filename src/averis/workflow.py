"""Authoritative case actions. Persistence and HTTP cannot bypass these rules."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from averis.domain import Action, AttachmentView, AuditEntry, CaseView
from averis.persistence import (
    Case,
    Counter,
    Database,
    Document,
    Outbox,
    Run,
    uid,
    utcnow,
)
from averis.review import require_comparison_category, review_case
from averis.storage import Storage


class Conflict(ValueError):
    pass


def take_quota(session: Session, key: str, limit: int) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    session.execute(
        insert(Counter)
        .values(key=key, value=0)
        .on_conflict_do_nothing(index_elements=["key"])
    )
    result = session.scalar(
        update(Counter)
        .where(Counter.key == key, Counter.value < limit)
        .values(value=Counter.value + 1)
        .returning(Counter.value)
    )
    if result is None:
        raise ValueError("Demo limit reached. Saved results remain available.")


def enqueue(session: Session, case: Case, purpose: str | None = None) -> str:
    if purpose is None and case.active_run_id:
        previous = session.get(Run, case.active_run_id)
        if previous is not None:
            purpose = previous.purpose
    purpose = purpose or "demo"
    if purpose not in {"demo", "development"}:
        raise ValueError("Unknown processing purpose")
    run = Run(
        id=uid(), case_id=case.id, input_revision=case.input_revision, purpose=purpose
    )
    session.add(run)
    session.add(Outbox(run_id=run.id))
    case.active_run_id = run.id
    case.state = {
        **case.state,
        "processing_run_id": run.id,
        "processing_attempts": 0,
        "processing_error": None,
    }
    return run.id


def view_of(case: Case) -> CaseView:
    return CaseView.model_validate(case.state)


class Workflow:
    def __init__(self, db: Database, storage: Storage):
        self.db, self.storage = db, storage

    def apply(
        self,
        workspace: str,
        case_id: str,
        actor: str,
        action: Action,
        live_enabled: bool,
        session_key: str,
    ) -> tuple[CaseView, str | None]:
        with self.db.session() as session, session.begin():
            row = session.scalar(
                select(Case)
                .where(Case.id == case_id, Case.workspace_id == workspace)
                .with_for_update()
            )
            if row is None:
                raise KeyError("Case not found")
            if row.revision != action.expected_revision:
                raise Conflict(
                    "This case changed. Refresh before applying your action."
                )
            view = view_of(row)
            take_quota(session, f"actions:{workspace}", 1000)
            run_id = None
            needs_processing = False
            controlled = any(
                entry.actor == "Demo setup" and entry.action == "created"
                for entry in view.history
            )
            if action.kind == "revision":
                view = self._controlled_revision(session, row, view, action, controlled)
                input_changed = True
                history_detail = action.reason.strip()
            else:
                decision = review_case(view, action, controlled=controlled)
                needs_processing = decision.needs_processing
                if needs_processing:
                    self._require_run(session, session_key, live_enabled)
                view = decision.view
                input_changed = decision.input_changed
                history_detail = decision.history_detail
                if decision.accepted_pair is not None:
                    row.accepted_pair = decision.accepted_pair
                if decision.reading_override is not None:
                    key, reading = decision.reading_override
                    row.overrides = {
                        **row.overrides,
                        key: reading.model_dump(mode="json"),
                    }
            if input_changed:
                view.input_revision += 1
                if view.report:
                    view.report.input_revision = view.input_revision
            view.revision += 1
            view.history.append(
                AuditEntry(
                    at=utcnow().isoformat(),
                    actor=actor,
                    action=action.kind,
                    detail=history_detail,
                )
            )
            row.revision, row.input_revision = view.revision, view.input_revision
            row.state = view.model_dump(mode="json")
            if needs_processing:
                run_id = enqueue(session, row)
                view.processing_run_id = run_id
                view.processing_attempts, view.processing_error = 0, None
            return view, run_id

    def attach_revision(
        self,
        workspace: str,
        case_id: str,
        actor: str,
        expected_revision: int,
        document_id: str,
        filename: str,
        content: bytes,
        reason: str,
    ) -> tuple[CaseView, str]:
        if not reason.strip():
            raise ValueError("Explain why this revised document is attached")
        stored = None
        try:
            with self.db.session() as session, session.begin():
                row = session.scalar(
                    select(Case)
                    .where(Case.id == case_id, Case.workspace_id == workspace)
                    .with_for_update()
                )
                if row is None:
                    raise KeyError("Case not found")
                if row.revision != expected_revision:
                    raise Conflict(
                        "This case changed. Refresh before attaching a revision."
                    )
                view = view_of(row)
                require_comparison_category(view)
                previous = next(
                    (a for a in view.attachments if a.id == document_id), None
                )
                if previous is None or previous.superseded:
                    raise ValueError("Original document does not belong to this case")
                if len(view.attachments) >= 24:
                    raise ValueError("Document version limit reached")
                doc_id = uid()
                stored, digest = self.storage.put(content)
                session.add(
                    Document(
                        id=doc_id,
                        case_id=row.id,
                        workspace_id=workspace,
                        filename=filename,
                        object_key=stored,
                        sha256=digest,
                        size=len(content),
                    )
                )
                role, previous.role = previous.role, "unknown"
                previous.superseded = True
                view.attachments.append(
                    AttachmentView(id=doc_id, filename=filename, role=role)
                )
                # Re-prove pairing and extract this new source independently.
                row.accepted_pair = None
                view.report = None
                view.revision += 1
                view.input_revision += 1
                view.processing, view.stage, view.workflow = (
                    "queued",
                    "revision_attached",
                    "open",
                )
                view.history.append(
                    AuditEntry(
                        at=utcnow().isoformat(),
                        actor=actor,
                        action="revision",
                        detail=f"{previous.id} replaced by {doc_id}: {reason.strip()}",
                    )
                )
                row.revision, row.input_revision, row.state = (
                    view.revision,
                    view.input_revision,
                    view.model_dump(mode="json"),
                )
                run_id = enqueue(session, row, "development")
                view.processing_run_id = run_id
                view.processing_attempts, view.processing_error = 0, None
                return view, run_id
        except Exception:
            if stored:
                self.storage.delete(stored)
            raise

    def _controlled_revision(
        self,
        session: Session,
        row: Case,
        original: CaseView,
        action: Action,
        controlled: bool,
    ) -> CaseView:
        require_comparison_category(original)
        if not controlled:
            raise ValueError("Use the operator revision upload for imported documents")
        if not action.reason.strip():
            raise ValueError("Explain why this revised draft is attached")
        if len(original.attachments) >= 24:
            raise ValueError("Document version limit reached")
        from averis.demo import controlled_revision
        from averis.review import replay_saved_comparison

        view = original.model_copy(deep=True)
        controlled_revision(session, row, view, self.storage)
        row.accepted_pair = None
        replay_saved_comparison(view)
        return view

    @staticmethod
    def _require_run(session: Session, session_key: str, enabled: bool) -> None:
        if not enabled:
            raise ValueError(
                "Live processing is disabled until the AI budget is verified"
            )
        take_quota(session, f"live:session:{session_key}", 3)
        take_quota(session, f"live:day:{utcnow().date()}", 50)
