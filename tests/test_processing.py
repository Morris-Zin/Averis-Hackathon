"""Durable processing regression checks with deterministic intelligence doubles."""
from __future__ import annotations

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text

from averis.config import Settings
from averis.demo import evidence
from averis.domain import AttachmentView, AuditEntry, CaseView, Classification
from averis.intelligence import ExtractionResult
from averis.persistence import Base, Case, Database, Outbox, Run, utcnow
from averis.processing import LostLease, Processor
from averis.storage import Storage
from averis.verification import reading_from_evidence


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
    with db.session() as session:
        assert session.scalar(text("SELECT current_schema()")) == schema
    settings = Settings(
        database_url=url,
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
        tasks_queue="",
        origin="http://localhost:8000",
        live_enabled=False,
    )
    storage = Storage(settings)
    try:
        yield db, settings, storage
    finally:
        db.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def processing_case(case_id: str = "case-1", input_revision: int = 1) -> CaseView:
    si_id, bl_id = "si-1", "bl-1"
    si = evidence(si_id, "SI", "SHIP-001", {field: field for field in (
        "shipper", "consignee", "notify_party", "port_of_loading",
        "port_of_discharge", "container_count", "gross_weight_kg",
    )})
    bl = evidence(bl_id, "BL", "SHIP-001", {field: field for field in (
        "shipper", "consignee", "notify_party", "port_of_loading",
        "port_of_discharge", "container_count", "gross_weight_kg",
    )})
    return CaseView(
        id=case_id,
        subject="Processing fixture",
        sender="fixture@example.test",
        body="Compare the attached documents.",
        received_at="2026-09-19T00:00:00+00:00",
        revision=1,
        input_revision=input_revision,
        classification=None,
        processing="queued",
        stage="queued",
        workflow="open",
        assignee="Unassigned",
        review_reasons=[],
        attachments=[
            AttachmentView(id=si_id, filename="si.txt", role="SI", evidence=si),
            AttachmentView(id=bl_id, filename="bl.txt", role="BL", evidence=bl),
        ],
        history=[AuditEntry(
            at="2026-09-19T00:00:00+00:00",
            actor="fixture",
            action="created",
            detail="deterministic processing fixture",
        )],
    )


def add_case_and_run(db: Database, *, input_revision: int = 1, run_status: str = "queued", attempts: int = 0):
    view = processing_case(input_revision=input_revision)
    run_id = str(uuid4())
    with db.session() as session, session.begin():
        session.add(Case(
            id=view.id,
            workspace_id="workspace-1",
            revision=view.revision,
            input_revision=view.input_revision,
            active_run_id=run_id,
            state=view.model_dump(mode="json"),
        ))
        session.add(Run(
            id=run_id,
            case_id=view.id,
            input_revision=input_revision,
            purpose="development",
            status=run_status,
            attempts=attempts,
        ))
    return view.id, run_id


class FlakyIntelligence:
    def __init__(self):
        self.classify_calls = 0
        self.extract_calls = 0

    def classify(self, _subject: str, _body: str) -> Classification:
        self.classify_calls += 1
        return Classification(
            suggested="BL_COMPARISON",
            accepted="BL_COMPARISON",
            confidence=1,
            probabilities={"BL_COMPARISON": 1},
            source="fixture",
            model="test-double",
        )

    def extract(self, document):
        self.extract_calls += 1
        if self.extract_calls == 1:
            raise RuntimeError("synthetic provider interruption")
        role = "SI" if document.document_id == "si-1" else "BL"
        fields = {
            field: reading_from_evidence(field, document, [field], confidence=1, threshold=0.8)
            for field in (
                "shipper", "consignee", "notify_party", "port_of_loading",
                "port_of_discharge", "container_count", "gross_weight_kg",
            )
        }
        return ExtractionResult(role=role, role_confidence=1, fields=fields)


def test_duplicate_completed_delivery_is_idempotent(postgres_db):
    db, settings, storage = postgres_db
    _case_id, run_id = add_case_and_run(db, run_status="completed", attempts=1)
    processor = Processor(db, settings, storage, factory=lambda *_: (_ for _ in ()).throw(AssertionError("provider called")))

    assert processor.execute(run_id) == "completed"
    assert processor.execute(run_id) == "completed"
    with db.session() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.attempts == 1


def test_checkpoint_survives_retry_and_avoids_reclassification(postgres_db):
    db, settings, storage = postgres_db
    _case_id, run_id = add_case_and_run(db)
    intelligence = FlakyIntelligence()
    processor = Processor(db, settings, storage, factory=lambda *_: intelligence)

    assert processor.execute(run_id) == "retry"
    with db.session() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "queued"
        assert run.attempts == 1
        assert "classification" in run.checkpoint

    assert processor.execute(run_id) == "completed"
    assert intelligence.classify_calls == 1
    assert intelligence.extract_calls == 3
    with db.session() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.attempts == 2
        assert "extraction:si-1" in run.checkpoint
        assert "extraction:bl-1" in run.checkpoint


def test_stale_input_revision_supersedes_before_provider_call(postgres_db):
    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db, input_revision=1)
    with db.session() as session, session.begin():
        row = session.get(Case, case_id)
        assert row is not None
        row.input_revision = 2
    called = False

    def provider(*_args):
        nonlocal called
        called = True
        raise AssertionError("stale run reached intelligence")

    processor = Processor(db, settings, storage, factory=provider)
    assert processor.execute(run_id) == "completed"
    assert called is False
    with db.session() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "superseded"


