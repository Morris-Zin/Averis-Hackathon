"""A completed classification is visible before slow extraction finishes."""

from datetime import timedelta

import pytest

from averis.config import Settings
from averis.domain import AuditEntry, CaseView, Classification
from averis.persistence import Base, Case, Database, Run, Workspace, utcnow
from averis.processing import LostLease, Processor
from averis.storage import Storage


def classification(suggested="BL_COMPARISON") -> Classification:
    return Classification(
        suggested=suggested,
        confidence=0.82,
        probabilities={suggested: 0.82, "GENERAL": 0.18},
        model="jev-test",
        policy_version="classification-v1",
    )


def case_view() -> CaseView:
    return CaseView(
        id="case-1",
        subject="Processing fixture",
        sender="fixture@example.test",
        body="Compare the attached documents.",
        received_at="2026-09-19T00:00:00+00:00",
        revision=2,
        input_revision=1,
        classification=None,
        processing="running",
        stage="classifying",
        workflow="open",
        assignee="John Tan",
        review_reasons=[],
        attachments=[],
        history=[
            AuditEntry(
                at="2026-09-19T00:00:00+00:00",
                actor="fixture",
                action="created",
                detail="classification publication fixture",
            )
        ],
    )


@pytest.fixture
def checkpoint_fixture(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'checkpoint.db'}",
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
        tasks_queue="",
        live_enabled=True,
        budget_verified=True,
    )
    db = Database(settings.database_url)
    Base.metadata.create_all(db.engine)
    with db.session() as session, session.begin():
        session.add(
            Workspace(id="workspace-1", expires_at=utcnow() + timedelta(days=1))
        )
        view = case_view()
        session.add(
            Case(
                id=view.id,
                workspace_id="workspace-1",
                revision=view.revision,
                input_revision=view.input_revision,
                active_run_id="run-1",
                state=view.model_dump(mode="json"),
            )
        )
        session.add(
            Run(
                id="run-1",
                case_id=view.id,
                input_revision=1,
                purpose="demo",
                status="running",
                attempts=1,
                token="token-1",
                lease_until=utcnow() + timedelta(seconds=90),
            )
        )
    return db, Processor(db, settings, Storage(settings))


def read_case(db):
    with db.session() as session:
        return CaseView.model_validate(session.get(Case, "case-1").state)


def test_classification_checkpoint_published_before_extraction_ends(
    checkpoint_fixture,
):
    db, processor = checkpoint_fixture

    processor._checkpoint(
        "run-1", "token-1", "classification", classification().model_dump(mode="json")
    )

    current = read_case(db)
    assert current.classification is not None
    assert current.classification.suggested == "BL_COMPARISON"
    assert current.stage == "classified"
    assert current.report is None
    assert current.review_reasons == []
    assert current.workflow == "open"


def test_human_classification_survives_worker_checkpoint(checkpoint_fixture):
    db, processor = checkpoint_fixture
    with db.session() as session, session.begin():
        row = session.get(Case, "case-1")
        view = CaseView.model_validate(row.state)
        view.classification = classification().model_copy(
            update={"source": "human", "accepted": "SI_REQUEST"}
        )
        row.state = view.model_dump(mode="json")

    processor._checkpoint(
        "run-1",
        "token-1",
        "classification",
        classification("GENERAL").model_dump(mode="json"),
    )

    current = read_case(db)
    assert current.classification is not None
    assert current.classification.source == "human"
    assert current.classification.accepted == "SI_REQUEST"


def test_superseded_run_cannot_publish_classification(checkpoint_fixture):
    db, processor = checkpoint_fixture
    with db.session() as session, session.begin():
        session.get(Case, "case-1").active_run_id = "run-2"

    with pytest.raises(LostLease):
        processor._checkpoint(
            "run-1",
            "token-1",
            "classification",
            classification().model_dump(mode="json"),
        )

    assert read_case(db).classification is None


def test_document_checkpoint_leaves_classification_untouched(checkpoint_fixture):
    db, processor = checkpoint_fixture

    processor._checkpoint("run-1", "token-1", "document:doc-1", {"evidence": []})

    current = read_case(db)
    assert current.classification is None
    assert current.stage == "document_read"


def test_invalid_classification_value_never_blocks_progress(checkpoint_fixture):
    db, processor = checkpoint_fixture

    processor._checkpoint("run-1", "token-1", "classification", {"bogus": True})

    current = read_case(db)
    assert current.classification is None
    assert current.stage == "classified"
