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
from averis.versions import OCR_PROFILE, READER_VERSION


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
        live_enabled=True,
        budget_verified=True,
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
    si = evidence(
        si_id,
        "SI",
        "SHIP-001",
        {
            field: field
            for field in (
                "shipper",
                "consignee",
                "notify_party",
                "port_of_loading",
                "port_of_discharge",
                "container_count",
                "gross_weight_kg",
            )
        },
    )
    bl = evidence(
        bl_id,
        "BL",
        "SHIP-001",
        {
            field: field
            for field in (
                "shipper",
                "consignee",
                "notify_party",
                "port_of_loading",
                "port_of_discharge",
                "container_count",
                "gross_weight_kg",
            )
        },
    )
    si.reader_version = bl.reader_version = READER_VERSION
    si.ocr_profile = bl.ocr_profile = OCR_PROFILE
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
        history=[
            AuditEntry(
                at="2026-09-19T00:00:00+00:00",
                actor="fixture",
                action="created",
                detail="deterministic processing fixture",
            )
        ],
    )


def add_case_and_run(
    db: Database,
    *,
    input_revision: int = 1,
    run_status: str = "queued",
    attempts: int = 0,
):
    view = processing_case(input_revision=input_revision)
    run_id = str(uuid4())
    with db.session() as session, session.begin():
        session.add(
            Case(
                id=view.id,
                workspace_id="workspace-1",
                revision=view.revision,
                input_revision=view.input_revision,
                active_run_id=run_id,
                state=view.model_dump(mode="json"),
            )
        )
        session.add(
            Run(
                id=run_id,
                case_id=view.id,
                input_revision=input_revision,
                purpose="development",
                status=run_status,
                attempts=attempts,
            )
        )
    return view.id, run_id


class FlakyIntelligence:
    def __init__(self):
        self.classify_calls = 0
        self.extract_calls = 0

    def classify(
        self,
        _subject: str,
        _body: str,
        *,
        attachment_filenames: tuple[str, ...] = (),
        load_attachment_previews=None,
    ) -> Classification:
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
            field: reading_from_evidence(
                field, document, [field], confidence=1, threshold=0.8
            )
            for field in (
                "shipper",
                "consignee",
                "notify_party",
                "port_of_loading",
                "port_of_discharge",
                "container_count",
                "gross_weight_kg",
            )
        }
        return ExtractionResult(role=role, role_confidence=1, fields=fields)


@pytest.mark.parametrize("disabled_setting", ["live_enabled", "budget_verified"])
def test_disabled_processing_holds_run_before_claim(postgres_db, disabled_setting):
    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db)
    setattr(settings, disabled_setting, False)
    settings.tasks_queue = "projects/test/locations/test/queues/averis"
    processor = Processor(
        db,
        settings,
        storage,
        factory=lambda *_: (_ for _ in ()).throw(AssertionError("provider called")),
    )

    assert processor.execute(run_id) == "held"
    assert processor.dispatch(run_id) is False
    with db.session() as session:
        run = session.get(Run, run_id)
        row = session.get(Case, case_id)
        assert run is not None and row is not None
        assert run.status == "queued"
        assert run.attempts == 0
        assert row.state["processing"] == "queued"


def test_cleanup_failure_does_not_block_run_reconciliation(
    postgres_db, monkeypatch, caplog
):
    db, settings, storage = postgres_db
    _case_id, run_id = add_case_and_run(db)
    processor = Processor(db, settings, storage)

    def fail_cleanup() -> int:
        raise RuntimeError("sensitive-storage-detail")

    monkeypatch.setattr(processor, "expire_workspaces", fail_cleanup)
    with caplog.at_level("WARNING", logger="averis.processing"):
        assert processor.reconcile() == 0

    with db.session() as session:
        assert session.get(Outbox, run_id) is not None
    assert "workspace_expiry_failed error_type=RuntimeError" in caplog.text
    assert "sensitive-storage-detail" not in caplog.text


