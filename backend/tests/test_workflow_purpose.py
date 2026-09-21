"""Processing-purpose continuity across workflow re-enqueue operations."""

from datetime import timedelta

from sqlalchemy import select

from averis.config import Settings
from averis.domain import AuditEntry, CaseView, RetryAction
from averis.email_intake import import_email
from averis.persistence import Base, Case, Database, Run, Workspace, utcnow
from averis.storage import Storage
from averis.workflow import Workflow


def setup_database(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'purpose.db'}",
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
    )
    db = Database(settings.database_url)
    Base.metadata.create_all(db.engine)
    with db.session() as session, session.begin():
        session.add(
            Workspace(
                id="workspace-1",
                expires_at=utcnow() + timedelta(days=1),
            )
        )
    return db, Storage(settings)


def test_imported_case_retry_keeps_development_budget_purpose(tmp_path):
    db, storage = setup_database(tmp_path)
    imported = import_email(
        db,
        storage,
        "workspace-1",
        "Operator",
        "Imported shipment",
        "sender@example.test",
        "Check the attached shipping documents.",
        [("draft.txt", b"Shipment ID: TEST-001")],
    )

    view, retry_run_id = Workflow(db, storage).apply(
        "workspace-1",
        imported.view.id,
        "Operator",
        RetryAction(expected_revision=imported.view.revision),
        live_enabled=True,
    )

    assert view.processing_run_id == retry_run_id
    with db.session() as session:
        runs = session.scalars(
            select(Run).where(Run.case_id == imported.view.id).order_by(Run.created_at)
        ).all()
        assert [run.purpose for run in runs] == ["development", "development"]


def test_demo_case_without_prior_run_uses_demo_budget_purpose(tmp_path):
    db, _storage = setup_database(tmp_path)
    view = CaseView(
        id="demo-case",
        subject="Controlled demo",
        sender="demo@example.test",
        body="Saved demo case",
        received_at=utcnow().isoformat(),
        revision=1,
        input_revision=1,
        processing="completed",
        stage="saved_demo",
        workflow="open",
        assignee="John Tan",
        review_reasons=[],
        attachments=[],
        history=[
            AuditEntry(
                at=utcnow().isoformat(),
                actor="Demo setup",
                action="created",
                detail="Controlled fixture",
            )
        ],
    )
    with db.session() as session, session.begin():
        session.add(
            Case(
                id=view.id,
                workspace_id="workspace-1",
                revision=1,
                input_revision=1,
                state=view.model_dump(mode="json"),
            )
        )

    _updated, run_id = Workflow(db, _storage).apply(
        "workspace-1",
        view.id,
        "John Tan",
        RetryAction(expected_revision=view.revision),
        live_enabled=True,
    )

    with db.session() as session:
        run = session.get(Run, run_id)
        assert run is not None and run.purpose == "demo"
