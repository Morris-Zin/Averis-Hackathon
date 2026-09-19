"""Durable, version-fenced processing; each network delivery is at least once."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Literal, TypeGuard

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2
from google.protobuf.duration_pb2 import Duration
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from averis.budget import BudgetAuthority, BudgetUnavailable
from averis.config import Settings
from averis.documents import read_document_bounded
from averis.domain import AuditEntry, CaseView
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
from averis.pipeline import (
    APPLICATION_DEADLINE_SECONDS,
    Checkpoints,
    InvalidCheckpoint,
    MissingDocument,
    ProcessingInput,
    ProcessingResult,
    ShipmentPipeline,
)
from averis.storage import Storage

log = logging.getLogger(__name__)


class LostLease(RuntimeError):
    pass


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=utcnow().tzinfo) if value.tzinfo is None else value


DeliveryOutcome = Literal["missing", "busy", "completed", "retry"]
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 25
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class ClaimedRun:
    run_id: str
    token: str
    purpose: str
    inputs: ProcessingInput
    checkpoint: dict[str, object]


def owns_lease(run: Run | None, token: str) -> TypeGuard[Run]:
    return bool(
        run
        and run.token == token
        and run.status == "running"
        and run.lease_until
        and aware(run.lease_until) > utcnow()
    )


def current_input(case: Case, run: Run) -> bool:
    return case.input_revision == run.input_revision and case.active_run_id == run.id


def failure_stage(error: Exception) -> str:
    if isinstance(error, BudgetUnavailable):
        return "budget_unavailable"
    if isinstance(error, MissingDocument):
        return "source_unavailable"
    if isinstance(error, InvalidCheckpoint):
        return "checkpoint_invalid"
    return "processing_failed"


def failure_message(error: Exception, *, retrying: bool) -> str:
    if isinstance(error, BudgetUnavailable):
        return "AI spending is unavailable. Ask the operator to check the allowance and ledger."
    if isinstance(error, MissingDocument):
        return "An original document is unavailable. Ask the operator to restore or re-import it."
    if isinstance(error, InvalidCheckpoint):
        return "Saved processing state is invalid. Ask the operator to investigate before retrying."
    if isinstance(error, ValueError):
        return "Processing data could not be validated. Ask the operator to investigate before retrying."
    if retrying:
        return "The processing attempt was interrupted. Background delivery will retry."
    return "Processing failed after three attempts. You can request a new run."


class Processor:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        storage: Storage,
        factory: Callable[[str, str], Intelligence] | None = None,
    ):
        self.db = db
        self.settings = settings
        self.storage = storage
        self.factory: Callable[[str, str], Intelligence] = factory or self._jev

    def _jev(self, run_id: str, purpose: str) -> Intelligence:
        return Jev(
            self.settings, BudgetAuthority(self.db, self.settings), run_id, purpose
        )

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
                parent=self.settings.tasks_queue,
                task=tasks_v2.Task(
                    name=name,
                    dispatch_deadline=Duration(seconds=600),
                    http_request=tasks_v2.HttpRequest(
                        http_method=tasks_v2.HttpMethod.POST,
                        url=f"{self.settings.worker_url}/internal/runs/{run_id}",
                        oidc_token=tasks_v2.OidcToken(
                            service_account_email=self.settings.tasks_service_account,
                            audience=self.settings.worker_url,
                        ),
                    ),
                ),
                timeout=5,
            )
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
            if not owns_lease(run, token):
                raise LostLease()
            case = session.scalar(
                select(Case).where(Case.id == run.case_id).with_for_update()
            )
            if case is None or not current_input(case, run):
                raise LostLease()
            run.checkpoint = {**run.checkpoint, key: value}
            run.lease_until = utcnow() + timedelta(seconds=LEASE_SECONDS)
            stage = (
                "classified"
                if key == "classification"
                else "document_read"
                if key.startswith("document:")
                else "fields_extracted"
            )
            current = CaseView.model_validate(case.state)
            current.stage = stage
            current.revision += 1
            case.revision, case.state = (
                current.revision,
                current.model_dump(mode="json"),
            )

    def _heartbeat(self, run_id: str, token: str, stop: Event) -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                with self.db.session() as session, session.begin():
                    run = session.scalar(
                        select(Run).where(Run.id == run_id).with_for_update()
                    )
                    if not owns_lease(run, token):
                        return
                    case = session.get(Case, run.case_id)
                    if case is None or not current_input(case, run):
                        return
                    run.lease_until = utcnow() + timedelta(seconds=LEASE_SECONDS)
            except Exception:  # noqa: BLE001 - lease expires instead of granting unsafe ownership
                log.warning("heartbeat_failed", extra={"run_id": run_id})
                return

    def execute(self, run_id: str) -> DeliveryOutcome:
        started = time.monotonic()
        outcome = "unexpected_failure"
        try:
            outcome = self._execute(run_id)
            return outcome
        finally:
            log.info(
                "processing_delivery run_id=%s outcome=%s duration_ms=%d",
                run_id,
                outcome,
                int((time.monotonic() - started) * 1000),
            )

    def metrics(self) -> dict[str, object]:
        """Return operational aggregates without emails, documents or credentials."""
        with self.db.session() as session:
            states = {
                status: count
                for status, count in session.execute(
                    select(Run.status, func.count()).group_by(Run.status)
                )
            }
            oldest = session.scalar(
                select(func.min(Run.created_at)).where(Run.status == "queued")
            )
            attempts = session.scalar(select(func.sum(Run.attempts))) or 0
            retried = (
                session.scalar(
                    select(func.count()).select_from(Run).where(Run.attempts > 1)
                )
                or 0
            )
            cases = session.scalar(select(func.count()).select_from(Case)) or 0
            reviews = (
                session.scalar(
                    select(func.count())
                    .select_from(Case)
                    .where(Case.needs_review.is_(True))
                )
                or 0
            )
            undispatched = (
                session.scalar(
                    select(func.count())
                    .select_from(Outbox)
                    .where(Outbox.dispatched_at.is_(None))
                )
                or 0
            )
        return {
            "run_states": states,
            "attempts": attempts,
            "retried_runs": retried,
            "oldest_queued_seconds": max(
                0, int((utcnow() - aware(oldest)).total_seconds())
            )
            if oldest
            else 0,
            "undispatched": undispatched,
            "cases": cases,
            "needs_review": reviews,
            "review_rate": reviews / cases if cases else 0,
        }

    def _claim(self, run_id: str) -> ClaimedRun | DeliveryOutcome:
        with self.db.session() as session, session.begin():
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if not run:
                return "missing"
            if run.status in {"completed", "failed", "superseded"}:
                return "completed"
            if (
                run.status == "running"
                and run.lease_until
                and aware(run.lease_until) > utcnow()
            ):
                return "busy"
            if run.attempts >= MAX_ATTEMPTS:
                self._exhausted(session, run)
                return "completed"
            row = session.get(Case, run.case_id)
            if (
                row is None
                or row.input_revision != run.input_revision
                or row.active_run_id != run.id
            ):
                run.status = "superseded"
                return "completed"
            token = uid()
            run.token, run.status = token, "running"
            run.lease_until = utcnow() + timedelta(seconds=LEASE_SECONDS)
            run.attempts += 1
            accepted_pair = row.accepted_pair
            overrides = dict(row.overrides)
            view = CaseView.model_validate(row.state)
            view.report = None
            view.processing, view.stage = "running", "classifying"
            view.processing_attempts, view.processing_error = run.attempts, None
            row.state = view.model_dump(mode="json")
            return ClaimedRun(
                run_id=run.id,
                token=token,
                purpose=run.purpose,
                inputs=ProcessingInput(view, accepted_pair, overrides),
                checkpoint=dict(run.checkpoint),
            )

    def _load_document(self, document_id: str) -> bytes:
        with self.db.session() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise MissingDocument("missing_attachment")
            object_key = document.object_key
        # Object storage can block; release the database connection first.
        return self.storage.read(object_key)

    def _execute(self, run_id: str) -> DeliveryOutcome:
        claim = self._claim(run_id)
        if not isinstance(claim, ClaimedRun):
            return claim
        stop = Event()
        heartbeat = Thread(
            target=self._heartbeat, args=(run_id, claim.token, stop), daemon=True
        )
        heartbeat.start()
        deadline = time.monotonic() + APPLICATION_DEADLINE_SECONDS
        try:
            checkpoints = Checkpoints(
                claim.checkpoint,
                lambda key, value: self._checkpoint(run_id, claim.token, key, value),
            )
            pipeline = ShipmentPipeline(
                self.factory(run_id, claim.purpose),
                checkpoints,
                self._load_document,
                read_document_bounded,
                lambda: deadline - time.monotonic(),
            )
            result = pipeline.process(claim.inputs)
            if time.monotonic() >= deadline:
                raise TimeoutError("application_deadline")
            self._publish(claim, result)
            return "completed"
        except LostLease:
            return self._lost_lease(run_id, claim.token)
        except Exception as exc:  # noqa: BLE001 - persist failure before acknowledging delivery.
            return self._record_failure(run_id, claim.token, exc)
        finally:
            stop.set()
            heartbeat.join(timeout=2)

    def _publish(self, claim: ClaimedRun, result: ProcessingResult) -> None:
        with self.db.session() as session, session.begin():
            run = session.scalar(
                select(Run).where(Run.id == claim.run_id).with_for_update()
            )
            if not owns_lease(run, claim.token):
                raise LostLease()
            row = session.scalar(
                select(Case).where(Case.id == run.case_id).with_for_update()
            )
            run.result = result.apply_to(claim.inputs.case).model_dump(mode="json")
            if row is None or not current_input(row, run):
                run.status = "superseded"
                return
            current = result.apply_to(CaseView.model_validate(row.state))
            current.processing_attempts = run.attempts
            current.processing_error = None
            current.revision += 1
            current.history.append(
                AuditEntry(
                    at=utcnow().isoformat(),
                    actor="Processing",
                    action="processed",
                    detail="Saved source-backed processing outcome",
                )
            )
            row.revision = current.revision
            row.state = current.model_dump(mode="json")
            run.status = "completed"

    def _lost_lease(self, run_id: str, token: str) -> DeliveryOutcome:
        with self.db.session() as session, session.begin():
            stale_run = session.scalar(
                select(Run).where(Run.id == run_id).with_for_update()
            )
            if stale_run and stale_run.token == token:
                current_case = session.get(Case, stale_run.case_id)
                if (
                    not current_case
                    or current_case.input_revision != stale_run.input_revision
                    or current_case.active_run_id != stale_run.id
                ):
                    stale_run.status = "superseded"
                    return "completed"
        return "busy"

    def _record_failure(
        self, run_id: str, token: str, exc: Exception
    ) -> DeliveryOutcome:
        terminal = isinstance(exc, (BudgetUnavailable, ValueError))
        with self.db.session() as session, session.begin():
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run and run.token == token:
                run.status = (
                    "failed" if terminal or run.attempts >= MAX_ATTEMPTS else "queued"
                )
                run.error = type(exc).__name__
                row = session.scalar(
                    select(Case).where(Case.id == run.case_id).with_for_update()
                )
                if (
                    row
                    and row.input_revision == run.input_revision
                    and row.active_run_id == run.id
                ):
                    current = CaseView.model_validate(row.state)
                    current.processing = (
                        "failed" if run.status == "failed" else "queued"
                    )
                    current.stage = failure_stage(exc)
                    current.processing_attempts = run.attempts
                    current.processing_error = failure_message(
                        exc, retrying=run.status == "queued"
                    )
                    current.revision += 1
                    row.revision, row.state = (
                        current.revision,
                        current.model_dump(mode="json"),
                    )
                terminal = run.status == "failed"
        log.warning(
            "processing_attempt_failed",
            extra={"run_id": run_id, "error_type": type(exc).__name__},
        )
        return "completed" if terminal else "retry"

    @staticmethod
    def _exhausted(session: Session, run: Run) -> None:
        run.status, run.error, run.token = "failed", "attempts_exhausted", None
        row = session.scalar(
            select(Case).where(Case.id == run.case_id).with_for_update()
        )
        if (
            row
            and row.input_revision == run.input_revision
            and row.active_run_id == run.id
        ):
            view = CaseView.model_validate(row.state)
            view.processing, view.stage = "failed", "attempts_exhausted"
            view.processing_attempts = run.attempts
            view.processing_error = (
                "Processing failed after three attempts. You can request a new run."
            )
            view.revision += 1
            row.revision, row.state = view.revision, view.model_dump(mode="json")

    def expire_workspaces(self) -> int:
        """Remove disposable data after session expiry; keep the spend ledger."""
        count = 0
        with self.db.session() as session, session.begin():
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
                    self.storage.delete(document.object_key)
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

    def reconcile(self) -> int:
        self.expire_workspaces()
        pending: list[str] = []
        with self.db.session() as session, session.begin():
            runs = session.scalars(
                select(Run)
                .where(Run.status.in_(["queued", "running"]))
                .with_for_update(skip_locked=True)
            ).all()
            for run in runs:
                if (
                    run.status == "running"
                    and run.lease_until
                    and aware(run.lease_until) > utcnow()
                ):
                    continue
                if run.attempts >= MAX_ATTEMPTS:
                    self._exhausted(session, run)
                    continue
                outbox = session.get(Outbox, run.id)
                if outbox is None:
                    outbox = Outbox(run_id=run.id)
                    session.add(outbox)
                elif outbox.dispatched_at and aware(
                    outbox.dispatched_at
                ) > utcnow() - timedelta(minutes=15):
                    continue
                else:
                    outbox.generation += 1
                    outbox.dispatched_at = None
                run.status, run.token = "queued", None
                pending.append(run.id)
        return sum(self.dispatch(run_id) for run_id in pending)
