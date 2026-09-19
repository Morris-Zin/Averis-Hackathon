"""PostgreSQL acceptance checks for the durable polling runner."""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text

from averis.config import Settings
from averis.domain import AuditEntry, CaseView, Classification, DocumentEvidence
from averis.intelligence import ExtractionResult
from averis.persistence import Base, Case, Database, Outbox, Run, utcnow
from averis.processing import Processor
from averis.runner import DurableRunner, RunnerOptions
from averis.storage import Storage


@pytest.fixture
def postgres_db(tmp_path):
    url = os.getenv("AVERIS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AVERIS_TEST_DATABASE_URL is not configured")

    admin = create_engine(url, pool_pre_ping=True)
    schema = f"averis_test_{uuid4().hex[:16]}"
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    db = Database(url)

    @event.listens_for(db.engine, "connect")
    def set_test_schema(raw_connection, _connection_record):
        cursor = raw_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()
        raw_connection.commit()

    Base.metadata.create_all(db.engine)
    settings = Settings(
        database_url=url,
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
        origin="http://localhost:8000",
        live_enabled=True,
        budget_verified=True,
    )
    try:
        yield db, settings, Storage(settings)
    finally:
        db.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def add_run(
    db: Database,
    suffix: str,
    *,
    attempts: int = 0,
    input_revision: int = 1,
    case_input_revision: int | None = None,
    create_outbox: bool = True,
) -> tuple[str, str]:
    case_id = f"case-{suffix}"
    run_id = str(uuid4())
    revision = input_revision if case_input_revision is None else case_input_revision
    view = CaseView(
        id=case_id,
        subject=f"Runner fixture {suffix}",
        sender="fixture@example.test",
        body="A deterministic runner fixture.",
        received_at="2026-09-20T00:00:00+00:00",
        revision=1,
        input_revision=revision,
        classification=None,
        processing="queued",
        stage="queued",
        workflow="open",
        assignee="Unassigned",
        review_reasons=[],
        attachments=[],
        history=[AuditEntry(
            at="2026-09-20T00:00:00+00:00",
            actor="fixture",
            action="created",
            detail="durable runner fixture",
        )],
    )
    with db.session() as session, session.begin():
        session.add(Case(
            id=case_id,
            workspace_id="workspace-1",
            revision=1,
            input_revision=revision,
            active_run_id=run_id,
            state=view.model_dump(mode="json"),
        ))
        session.add(Run(
            id=run_id,
            case_id=case_id,
            input_revision=input_revision,
            purpose="development",
            status="queued",
            attempts=attempts,
        ))
        if create_outbox:
            session.add(Outbox(run_id=run_id))
    return case_id, run_id


class GeneralIntelligence:
    def __init__(self, barrier: Barrier | None = None, failures: int = 0):
        self.barrier = barrier
        self.failures = failures
        self.calls = 0

    def classify(self, _subject: str, _body: str) -> Classification:
        self.calls += 1
        if self.barrier:
            self.barrier.wait(timeout=3)
        if self.calls <= self.failures:
            raise RuntimeError("synthetic interruption")
        return Classification(
            suggested="GENERAL",
            accepted="GENERAL",
            confidence=1,
            probabilities={"GENERAL": 1},
            source="fixture",
            model="test-double",
        )

    def extract(self, _document: DocumentEvidence) -> ExtractionResult:
        raise AssertionError("GENERAL messages must not reach extraction")


def runner(
    db: Database,
    settings: Settings,
    storage: Storage,
    intelligence: GeneralIntelligence,
    *,
    concurrency: int = 1,
    retry_base_seconds: float = 60,
) -> DurableRunner:
    processor = Processor(db, settings, storage, factory=lambda *_: intelligence)
    return DurableRunner(processor, RunnerOptions(
        concurrency=concurrency,
        poll_seconds=0.01,
        reconcile_seconds=60,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=max(retry_base_seconds, 120),
    ))


def test_runner_processes_durable_outbox_without_cloud_tasks(postgres_db):
    db, settings, storage = postgres_db
    _case_id, run_id = add_run(db, "one")
    worker = runner(db, settings, storage, GeneralIntelligence())

    assert worker.run_available() == {run_id: "completed"}
    with db.session() as session:
        run = session.get(Run, run_id)
        outbox = session.get(Outbox, run_id)
        assert run is not None and outbox is not None
        assert run.status == "completed"
        assert run.attempts == 1
        assert outbox.dispatched_at is not None


@pytest.mark.parametrize("disabled_setting", ["live_enabled", "budget_verified"])
def test_disabled_processing_holds_queued_work(postgres_db, disabled_setting):
    db, settings, storage = postgres_db
    _case_id, run_id = add_run(db, f"disabled-{disabled_setting}")
    setattr(settings, disabled_setting, False)
    worker = runner(db, settings, storage, GeneralIntelligence())

    assert worker.run_available() == {}
    with db.session() as session:
        run = session.get(Run, run_id)
        outbox = session.get(Outbox, run_id)
        assert run is not None and outbox is not None
        assert run.status == "queued"
        assert run.attempts == 0
        assert outbox.dispatched_at is None