def test_disabled_processing_still_acknowledges_terminal_and_missing_runs(postgres_db):
    db, settings, storage = postgres_db
    _case_id, run_id = add_case_and_run(db, run_status="completed", attempts=1)
    settings.live_enabled = False
    processor = Processor(db, settings, storage)

    assert processor.execute(run_id) == "completed"
    assert processor.execute("missing-run") == "missing"


def test_duplicate_completed_delivery_is_idempotent(postgres_db):
    db, settings, storage = postgres_db
    _case_id, run_id = add_case_and_run(db, run_status="completed", attempts=1)
    processor = Processor(
        db,
        settings,
        storage,
        factory=lambda *_: (_ for _ in ()).throw(AssertionError("provider called")),
    )

    assert processor.execute(run_id) == "completed"
    assert processor.execute(run_id) == "completed"
    with db.session() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.attempts == 1


def test_corrupt_checkpoint_stops_without_repeating_paid_work(postgres_db):
    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db)
    with db.session() as session, session.begin():
        session.get(Run, run_id).checkpoint = {"classification": {"unexpected": True}}
    intelligence = FlakyIntelligence()
    processor = Processor(db, settings, storage, factory=lambda *_: intelligence)

    assert processor.execute(run_id) == "completed"
    assert intelligence.classify_calls == 0
    assert intelligence.extract_calls == 0
    with db.session() as session:
        run = session.get(Run, run_id)
        case = CaseView.model_validate(session.get(Case, case_id).state)
        assert run.status == "failed"
        assert case.stage == "checkpoint_invalid"
        assert case.processing == "failed"
        assert case.report is None


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

    monkeypatch.setattr(
        "averis.processing.tasks_v2.CloudTasksClient", FailingTasksClient
    )
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
        def classify(
            self,
            subject,
            body,
            *,
            attachment_filenames: tuple[str, ...] = (),
            load_attachment_previews=None,
        ):
            with db.session() as session, session.begin():
                row = session.get(Case, case_id)
                session.add(
                    Run(
                        id=new_run_id,
                        case_id=case_id,
                        input_revision=1,
                        purpose="development",
                        status="queued",
                    )
                )
                row.active_run_id = new_run_id
                row.state = {
                    **row.state,
                    "processing_run_id": new_run_id,
                    "processing": "queued",
                    "stage": "newer_run",
                }
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


def test_expired_attempt_cannot_checkpoint_and_recovery_preserves_completed_stage(
    postgres_db,
):
    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db, run_status="running", attempts=1)
    classification = Classification(
        suggested="GENERAL",
        accepted="GENERAL",
        confidence=1,
        probabilities={"GENERAL": 1},
        source="model",
        model="test",
    )
    with db.session() as session, session.begin():
        run = session.get(Run, run_id)
        run.token = "dead-worker"
        run.lease_until = utcnow() - timedelta(seconds=1)
        run.checkpoint = {"classification": classification.model_dump(mode="json")}
    processor = Processor(db, settings, storage, factory=lambda *_: FlakyIntelligence())
    with pytest.raises(LostLease):
        processor._checkpoint(run_id, "dead-worker", "document:si-1", {})
    assert (
        processor.reconcile() == 0
    )  # local queue deliberately has no cloud dispatcher
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
    Processor(db, settings, storage)._checkpoint(
        run_id, "current-worker", "document:si-1", {}
    )
    with db.session() as session:
        row = session.get(Case, case_id)
        assert row.state["assignee"] == "Mei Lin"
        assert row.state["workflow"] == "waiting"
        assert row.state["stage"] == "document_read"
        assert row.input_revision == 1


