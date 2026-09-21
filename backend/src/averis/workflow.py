"""Authoritative case actions. Persistence and HTTP cannot bypass these rules."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from averis.domain import Action, AttachmentView, AuditEntry, CaseView
from averis.persistence import (
    Case,
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


def resolve_purpose(session: Session, case: Case, requested: str | None = None) -> str:
    """Resolve the processing purpose without acquiring a Run row lock.

    Reviewer transactions hold the Case lock; worker transactions use Run ->
    Case ordering, so reviewers must never lock a Run row while holding Case.
    """

    if requested is not None:
        purpose = requested
    elif case.active_run_id:
        previous = session.get(Run, case.active_run_id)
        purpose = previous.purpose if previous is not None else "demo"
    else:
        purpose = "demo"
    if purpose not in {"demo", "development"}:
        raise ValueError("Unknown processing purpose")
    return purpose


def create_processing_run(
    session: Session, case: Case, input_revision: int, purpose: str
) -> str:
    """Create a Run and Outbox entry; the caller serializes the final view once.

    This owns Run/Outbox persistence and the active-run pointer. It never
    mutates the serialized case JSON; the workflow adapter updates the view and
    persists ``row.state`` exactly once.
    """

    if purpose not in {"demo", "development"}:
        raise ValueError("Unknown processing purpose")
    run = Run(id=uid(), case_id=case.id, input_revision=input_revision, purpose=purpose)
    session.add(run)
    session.add(Outbox(run_id=run.id))
    case.active_run_id = run.id
    return run.id


def enqueue(session: Session, case: Case, purpose: str | None = None) -> str:
    """Legacy entry point kept for intake compatibility; prefers explicit ops.

    New workflow code uses :func:`resolve_purpose` + :func:`create_processing_run`
    and serializes the view once. This wrapper preserves the old import path
    without the previous JSON-mutating protocol.
    """

    resolved = resolve_purpose(session, case, purpose)
    return create_processing_run(session, case, case.input_revision, resolved)


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
    ) -> tuple[CaseView, str | None]:
        # One ordered transaction: validate revision, apply the domain decision,
        # append history, create any run/outbox entry, synchronize run metadata,
        # and serialize the final state once.
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
            controlled = any(
                entry.actor == "Demo setup" and entry.action == "created"
                for entry in view.history
            )
            run_id: str | None = None
            correction = None
            if action.kind == "revision":
                view = self._controlled_revision(session, row, view, action, controlled)
                history_detail = action.reason.strip()
                processing_intent = "none"
            else:
                decision = review_case(view, action, controlled=controlled)
                if decision.processing_intent == "queue" and not live_enabled:
                    raise ValueError(
                        "Live processing is disabled until the AI budget is verified"
                    )
                view = decision.view
                history_detail = decision.history_detail
                correction = decision.correction
                processing_intent = decision.processing_intent
                if decision.accepted_pair is not None:
                    row.accepted_pair = decision.accepted_pair
                if decision.reading_override is not None:
                    key, reading = decision.reading_override
                    row.overrides = {
                        **row.overrides,
                        key: reading.model_dump(mode="json"),
                    }
            view.revision += 1
            view.history.append(
                AuditEntry(
                    at=utcnow().isoformat(),
                    actor=actor,
                    action=action.kind,
                    detail=history_detail,
                    correction=correction,
                )
            )
            if processing_intent == "queue":
                purpose = resolve_purpose(session, row, None)
                run_id = create_processing_run(
                    session, row, view.input_revision, purpose
                )
                view.processing_run_id = run_id
                view.processing_attempts, view.processing_error = 0, None
            row.revision, row.input_revision = view.revision, view.input_revision
            row.state = view.model_dump(mode="json")
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
                run_id = create_processing_run(
                    session, row, view.input_revision, "development"
                )
                view.processing_run_id = run_id
                view.processing_attempts, view.processing_error = 0, None
                row.revision, row.input_revision, row.state = (
                    view.revision,
                    view.input_revision,
                    view.model_dump(mode="json"),
                )
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
        # Controlled revisions advance the processing input exactly once.
        view.input_revision = original.input_revision + 1
        controlled_revision(session, row, view, self.storage)
        row.accepted_pair = None
        replay_saved_comparison(view)
        # Ensure the replayed report (if any) matches the new input revision.
        if view.report is not None:
            view.report.input_revision = view.input_revision
        return view
