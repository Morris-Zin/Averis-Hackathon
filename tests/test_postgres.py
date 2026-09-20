"""Concurrency and budget regression checks against isolated PostgreSQL schemas."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text

from averis.budget import BudgetAuthority, BudgetUnavailable
from averis.config import Settings
from averis.domain import Action, AuditEntry, CaseView, Classification
from averis.persistence import Base, Budget, Case, Database, Reservation
from averis.storage import Storage
from averis.workflow import Conflict, Workflow


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
        origin="http://localhost:8000",
        live_enabled=True,
        budget_verified=True,
        input_usd_per_million="1",
        output_usd_per_million="0",
    )
    storage = Storage(settings)
    try:
        yield db, settings, storage, schema
    finally:
        db.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def case_view(case_id: str = "case-1", revision: int = 1) -> CaseView:
    return CaseView(
        id=case_id,
        subject="Concurrency fixture",
        sender="fixture@example.test",
        body="A deterministic PostgreSQL fixture.",
        received_at="2026-09-19T00:00:00+00:00",
        revision=revision,
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
        history=[
            AuditEntry(
                at="2026-09-19T00:00:00+00:00",
                actor="fixture",
                action="created",
                detail="deterministic fixture",
            )
        ],
    )


def add_case(
    db: Database, workspace_id: str = "workspace-1", case_id: str = "case-1"
) -> None:
    view = case_view(case_id)
    with db.session() as session, session.begin():
        session.add(
            Case(
                id=case_id,
                workspace_id=workspace_id,
                revision=view.revision,
                input_revision=view.input_revision,
                state=view.model_dump(mode="json"),
            )
        )


def test_workflow_concurrent_edits_have_one_winner(postgres_db):
    db, _settings, storage, _schema = postgres_db
    add_case(db)
    workflows = [Workflow(db, storage), Workflow(db, storage)]
    barrier = Barrier(2)

    def apply_edit(workflow: Workflow, assignee: str):
        barrier.wait()
        try:
            return workflow.apply(
                "workspace-1",
                "case-1",
                assignee,
                Action(expected_revision=1, kind="assign", assignee=assignee),
                live_enabled=False,
            )
        except Conflict as exc:  # assertions below classify the result
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: apply_edit(*pair),
                zip(workflows, ("Mei Lin", "Aisha Rahman")),
            )
        )

    assert sum(isinstance(result, tuple) for result in results) == 1
    assert sum(isinstance(result, Conflict) for result in results) == 1
    with db.session() as session:
        row = session.get(Case, "case-1")
        assert row is not None
        assert row.revision == 2
        assert row.state["assignee"] in {"Mei Lin", "Aisha Rahman"}


def test_budget_reservation_race_allows_only_one_reservation(postgres_db):
    db, settings, _storage, _schema = postgres_db
    # payload=1, questions=1, input rate=1 USD/M tokens gives 32,772 micros.
    with db.session() as session, session.begin():
        session.add(Budget(id=1, development=5_000_000 - 32_772, demo=0))

    authority = BudgetAuthority(db, settings)

    def reserve(index: int):
        try:
            return authority.reserve(f"run-{index}", "development", 1, 1)
        except (
            BudgetUnavailable
        ) as exc:  # one contender must lose the row lock/budget race
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, (1, 2)))

    assert sum(isinstance(result, str) for result in results) == 1
    assert sum(isinstance(result, BudgetUnavailable) for result in results) == 1
    with db.session() as session:
        budget = session.get(Budget, 1)
        reservations = session.scalars(select(Reservation)).all()
        assert budget is not None
        assert budget.development == 5_000_000
        assert len(reservations) == 1


def test_concurrent_settlement_releases_reservation_only_once(postgres_db):
    db, settings, _, _ = postgres_db
    with db.session() as session, session.begin():
        session.add(Budget(id=1, prior_spend=0, development=0, demo=0))
    authority = BudgetAuthority(db, settings)
    reservation_id = authority.reserve("same-paid-call", "development", 100, 1)
    barrier = Barrier(2)

    def settle(_index):
        barrier.wait()
        return authority.settle_success(reservation_id, 50, 0, "same-request")

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(settle, range(2))) == [True, True]
    with db.session() as session:
        assert session.get(Budget, 1).development == 50
        assert session.get(Reservation, reservation_id).actual_amount == 50
