"""Transactional tests for the framework-independent intake boundary."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from averis.config import Settings
from averis.intake import import_email
from averis.persistence import Base, Case, Database, Document, Outbox, Workspace, utcnow
from averis.storage import Storage


@pytest.fixture
def intake_fixture(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'intake.db'}",
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
    )
    db = Database(settings.database_url)
    Base.metadata.create_all(db.engine)
    with db.session() as session, session.begin():
        session.add(
            Workspace(id="workspace-1", expires_at=utcnow() + timedelta(days=1))
        )
    return db, Storage(settings), Path(settings.storage_dir)


def call_import(db, storage):
    return import_email(
        db,
        storage,
        "workspace-1",
        "John Tan",
        "New shipping documents",
        "sender@example.test",
        "Please check these documents.",
        [("draft.txt", b"Shipment ID: TEST-001\nContainer count: 4")],
    )


def test_import_deduplicates_and_persists_one_run(intake_fixture):
    db, storage, _root = intake_fixture

    first = call_import(db, storage)
    second = call_import(db, storage)

    assert first.run_id
    assert second.run_id is None
    assert second.view.id == first.view.id
    with db.session() as session:
        assert len(session.scalars(select(Case)).all()) == 1
        assert len(session.scalars(select(Document)).all()) == 1
        assert len(session.scalars(select(Outbox)).all()) == 1


def test_import_failure_cleans_objects_and_metadata(intake_fixture, monkeypatch):
    db, storage, root = intake_fixture

    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("synthetic transaction failure")

    monkeypatch.setattr("averis.intake.enqueue", fail_enqueue)
    with pytest.raises(RuntimeError, match="transaction failure"):
        call_import(db, storage)

    with db.session() as session:
        assert not session.scalars(select(Case)).all()
        assert not session.scalars(select(Document)).all()
        assert not session.scalars(select(Outbox)).all()
    assert not [path for path in root.rglob("*") if path.is_file()]