def test_exhausted_retry_is_visible_on_run_and_case(postgres_db):
    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db, attempts=3)
    processor = Processor(db, settings, storage)

    assert processor.execute(run_id) == "completed"
    with db.session() as session:
        run = session.get(Run, run_id)
        row = session.get(Case, case_id)
        assert run is not None and row is not None
        assert run.status == "failed"
        assert run.error == "attempts_exhausted"
        assert row.state["processing"] == "failed"
        assert row.state["stage"] == "attempts_exhausted"


def test_failed_dispatch_leaves_durable_outbox_for_reconcile(postgres_db, monkeypatch):
    db, settings, storage = postgres_db
    _case_id, run_id = add_case_and_run(db)
    settings.tasks_queue = "projects/test/locations/test/queues/averis"
    settings.worker_url = "https://worker.example.test"
    settings.tasks_service_account = "tasks@test.iam.gserviceaccount.com"

    class FailingTasksClient:
        def __init__(self):
            raise RuntimeError("synthetic Cloud Tasks outage")

    monkeypatch.setattr("averis.processing.tasks_v2.CloudTasksClient", FailingTasksClient)
    processor = Processor(db, settings, storage)

    assert processor.reconcile() == 0
    with db.session() as session:
        run = session.get(Run, run_id)
        outbox = session.get(Outbox, run_id)
        assert run is not None and outbox is not None
        assert run.status == "queued"
        assert outbox.dispatched_at is None


def test_replaced_run_with_same_inputs_cannot_publish_late_result(postgres_db):
    db, settings, storage = postgres_db
    case_id, old_run_id = add_case_and_run(db)
    new_run_id = str(uuid4())

    class SupersededDuringProvider(FlakyIntelligence):
        def classify(self, subject, body):
            with db.session() as session, session.begin():
                row = session.get(Case, case_id)
                session.add(Run(id=new_run_id, case_id=case_id, input_revision=1,
                                purpose="development", status="queued"))
                row.active_run_id = new_run_id
                row.state = {**row.state, "processing_run_id": new_run_id,
                             "processing": "queued", "stage": "newer_run"}
            return super().classify(subject, body)

    provider = SupersededDuringProvider()
    processor = Processor(db, settings, storage, factory=lambda *_: provider)
    assert processor.execute(old_run_id) == "completed"
    with db.session() as session:
        old = session.get(Run, old_run_id)
        row = session.get(Case, case_id)
        assert old.status == "superseded"
        assert row.input_revision == 1
        assert row.active_run_id == new_run_id
        assert row.state["stage"] == "newer_run"
        assert row.state["classification"] is None
    assert provider.extract_calls == 0


def test_operational_metrics_are_aggregate_only(postgres_db):
    db, settings, storage = postgres_db
    add_case_and_run(db, attempts=2)
    metrics = Processor(db, settings, storage).metrics()
    assert metrics["run_states"] == {"queued": 1}
    assert metrics["retried_runs"] == 1
    assert metrics["attempts"] == 2
    assert metrics["cases"] == 1
    assert "subject" not in str(metrics)
    assert "fixture@example.test" not in str(metrics)


def test_expired_attempt_cannot_checkpoint_and_recovery_preserves_completed_stage(postgres_db):
    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db, run_status="running", attempts=1)
    classification = Classification(suggested="GENERAL", accepted="GENERAL", confidence=1,
                                    probabilities={"GENERAL": 1}, source="model", model="test")
    with db.session() as session, session.begin():
        run = session.get(Run, run_id)
        run.token = "dead-worker"
        run.lease_until = utcnow() - timedelta(seconds=1)
        run.checkpoint = {"classification": classification.model_dump(mode="json")}
    processor = Processor(db, settings, storage, factory=lambda *_: FlakyIntelligence())
    with pytest.raises(LostLease):
        processor._checkpoint(run_id, "dead-worker", "document:si-1", {})
    assert processor.reconcile() == 0  # local queue deliberately has no cloud dispatcher
    assert processor.execute(run_id) == "completed"
    with db.session() as session:
        run = session.get(Run, run_id)
        case = session.get(Case, case_id)
        assert run.attempts == 2
        assert run.token != "dead-worker"
        assert case.state["classification"]["accepted"] == "GENERAL"
        assert case.state["processing"] == "completed"


def test_checkpoint_progress_preserves_reviewer_edits(postgres_db):
    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db, run_status="running", attempts=1)
    with db.session() as session, session.begin():
        run = session.get(Run, run_id)
        run.token = "current-worker"
        run.lease_until = utcnow() + timedelta(seconds=90)
        row = session.get(Case, case_id)
        row.state = {**row.state, "assignee": "Mei Lin", "workflow": "waiting"}
    Processor(db, settings, storage)._checkpoint(run_id, "current-worker", "document:si-1", {})
    with db.session() as session:
        row = session.get(Case, case_id)
        assert row.state["assignee"] == "Mei Lin"
        assert row.state["workflow"] == "waiting"
        assert row.state["stage"] == "document_read"
        assert row.input_revision == 1