@pytest.mark.parametrize("category,elapsed", [("BL_COMPARISON", 436), ("GENERAL", 481)])
def test_application_deadline_never_publishes_a_late_success(
    postgres_db, monkeypatch, category, elapsed
):
    from types import SimpleNamespace

    from averis import processing

    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db, attempts=2)
    clock = [0.0]
    monkeypatch.setattr(processing, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    class LateClassification:
        def classify(
            self,
            _subject,
            _body,
            *,
            attachment_filenames: tuple[str, ...] = (),
            load_attachment_previews=None,
        ):
            clock[0] = elapsed
            return Classification(
                suggested=category,
                accepted=category,
                confidence=1,
                probabilities={category: 1},
                source="fixture",
                model="test",
            )

        def extract(self, _document):
            raise AssertionError(
                "No extraction may start beyond the application deadline"
            )

    processor = Processor(
        db, settings, storage, factory=lambda *_: LateClassification()
    )
    assert (
        processor.execute(run_id) == "completed"
    )  # Terminal task acknowledgement, not a match.
    with db.session() as session:
        run = session.get(Run, run_id)
        row = session.get(Case, case_id)
        assert run.status == "failed"
        assert run.error == "TimeoutError"
        view = CaseView.model_validate(row.state)
        assert view.processing == "failed"
        assert view.report is None
        assert view.processing_error


def test_parser_and_provider_callbacks_release_database_connections(
    postgres_db, monkeypatch
):
    from averis import processing
    from averis.persistence import Document

    db, settings, storage = postgres_db
    case_id, run_id = add_case_and_run(db)
    original_evidence = {}
    with db.session() as session, session.begin():
        row = session.get(Case, case_id)
        view = CaseView.model_validate(row.state)
        for attachment in view.attachments:
            original_evidence[attachment.id] = attachment.evidence
            attachment.evidence = None
            content = b"Synthetic parser boundary fixture"
            key, digest = storage.put(content)
            session.add(
                Document(
                    id=attachment.id,
                    workspace_id="workspace-1",
                    case_id=case_id,
                    filename=attachment.filename,
                    object_key=key,
                    sha256=digest,
                    size=len(content),
                )
            )
        row.state = view.model_dump(mode="json")

    callbacks = []

    def observe(name):
        # Exclude the independent lease heartbeat; inspect the processing thread's boundaries.
        assert db.engine.pool.checkedout() == 0
        callbacks.append(name)

    def read(document_id, _filename, _content, *, timeout_seconds):
        observe("parser")
        assert 0 < timeout_seconds <= 120
        return original_evidence[document_id]

    original_read = storage.read

    def read_storage(key):
        observe("storage")
        return original_read(key)

    monkeypatch.setattr(storage, "read", read_storage)

    class ObservedIntelligence:
        def classify(
            self,
            _subject,
            _body,
            *,
            attachment_filenames: tuple[str, ...] = (),
            load_attachment_previews=None,
        ):
            observe("classification")
            return Classification(
                suggested="BL_COMPARISON",
                accepted="BL_COMPARISON",
                confidence=1,
                probabilities={"BL_COMPARISON": 1},
                source="fixture",
                model="test",
            )

        def extract(self, document):
            observe("extraction")
            return ExtractionResult(
                role="SI" if document.document_id == "si-1" else "BL",
                role_confidence=1,
                fields={
                    field: reading_from_evidence(field, document, [], confidence=0)
                    for field in (
                        "shipper",
                        "consignee",
                        "notify_party",
                        "port_of_loading",
                        "port_of_discharge",
                        "container_count",
                        "gross_weight_kg",
                    )
                },
            )

    monkeypatch.setattr(processing, "read_document_bounded", read)
    processor = Processor(
        db, settings, storage, factory=lambda *_: ObservedIntelligence()
    )
    monkeypatch.setattr(processor, "_heartbeat", lambda *_: None)
    assert processor.execute(run_id) == "completed"
    assert callbacks == [
        "classification",
        "storage",
        "parser",
        "extraction",
        "storage",
        "parser",
        "extraction",
    ]
    with db.session() as session:
        assert session.get(Run, run_id).status == "completed"
