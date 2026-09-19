"""Public session and live-processing quota acceptance tests on PostgreSQL."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text

from averis.api import create_app
from averis.config import Settings
from averis.domain import Action, AuditEntry, CaseView, Classification
from averis.persistence import (
    Base,
    BrowserSession,
    Case,
    Counter,
    Database,
    Run,
    Workspace,
    utcnow,
)
from averis.storage import Storage
from averis.workflow import Workflow


@pytest.fixture
def postgres_quota_db(tmp_path):
    """Give each test a private schema and never touch PostgreSQL public."""
    url = os.getenv("AVERIS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AVERIS_TEST_DATABASE_URL is not configured")

    admin = create_engine(url, pool_pre_ping=True)
    schema = f"averis_quota_{uuid4().hex[:16]}"
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
        origin="http://localhost:8000",
        live_enabled=True,
        budget_verified=True,
        operator_token="test-operator",
    )
    storage = Storage(settings)
    try:
        yield db, settings, storage, schema
    finally:
        db.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _case(case_id: str, workspace_id: str = "workspace-1") -> Case:
    view = CaseView(
        id=case_id,
        subject="Quota fixture",
        sender="fixture@example.test",
        body="A deterministic quota fixture.",
        received_at=datetime.now(UTC).isoformat(),
        revision=1,
        input_revision=1,
        classification=Classification(
            suggested="GENERAL",
            accepted="GENERAL",
            confidence=1,
            probabilities={"GENERAL": 1},
            source="fixture",
            model="test-double",
        ),
        processing="completed",
        stage="complete",
        workflow="open",
        assignee="Unassigned",
        review_reasons=[],
        attachments=[],
        history=[AuditEntry(
            at=datetime.now(UTC).isoformat(),
            actor="fixture",
            action="created",
            detail="quota fixture",
        )],
    )
    return Case(
        id=case_id,
        workspace_id=workspace_id,
        revision=1,
        input_revision=1,
        state=view.model_dump(mode="json"),
    )


def _add_cases(db: Database, count: int) -> list[str]:
    case_ids = [f"case-{index}" for index in range(count)]
    with db.session() as session, session.begin():
        session.add_all(_case(case_id) for case_id in case_ids)
    return case_ids


def _accept_comparison(db: Database, storage: Storage, case_id: str, session_key: str,
                       barrier: Barrier | None = None):
    if barrier is not None:
        barrier.wait(timeout=15)
    try:
        return Workflow(db, storage).apply(
            "workspace-1",
            case_id,
            "quota-test",
            # This action enters the live path and creates a durable run only after
            # both session and global daily quotas have been reserved.
            Action(
                expected_revision=1,
                kind="category",
                category="BL_COMPARISON",
                reason="quota acceptance",
            ),
            live_enabled=True,
            session_key=session_key,
        )
    except ValueError as exc:  # assertions classify expected quota failures
        return exc


def test_demo_session_hourly_boundary_has_no_partial_workspace(postgres_quota_db):
    db, settings, _storage, _schema = postgres_quota_db
    application = create_app(settings, db)
    with TestClient(application, base_url=settings.origin) as client:
        responses = [client.post("/api/demo/session", headers={"origin": settings.origin})
                     for _ in range(11)]

    assert [response.status_code for response in responses[:10]] == [200] * 10
    assert responses[10].status_code == 422
    assert responses[10].json()["detail"] == "Demo limit reached. Saved results remain available."
    # TestClient uses a stable host, so locate the one generated hour counter.
    with db.session() as session:
        counters = session.scalars(select(Counter).where(Counter.key.like("sessions:hour:%"))).all()
        assert len(counters) == 1
        assert counters[0].value == 10
        assert session.scalar(select(func.count()).select_from(Workspace)) == 10
        assert session.scalar(select(func.count()).select_from(BrowserSession)) == 10


def test_live_session_quota_has_exactly_three_concurrent_winners(postgres_quota_db):
    db, _settings, storage, _schema = postgres_quota_db
    case_ids = _add_cases(db, 4)
    barrier = Barrier(4)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda case_id: _accept_comparison(db, storage, case_id, "same-session", barrier),
            case_ids,
        ))

    assert sum(isinstance(result, tuple) for result in results) == 3
    assert sum(isinstance(result, ValueError) for result in results) == 1
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 3
        assert session.scalar(select(Counter.value).where(Counter.key == "live:session:same-session")) == 3
        rejected = [case for case in session.scalars(select(Case)).all() if case.active_run_id is None]
        assert len(rejected) == 1
        assert rejected[0].revision == 1


def test_global_daily_quota_has_exactly_fifty_concurrent_winners(postgres_quota_db):
    db, _settings, storage, _schema = postgres_quota_db
    case_ids = _add_cases(db, 55)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda case_id: _accept_comparison(db, storage, case_id, f"session-{case_id}"),
            case_ids,
        ))

    assert sum(isinstance(result, tuple) for result in results) == 50
    assert sum(isinstance(result, ValueError) for result in results) == 5
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 50
        assert session.scalar(select(Counter.value).where(Counter.key.like("live:day:%"))) == 50
        assert session.scalar(select(func.count()).select_from(Case).where(Case.active_run_id.is_(None))) == 5


def test_global_rejection_rolls_back_session_quota_and_run_creation(postgres_quota_db):
    db, _settings, storage, _schema = postgres_quota_db
    first, second = _add_cases(db, 2)
    day_key = f"live:day:{utcnow().date()}"
    with db.session() as session, session.begin():
        session.add(Counter(key=day_key, value=49))

    accepted = _accept_comparison(db, storage, first, "rollback-session")
    rejected = _accept_comparison(db, storage, second, "rollback-session")
    assert isinstance(accepted, tuple)
    assert isinstance(rejected, ValueError)

    with db.session() as session:
        assert session.scalar(select(Counter.value).where(Counter.key == day_key)) == 50
        assert session.scalar(select(Counter.value).where(Counter.key == "live:session:rollback-session")) == 1
        assert session.scalar(select(func.count()).select_from(Run)) == 1
        rejected_case = session.get(Case, second)
        assert rejected_case is not None
        assert rejected_case.active_run_id is None
        assert rejected_case.revision == 1