def test_periodic_reconcile_repairs_missing_outbox(postgres_db):
    db, settings, storage = postgres_db
    _case_id, run_id = add_run(db, "missing-outbox", create_outbox=False)
    worker = runner(db, settings, storage, GeneralIntelligence())

    assert worker.run_available() == {run_id: "completed"}
    with db.session() as session:
        assert session.get(Outbox, run_id) is not None


def test_ready_run_after_256_delayed_rows_is_not_starved(postgres_db):
    db, settings, storage = postgres_db
    delayed_run_ids = [add_run(db, f"delayed-{index}")[1] for index in range(256)]
    _case_id, ready_run_id = add_run(db, "ready-after-delayed")
    with db.session() as session, session.begin():
        claimed_at = utcnow()
        for run_id in delayed_run_ids:
            run = session.get(Run, run_id)
            outbox = session.get(Outbox, run_id)
            assert run is not None and outbox is not None
            run.attempts = 1
            outbox.dispatched_at = claimed_at

    worker = runner(db, settings, storage, GeneralIntelligence())

    assert worker.run_available() == {ready_run_id: "completed"}
    with db.session() as session:
        assert session.get(Run, delayed_run_ids[0]).status == "queued"
        assert session.get(Run, delayed_run_ids[-1]).status == "queued"


def test_transient_claim_failure_waits_for_next_poll_without_sensitive_log(
    postgres_db,
    monkeypatch,
    caplog,
):
    db, settings, storage = postgres_db
    _case_id, run_id = add_run(db, "claim-recovery")
    worker = runner(db, settings, storage, GeneralIntelligence())
    original_claim = worker._claim
    calls = 0

    def flaky_claim(limit: int) -> list[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("secret-database-address")
        return original_claim(limit)

    monkeypatch.setattr(worker, "_claim", flaky_claim)
    with caplog.at_level(logging.WARNING, logger="averis.runner"):
        assert worker.run_available() == {}
    assert "runner_claim_failed error_type=RuntimeError" in caplog.text
    assert "secret-database-address" not in caplog.text

    assert worker.run_available() == {run_id: "completed"}


def test_retry_delay_is_durable_and_failed_work_resumes(postgres_db):
    db, settings, storage = postgres_db
    _case_id, run_id = add_run(db, "retry")
    intelligence = GeneralIntelligence(failures=1)
    worker = runner(db, settings, storage, intelligence)

    assert worker.run_available() == {run_id: "retry"}
    assert worker.run_available() == {}
    with db.session() as session, session.begin():
        outbox = session.get(Outbox, run_id)
        assert outbox is not None and outbox.dispatched_at is not None
        outbox.dispatched_at = utcnow() - timedelta(seconds=61)

    assert worker.run_available() == {run_id: "completed"}
    with db.session() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.attempts == 2
        assert run.status == "completed"
    assert intelligence.calls == 2


def test_runner_delegates_stale_and_exhausted_state_to_processor(postgres_db):
    db, settings, storage = postgres_db
    stale_case_id, stale_run_id = add_run(
        db,
        "stale",
        input_revision=1,
        case_input_revision=2,
    )
    exhausted_case_id, exhausted_run_id = add_run(db, "exhausted", attempts=3)
    intelligence = GeneralIntelligence()
    worker = runner(db, settings, storage, intelligence)

    assert worker.run_available() == {stale_run_id: "completed"}
    with db.session() as session:
        stale = session.get(Run, stale_run_id)
        exhausted = session.get(Run, exhausted_run_id)
        exhausted_case = session.get(Case, exhausted_case_id)
        assert stale is not None and stale.status == "superseded"
        assert exhausted is not None and exhausted.status == "failed"
        assert exhausted.error == "attempts_exhausted"
        assert exhausted_case is not None
        assert exhausted_case.state["stage"] == "attempts_exhausted"
        assert session.get(Case, stale_case_id) is not None
    assert intelligence.calls == 0


def test_runner_honors_two_delivery_concurrency_bound(postgres_db):
    db, settings, storage = postgres_db
    _case_one, run_one = add_run(db, "parallel-one")
    _case_two, run_two = add_run(db, "parallel-two")
    intelligence = GeneralIntelligence(barrier=Barrier(2))
    worker = runner(db, settings, storage, intelligence, concurrency=2)

    assert worker.run_available() == {
        run_one: "completed",
        run_two: "completed",
    }
    assert intelligence.calls == 2


def test_runner_rejects_cloud_tasks_and_more_than_two_workers(postgres_db):
    db, settings, storage = postgres_db
    processor = Processor(db, settings, storage, factory=lambda *_: GeneralIntelligence())

    with pytest.raises(ValueError, match="between one and two"):
        DurableRunner(processor, RunnerOptions(concurrency=3))
    settings.tasks_queue = "projects/example/locations/example/queues/example"
    with pytest.raises(ValueError, match="cannot be combined"):
        DurableRunner(processor)
