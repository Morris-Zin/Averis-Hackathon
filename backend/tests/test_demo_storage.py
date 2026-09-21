"""Shared immutable synthetic seeds with isolated workspace metadata."""

from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from averis.case_queries import list_cases
from averis.config import Settings
from averis.demo import seed
from averis.maintenance import expire_workspaces
from averis.persistence import Base, Budget, Case, Database, Document, Workspace, utcnow
from averis.storage import Storage


@pytest.fixture
def demo_store(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'demo.db'}",
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
    )
    db = Database(settings.database_url)
    Base.metadata.create_all(db.engine)
    storage = Storage(settings)
    return db, storage


def make_workspace(
    db: Database, storage: Storage, workspace_id: str, *, expired: bool = False
) -> None:
    expires_at = (
        utcnow() - timedelta(minutes=1) if expired else utcnow() + timedelta(hours=1)
    )
    with db.session() as session, session.begin():
        workspace = Workspace(id=workspace_id, expires_at=expires_at)
        session.add(workspace)
        seed(session, workspace, storage)


def test_seed_objects_are_shared_while_workspace_metadata_isolated(demo_store):
    db, storage = demo_store
    make_workspace(db, storage, "workspace-a")
    make_workspace(db, storage, "workspace-b")

    with db.session() as session:
        documents = session.scalars(
            select(Document).order_by(Document.workspace_id)
        ).all()
        cases = session.scalars(select(Case)).all()

    assert {case.workspace_id for case in cases} == {"workspace-a", "workspace-b"}
    assert {case.category for case in cases if case.category} == {
        "BL_COMPARISON",
        "SI_REQUEST",
        "INVOICE_QUERY",
        "GENERAL",
        "SPAM",
    }
    first = [
        document for document in documents if document.workspace_id == "workspace-a"
    ]
    second = [
        document for document in documents if document.workspace_id == "workspace-b"
    ]
    assert first and second
    assert {document.object_key for document in first}.isdisjoint(
        document.object_key for document in second
    )
    assert {document.sha256 for document in first} == {
        document.sha256 for document in second
    }
    assert all(storage.read(document.object_key) for document in documents)

    seed_files = list((Path(storage.settings.storage_dir) / "seeds").glob("*"))
    assert len(seed_files) == len({document.sha256 for document in documents})
    assert all(document.object_key.startswith("seeds/") for document in documents)


def test_expired_workspace_cleanup_keeps_shared_seed_objects(demo_store):
    db, storage = demo_store
    make_workspace(db, storage, "expired", expired=True)
    with db.session() as session:
        before = session.scalars(
            select(Document).where(Document.workspace_id == "expired")
        ).all()
        assert before
        original = storage.read(before[0].object_key)
    seed_files = list((Path(storage.settings.storage_dir) / "seeds").glob("*"))

    assert expire_workspaces(db, storage) == 1

    with db.session() as session:
        assert not session.scalar(select(Workspace).where(Workspace.id == "expired"))
        assert not session.scalars(
            select(Document).where(Document.workspace_id == "expired")
        ).all()
    assert list((Path(storage.settings.storage_dir) / "seeds").glob("*")) == seed_files
    assert storage.read(before[0].object_key) == original
    storage.delete(before[0].object_key)
    assert storage.read(before[0].object_key) == original


def test_seed_reference_requires_a_safe_reference(demo_store):
    _db, storage = demo_store
    valid_key, _ = storage.put_seed(b"demo", str(uuid4()))
    assert storage.read(valid_key) == b"demo"
    with pytest.raises(ValueError, match="UUID"):
        storage.put_seed(b"demo", "../escape")


def test_malformed_seed_keys_are_rejected(demo_store):
    _db, storage = demo_store
    digest = sha256(b"demo").hexdigest()
    malformed = [
        "seeds/..",
        "seeds/random",
        f"seeds/{digest.upper()}",
        f"seeds/{digest}/../escape",
        f"seeds/{digest}/{uuid4()}/extra",
    ]
    for key in malformed:
        with pytest.raises(ValueError, match="seed"):
            storage.read(key)
        with pytest.raises(ValueError, match="seed"):
            storage.delete(key)


def test_case_queries_preserve_team_filters_pagination_and_workspace_scope(demo_store):
    db, storage = demo_store
    make_workspace(db, storage, "team-a")
    make_workspace(db, storage, "team-b")
    all_cases = list_cases(db, "team-a")
    other_cases = list_cases(db, "team-b")
    assert all_cases.total == 8
    assert {item.assignee for item in all_cases.items} == {
        "John Tan",
        "Aisha Rahman",
        "Mei Lin",
    }
    assert {item.id for item in all_cases.items}.isdisjoint(
        item.id for item in other_cases.items
    )
    first = list_cases(db, "team-a", page_size=3)
    second = list_cases(db, "team-a", page_size=3, page=2)
    assert first.items + second.items == all_cases.items[:6]
    filtered = list_cases(db, "team-a", assignee="Aisha Rahman", category="SI_REQUEST")
    assert filtered.total == 1
    assert filtered.items[0].assignee == "Aisha Rahman"
    assert filtered.counts == all_cases.counts
    assert list_cases(db, "team-a", q="invoice").total == 1
    with pytest.raises(ValueError, match="Unknown inbox view"):
        list_cases(db, "team-a", view="invalid")


def test_cleanup_failure_retains_rows_for_retry_and_keeps_budget(
    demo_store, monkeypatch
):
    db, storage = demo_store
    make_workspace(db, storage, "expired", expired=True)
    make_workspace(db, storage, "active")
    with db.session() as session, session.begin():
        session.add(Budget(id=1, prior_spend=123, development=456, demo=789))

    def fail_delete(_key):
        raise OSError("storage unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "delete", fail_delete)
        with pytest.raises(OSError):
            expire_workspaces(db, storage)
    with db.session() as session:
        assert session.get(Workspace, "expired") is not None
        assert session.scalar(
            select(Document).where(Document.workspace_id == "expired")
        )
    assert expire_workspaces(db, storage) == 1
    assert expire_workspaces(db, storage) == 0
    with db.session() as session:
        assert session.get(Workspace, "expired") is None
        assert session.get(Workspace, "active") is not None
        budget = session.get(Budget, 1)
        assert (budget.prior_spend, budget.development, budget.demo) == (123, 456, 789)
