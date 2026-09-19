"""Durable, version-fenced processing; each network delivery is at least once."""
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import cast

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2
from google.protobuf.duration_pb2 import Duration
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from averis.budget import BudgetAuthority, BudgetUnavailable
from averis.config import Settings
from averis.documents import read_document_bounded
from averis.domain import AuditEntry, CaseView, Classification, Reading
from averis.intelligence import Intelligence, Jev
from averis.persistence import (
    BrowserSession,
    Case,
    Database,
    Document,
    Outbox,
    Run,
    Workspace,
    uid,
    utcnow,
)
from averis.storage import Storage
from averis.verification import compare, validate_pair

log = logging.getLogger(__name__)


class LostLease(RuntimeError):
    pass


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=utcnow().tzinfo) if value.tzinfo is None else value


class Processor:
    def __init__(self, db: Database, settings: Settings, storage: Storage,
                 factory: Callable[[str, str], Intelligence] | None = None):
        self.db, self.settings, self.storage = db, settings, storage
        self.factory: Callable[[str, str], Intelligence] = factory or self._jev

    def _jev(self, run_id: str, purpose: str) -> Intelligence:
        return Jev(self.settings, BudgetAuthority(self.db, self.settings), run_id, purpose)

    def dispatch(self, run_id: str) -> bool:
        if not self.settings.tasks_queue:
            return False
        with self.db.session() as session:
            outbox = session.get(Outbox, run_id)
            if outbox is None or outbox.dispatched_at:
                return True
            generation = outbox.generation
        name = f"{self.settings.tasks_queue}/tasks/{run_id}-{generation}"
        try:
            client = tasks_v2.CloudTasksClient()
            client.create_task(  # pyright: ignore[reportUnknownMemberType] -- generated Google SDK overload includes untyped transport arguments
                parent=self.settings.tasks_queue, task=tasks_v2.Task(
                name=name, dispatch_deadline=Duration(seconds=600),
                http_request=tasks_v2.HttpRequest(
                    http_method=tasks_v2.HttpMethod.POST,
                    url=f"{self.settings.worker_url}/internal/runs/{run_id}",
                    oidc_token=tasks_v2.OidcToken(service_account_email=self.settings.tasks_service_account,
                                                 audience=self.settings.worker_url))), timeout=5)
        except AlreadyExists:
            pass
        except Exception:  # noqa: BLE001 - outbox remains durable for provider/transport failures
            log.warning("task_dispatch_pending", extra={"run_id": run_id})
            return False
        with self.db.session() as session, session.begin():
            outbox = session.get(Outbox, run_id)
            if outbox and outbox.generation == generation:
                outbox.dispatched_at = utcnow()
        return True

    def _checkpoint(self, run_id: str, token: str, key: str, value: object) -> None:
        with self.db.session() as session, session.begin():
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if not run or run.token != token or run.status != "running" or not run.lease_until or aware(run.lease_until) <= utcnow():
                raise LostLease()
            case = session.scalar(select(Case).where(Case.id == run.case_id).with_for_update())
            if not case or case.input_revision != run.input_revision or case.active_run_id != run.id:
                raise LostLease()
            run.checkpoint = {**run.checkpoint, key: value}
            run.lease_until = utcnow() + timedelta(seconds=90)
            stage = ("classified" if key == "classification" else
                     "document_read" if key.startswith("document:") else "fields_extracted")
            current = CaseView.model_validate(case.state)
            current.stage = stage
            current.revision += 1
            case.revision, case.state = current.revision, current.model_dump(mode="json")

    def _heartbeat(self, run_id: str, token: str, stop: Event) -> None:
        while not stop.wait(25):
            try:
                with self.db.session() as session, session.begin():
                    run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
                    if not run or run.token != token or run.status != "running" or not run.lease_until or aware(run.lease_until) <= utcnow():
                        return
                    case = session.get(Case, run.case_id)
                    if not case or case.input_revision != run.input_revision or case.active_run_id != run.id:
                        return
                    run.lease_until = utcnow() + timedelta(seconds=90)
            except Exception:  # noqa: BLE001 - lease expires instead of granting unsafe ownership
                log.warning("heartbeat_failed", extra={"run_id": run_id})
                return

    def execute(self, run_id: str) -> str:
        started = time.monotonic()
        outcome = "unexpected_failure"
        try:
            outcome = self._execute(run_id)
            return outcome
        finally:
            log.info("processing_delivery run_id=%s outcome=%s duration_ms=%d",
                     run_id, outcome, int((time.monotonic() - started) * 1000))

    def metrics(self) -> dict[str, object]:
        """Return operational aggregates without emails, documents or credentials."""
        with self.db.session() as session:
            states = {status: count for status, count in session.execute(
                select(Run.status, func.count()).group_by(Run.status))}
            oldest = session.scalar(select(func.min(Run.created_at)).where(Run.status == "queued"))
            attempts = session.scalar(select(func.sum(Run.attempts))) or 0
            retried = session.scalar(select(func.count()).select_from(Run).where(Run.attempts > 1)) or 0
            cases = session.scalar(select(func.count()).select_from(Case)) or 0
            reviews = session.scalar(select(func.count()).select_from(Case).where(Case.needs_review.is_(True))) or 0
            undispatched = session.scalar(select(func.count()).select_from(Outbox).where(Outbox.dispatched_at.is_(None))) or 0
        return {"run_states": states, "attempts": attempts, "retried_runs": retried,
                "oldest_queued_seconds": max(0, int((utcnow() - aware(oldest)).total_seconds())) if oldest else 0,
                "undispatched": undispatched, "cases": cases,
                "needs_review": reviews, "review_rate": reviews / cases if cases else 0}

    def _execute(self, run_id: str) -> str:
        with self.db.session() as session, session.begin():
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if not run:
                return "missing"
            if run.status in {"completed", "failed", "superseded"}:
                return "completed"
            if run.status == "running" and run.lease_until and aware(run.lease_until) > utcnow():
                return "busy"
            if run.attempts >= 3:
                self._exhausted(session, run)
                return "completed"
            row = session.get(Case, run.case_id)
            if row is None or row.input_revision != run.input_revision or row.active_run_id != run.id:
                run.status = "superseded"
                return "completed"
            token = uid()
            run.token, run.status = token, "running"
            run.lease_until = utcnow() + timedelta(seconds=90)
            run.attempts += 1
            accepted_pair = row.accepted_pair
            overrides = dict(row.overrides)
            view = CaseView.model_validate(row.state)
            view.report = None
            view.processing, view.stage = "running", "classifying"
            view.processing_attempts, view.processing_error = run.attempts, None
            row.state = view.model_dump(mode="json")
            checkpoint = dict(run.checkpoint)
            purpose = run.purpose
        stop = Event()
        heartbeat = Thread(target=self._heartbeat, args=(run_id, token, stop), daemon=True)
        heartbeat.start()
        deadline = time.monotonic() + 480
        try:
            intelligence = self.factory(run_id, purpose)
            if "classification" in checkpoint:
                view.classification = Classification.model_validate(checkpoint["classification"])
            elif not view.classification or view.classification.source != "human":
                view.classification = intelligence.classify(view.subject, view.body)
                self._checkpoint(run_id, token, "classification", view.classification.model_dump(mode="json"))
            view.review_reasons = []
            if view.classification.accepted is None:
                view.review_reasons = ["Check category"]
                view.report = None
            elif view.classification.accepted == "BL_COMPARISON":
                readings: dict[str, dict[str, Reading]] = {}
                for attachment in view.attachments:
                    if attachment.superseded:
                        continue
                    if time.monotonic() >= deadline - 45:
                        raise TimeoutError("application_deadline")
                    key = f"document:{attachment.id}"
                    if key in checkpoint:
                        saved = cast(dict[str, object], checkpoint[key])
                        from averis.domain import DocumentEvidence
                        attachment.evidence = DocumentEvidence.model_validate(saved["evidence"])
                    if attachment.evidence is None:
                        with self.db.session() as session:
                            document = session.get(Document, attachment.id)
                            if document is None:
                                raise ValueError("missing_attachment")
                            content = self.storage.read(document.object_key)
                        attachment.evidence = read_document_bounded(attachment.id, attachment.filename, content,
                            timeout_seconds=min(120, deadline - time.monotonic() - 45))
                        self._checkpoint(run_id, token, key, {"evidence": attachment.evidence.model_dump(mode="json")})
                    evidence = attachment.evidence
                    if evidence.issues:
                        view.review_reasons.extend(evidence.issues)
                    extraction_key = f"extraction:{attachment.id}"
                    if extraction_key in checkpoint:
                        saved = cast(dict[str, object], checkpoint[extraction_key])
                        role = str(saved["role"])
                        attachment.role_confidence = float(str(saved.get("role_confidence", 0)))
                        fields = {k: Reading.model_validate(v) for k, v in cast(dict[str, object], saved["fields"]).items()}
                    elif evidence.blocks and len(evidence.blocks) <= 240:
                        extraction = intelligence.extract(evidence)
                        role, fields = extraction.role, extraction.fields
                        attachment.role_confidence = extraction.role_confidence
                        self._checkpoint(run_id, token, extraction_key, {"role": role, "role_confidence": extraction.role_confidence,
                            "fields": {k: v.model_dump(mode="json") for k, v in fields.items()}})
                    else:
                        view.review_reasons.append("Document cannot be reliably extracted")
                        continue
                    if accepted_pair:
                        attachment.role = "SI" if attachment.id == accepted_pair[0] else "BL" if attachment.id == accepted_pair[1] else "unknown"
                    else:
                        attachment.role = "SI" if role == "SI" else "BL" if role == "BL" else "unknown"
                    for field in fields:
                        saved_override = overrides.get(f"{attachment.id}:{field}")
                        if saved_override:
                            fields[field] = Reading.model_validate(saved_override)
                    readings[attachment.id] = fields
                sis = [a for a in view.attachments if a.role == "SI" and not a.superseded]
                bls = [a for a in view.attachments if a.role == "BL" and not a.superseded]
                if len(sis) == 1 and len(bls) == 1:
                    si, bl = sis[0], bls[0]
                    if si.evidence and bl.evidence and si.id in readings and bl.id in readings:
                        manually_paired = accepted_pair == [si.id, bl.id]
                        valid = validate_pair(si.evidence, bl.evidence, manually_paired)
                        view.report = compare(readings[si.id], readings[bl.id], view.input_revision, valid, view.review_reasons)
                        view.review_reasons.extend(view.report.issues)
                        if any(f.outcome == "unresolved" for f in view.report.findings):
                            view.review_reasons.append("Some fields need review")
                    else:
                        view.review_reasons.append("Unreadable comparison documents")
                else:
                    view.report = None
                    view.review_reasons.append("Select the correct SI and draft BL")
            else:
                view.report = None
            if time.monotonic() >= deadline:
                raise TimeoutError("application_deadline")
            view.processing, view.stage = "completed", "complete"
            view.review_reasons = sorted(set(view.review_reasons))
            with self.db.session() as session, session.begin():
                run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
                if not run or run.token != token or run.status != "running" or not run.lease_until or aware(run.lease_until) <= utcnow():
                    raise LostLease()
                row = session.scalar(select(Case).where(Case.id == run.case_id).with_for_update())
                run.result = view.model_dump(mode="json")
                if row and row.input_revision == run.input_revision and row.active_run_id == run.id:
                    current = CaseView.model_validate(row.state)
                    # Preserve concurrent assignment/workflow edits; only processing owns these outputs.
                    current.classification, current.attachments, current.report = view.classification, view.attachments, view.report
                    current.processing, current.stage, current.review_reasons = view.processing, view.stage, view.review_reasons
                    current.processing_attempts, current.processing_error = run.attempts, None
                    current.revision += 1
                    current.history.append(AuditEntry(at=utcnow().isoformat(), actor="Processing", action="processed", detail="Saved source-backed processing outcome"))
                    row.revision, row.state = current.revision, current.model_dump(mode="json")
                    run.status = "completed"
                else:
                    run.status = "superseded"
            return "completed"
        except LostLease:
            with self.db.session() as session, session.begin():
                stale_run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
                if stale_run and stale_run.token == token:
                    current_case = session.get(Case, stale_run.case_id)
                    if not current_case or current_case.input_revision != stale_run.input_revision or current_case.active_run_id != stale_run.id:
                        stale_run.status = "superseded"
                        return "completed"
            return "busy"
        except Exception as exc:  # noqa: BLE001 - persist bounded failure, never fabricate success
            terminal = isinstance(exc, (BudgetUnavailable, ValueError))
            with self.db.session() as session, session.begin():
                run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
                if run and run.token == token:
                    run.status = "failed" if terminal or run.attempts >= 3 else "queued"
                    run.error = type(exc).__name__
                    row = session.scalar(select(Case).where(Case.id == run.case_id).with_for_update())
                    if row and row.input_revision == run.input_revision and row.active_run_id == run.id:
                        current = CaseView.model_validate(row.state)
                        current.processing = "failed" if run.status == "failed" else "queued"
                        current.stage = "budget_unavailable" if isinstance(exc, BudgetUnavailable) else "processing_failed"
                        current.processing_attempts = run.attempts
                        current.processing_error = (
                            "AI spending is unavailable. Ask the operator to check the allowance and ledger."
                            if isinstance(exc, BudgetUnavailable) else
                            "The provider response could not be validated. Retry or ask the operator to investigate."
                            if isinstance(exc, ValueError) else
                            "The processing attempt was interrupted. Background delivery will retry."
                            if run.status == "queued" else
                            "Processing failed after three attempts. You can request a new run."
                        )
                        current.revision += 1
                        row.revision, row.state = current.revision, current.model_dump(mode="json")
                    terminal = run.status == "failed"
            log.warning("processing_attempt_failed", extra={"run_id": run_id, "error_type": type(exc).__name__})
            return "completed" if terminal else "retry"
        finally:
            stop.set()
            heartbeat.join(timeout=2)

    @staticmethod
    def _exhausted(session: Session, run: Run) -> None:
        run.status, run.error, run.token = "failed", "attempts_exhausted", None
        row = session.scalar(select(Case).where(Case.id == run.case_id).with_for_update())
        if row and row.input_revision == run.input_revision and row.active_run_id == run.id:
            view = CaseView.model_validate(row.state)
            view.processing, view.stage = "failed", "attempts_exhausted"
            view.processing_attempts = run.attempts
            view.processing_error = "Processing failed after three attempts. You can request a new run."
            view.revision += 1
            row.revision, row.state = view.revision, view.model_dump(mode="json")

    def expire_workspaces(self) -> int:
        """Remove disposable data after session expiry; keep the spend ledger."""
        count = 0
        with self.db.session() as session, session.begin():
            expired = session.scalars(select(Workspace).where(Workspace.expires_at < utcnow())
                                      .limit(100).with_for_update(skip_locked=True)).all()
            for workspace in expired:
                cases = select(Case.id).where(Case.workspace_id == workspace.id)
                runs = select(Run.id).where(Run.case_id.in_(cases))
                # Keep object rows until deletion succeeds, so a failed delete is retried.
                for document in session.scalars(select(Document).where(Document.workspace_id == workspace.id)):
                    self.storage.delete(document.object_key)
                session.execute(delete(Outbox).where(Outbox.run_id.in_(runs)))
                session.execute(delete(Run).where(Run.case_id.in_(cases)))
                session.execute(delete(Document).where(Document.workspace_id == workspace.id))
                session.execute(delete(Case).where(Case.workspace_id == workspace.id))
                session.execute(delete(BrowserSession).where(BrowserSession.workspace_id == workspace.id))
                session.delete(workspace)
                count += 1
        return count

    def reconcile(self) -> int:
        self.expire_workspaces()
        pending: list[str] = []
        with self.db.session() as session, session.begin():
            runs = session.scalars(select(Run).where(Run.status.in_(["queued", "running"])).with_for_update(skip_locked=True)).all()
            for run in runs:
                if run.status == "running" and run.lease_until and aware(run.lease_until) > utcnow():
                    continue
                if run.attempts >= 3:
                    self._exhausted(session, run)
                    continue
                outbox = session.get(Outbox, run.id)
                if outbox is None:
                    outbox = Outbox(run_id=run.id)
                    session.add(outbox)
                elif outbox.dispatched_at and aware(outbox.dispatched_at) > utcnow() - timedelta(minutes=15):
                    continue
                else:
                    outbox.generation += 1
                    outbox.dispatched_at = None
                run.status, run.token = "queued", None
                pending.append(run.id)
        return sum(self.dispatch(run_id) for run_id in pending)
