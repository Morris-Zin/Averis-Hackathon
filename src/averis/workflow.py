"""Authoritative case actions. Persistence and HTTP cannot bypass these rules."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from averis.contracts import FIELDS
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
from averis.storage import Storage
from averis.verification import compare, reading_from_evidence, validate_pair


class Conflict(ValueError):
    pass


def take_quota(session: Session, key: str, limit: int) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    session.execute(insert(Counter).values(key=key, value=0).on_conflict_do_nothing(index_elements=["key"]))
    result = session.scalar(update(Counter).where(Counter.key == key, Counter.value < limit).values(value=Counter.value + 1).returning(Counter.value))
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
    run = Run(id=uid(), case_id=case.id, input_revision=case.input_revision, purpose=purpose)
    session.add(run)
    session.add(Outbox(run_id=run.id))
    case.active_run_id = run.id
    case.state = {**case.state, "processing_run_id": run.id, "processing_attempts": 0, "processing_error": None}
    return run.id


def view_of(case: Case) -> CaseView:
    return CaseView.model_validate(case.state)


class Workflow:
    def __init__(self, db: Database, storage: Storage):
        self.db, self.storage = db, storage

    def apply(self, workspace: str, case_id: str, actor: str, action: Action,
              live_enabled: bool, session_key: str) -> tuple[CaseView, str | None]:
        with self.db.session() as session, session.begin():
            row = session.scalar(select(Case).where(Case.id == case_id, Case.workspace_id == workspace).with_for_update())
            if row is None:
                raise KeyError("Case not found")
            if row.revision != action.expected_revision:
                raise Conflict("This case changed. Refresh before applying your action.")
            view = view_of(row)
            take_quota(session, f"actions:{workspace}", 1000)
            run_id = None
            history_detail = action.reason.strip() or f"Updated {action.kind}"
            controlled = any(entry.actor == "Demo setup" and entry.action == "created" for entry in view.history)
            input_changed = action.kind in {"category", "pair", "correct", "revision"}
            if action.kind == "assign":
                if action.assignee not in {"John Tan", "Aisha Rahman", "Mei Lin", "Unassigned"}:
                    raise ValueError("Unknown reviewer")
                view.assignee = action.assignee
            elif action.kind == "workflow":
                if action.workflow is None:
                    raise ValueError("Select a workflow state")
                view.workflow = action.workflow
            elif action.kind == "category":
                if action.category is None or view.classification is None:
                    raise ValueError("Choose a category after classification is available")
                previous_category = view.classification.accepted
                view.classification.accepted = action.category
                view.classification.source = "human"
                history_detail = f"Category changed from {previous_category or 'unaccepted'} to {action.category}"
                if action.reason.strip():
                    history_detail += f": {action.reason.strip()}"
                view.review_reasons = []
                view.report = None
                if action.category == "BL_COMPARISON":
                    if controlled:
                        self._saved_comparison(view)
                    else:
                        self._require_run(session, session_key, live_enabled)
                        view.processing, view.stage = "queued", "classification_accepted"
                else:
                    view.processing, view.stage = "completed", "category_changed"
            elif action.kind == "pair":
                self._require_comparison_category(view)
                si = next((a for a in view.attachments if a.id == action.si_id), None)
                bl = next((a for a in view.attachments if a.id == action.bl_id), None)
                if not si or not bl or si.superseded or bl.superseded or not si.evidence or not bl.evidence or not action.reason.strip():
                    raise ValueError("Choose two read documents and explain the pairing")
                if not validate_pair(si.evidence, bl.evidence, human_selected=True):
                    raise ValueError("Document shipment identifiers conflict")
                for attachment in view.attachments:
                    attachment.role = "SI" if attachment.id == si.id else "BL" if attachment.id == bl.id else "unknown"
                row.accepted_pair = [si.id, bl.id]
                view.report = None
                if controlled:
                    self._saved_comparison(view)
                else:
                    self._require_run(session, session_key, live_enabled)
                    view.processing, view.stage = "queued", "pair_accepted"
            elif action.kind == "correct":
                self._require_comparison_category(view)
                if not view.report or not view.report.pair_valid or not action.field or not action.reason.strip():
                    raise ValueError("A valid comparison, field and correction reason are required")
                attachment = next((a for a in view.attachments if a.id == action.document_id), None)
                if attachment is None or attachment.superseded or attachment.evidence is None:
                    raise ValueError("Evidence does not belong to this case")
                if action.transcription is not None and not action.verified:
                    raise ValueError("Verify the transcription against the original image before saving")
                replacement = reading_from_evidence(action.field, attachment.evidence, action.evidence_ids,
                    transcription=action.transcription, verified=action.verified)
                if not replacement.evidence_ids:
                    raise ValueError("Select evidence from this document")
                if action.transcription is None:
                    replacement.provenance = "human_verified"
                row.overrides = {**row.overrides, f"{attachment.id}:{action.field}": replacement.model_dump(mode="json")}
                si = {f.field: f.si for f in view.report.findings}
                bl = {f.field: f.bl for f in view.report.findings}
                target = si if attachment.role == "SI" else bl if attachment.role == "BL" else None
                if target is None:
                    raise ValueError("Document is not in the accepted pair")
                target[action.field] = replacement
                view.report = compare(si, bl, view.input_revision + 1, True, view.report.issues)
                view.review_reasons = sorted(set(view.report.issues) | {f.si.issue or f.bl.issue or "Unresolved field"
                    for f in view.report.findings if f.outcome == "unresolved"})
            elif action.kind == "revision":
                self._require_comparison_category(view)
                if not controlled:
                    raise ValueError("Use the operator revision upload for imported documents")
                if not action.reason.strip():
                    raise ValueError("Explain why this revised draft is attached")
                if len(view.attachments) >= 24:
                    raise ValueError("Document version limit reached")
                from averis.demo import controlled_revision
                controlled_revision(session, row, view, self.storage)
                row.accepted_pair = None
                self._saved_comparison(view)
            elif action.kind == "retry":
                self._require_run(session, session_key, live_enabled)
                view.processing, view.stage = "queued", "retry_requested"
            if input_changed:
                view.input_revision += 1
                if view.report:
                    view.report.input_revision = view.input_revision
            view.revision += 1
            view.history.append(AuditEntry(at=utcnow().isoformat(), actor=actor, action=action.kind,
                detail=history_detail))
            row.revision, row.input_revision = view.revision, view.input_revision
            row.state = view.model_dump(mode="json")
            if view.processing == "queued" and action.kind in {"category", "pair", "retry"}:
                run_id = enqueue(session, row)
                view.processing_run_id = run_id
                view.processing_attempts, view.processing_error = 0, None
            return view, run_id

    def attach_revision(self, workspace: str, case_id: str, actor: str, expected_revision: int,
                        document_id: str, filename: str, content: bytes, reason: str) -> tuple[CaseView, str]:
        if not reason.strip():
            raise ValueError("Explain why this revised document is attached")
        stored = None
        try:
            with self.db.session() as session, session.begin():
                row = session.scalar(select(Case).where(Case.id == case_id, Case.workspace_id == workspace).with_for_update())
                if row is None:
                    raise KeyError("Case not found")
                if row.revision != expected_revision:
                    raise Conflict("This case changed. Refresh before attaching a revision.")
                view = view_of(row)
                self._require_comparison_category(view)
                previous = next((a for a in view.attachments if a.id == document_id), None)
                if previous is None or previous.superseded:
                    raise ValueError("Original document does not belong to this case")
                if len(view.attachments) >= 24:
                    raise ValueError("Document version limit reached")
                doc_id = uid()
                stored, digest = self.storage.put(content)
                session.add(Document(id=doc_id, case_id=row.id, workspace_id=workspace,
                    filename=filename, object_key=stored, sha256=digest, size=len(content)))
                role, previous.role = previous.role, "unknown"
                previous.superseded = True
                view.attachments.append(AttachmentView(id=doc_id, filename=filename, role=role))
                # Re-prove pairing and extract this new source independently.
                row.accepted_pair = None
                view.report = None
                view.revision += 1
                view.input_revision += 1
                view.processing, view.stage, view.workflow = "queued", "revision_attached", "open"
                view.history.append(AuditEntry(at=utcnow().isoformat(), actor=actor, action="revision",
                    detail=f"{previous.id} replaced by {doc_id}: {reason.strip()}"))
                row.revision, row.input_revision, row.state = view.revision, view.input_revision, view.model_dump(mode="json")
                run_id = enqueue(session, row, "development")
                view.processing_run_id = run_id
                view.processing_attempts, view.processing_error = 0, None
                return view, run_id
        except Exception:
            if stored:
                self.storage.delete(stored)
            raise

    @staticmethod
    def _require_comparison_category(view: CaseView) -> None:
        if not view.classification or view.classification.accepted != "BL_COMPARISON":
            raise ValueError("Accept the BL comparison category before reviewing shipment documents")

    @staticmethod
    def _saved_comparison(view: CaseView) -> None:
        """Replay explicitly labelled fixture readings, without pretending to run AI."""
        si = next((a for a in view.attachments if a.role == "SI" and not a.superseded), None)
        bl = next((a for a in view.attachments if a.role == "BL" and not a.superseded), None)
        view.processing, view.stage = "completed", "saved_demo"
        if not si or not bl or not si.evidence or not bl.evidence:
            view.report = None
            view.review_reasons = ["Select the correct SI and draft BL"]
            return
        readings = [{field: reading_from_evidence(field, a.evidence, [field])
                     for field in FIELDS} for a in (si, bl) if a.evidence]
        view.report = compare(readings[0], readings[1], view.input_revision,
                              validate_pair(si.evidence, bl.evidence, True))
        view.review_reasons = ["Some fields need review"] if any(f.outcome == "unresolved" for f in view.report.findings) else []

    @staticmethod
    def _require_run(session: Session, session_key: str, enabled: bool) -> None:
        if not enabled:
            raise ValueError("Live processing is disabled until the AI budget is verified")
        take_quota(session, f"live:session:{session_key}", 3)
        take_quota(session, f"live:day:{utcnow().date()}", 50)
