"""Private persistence structures; public clients receive domain models."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    and_,
    create_engine,
    event,
    func,
    or_,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.sql.elements import ColumnElement


def utcnow() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class BrowserSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    csrf: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    input_revision: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[dict[str, object]] = mapped_column(JSON)
    active_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    accepted_pair: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    overrides: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    import_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    workflow: Mapped[str] = mapped_column(String(20), default="open")
    received_at: Mapped[str] = mapped_column(String(40), default="")
    subject: Mapped[str] = mapped_column(String(1000), default="")
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    assignee: Mapped[str] = mapped_column(String(100), default="")
    __table_args__ = (
        Index("case_workspace_received", "workspace_id", "received_at"),
        Index("case_workspace_import", "workspace_id", "import_digest", unique=True),
        Index("case_workspace_mismatch", "workspace_id", "has_mismatch"),
        Index("case_workspace_review", "workspace_id", "needs_review"),
    )


def spam_filter() -> ColumnElement[bool]:
    """SQL counterpart of spam_status; reads legacy state without a backfill.

    Human abstention is the persisted Not spam decision. Accepted categories
    always take precedence over the original model suggestion.
    """
    classification = Case.state["classification"]
    accepted = classification["accepted"].as_string()
    return or_(
        func.coalesce(accepted == "SPAM", False),
        and_(
            accepted.is_(None),
            func.coalesce(classification["suggested"].as_string() == "SPAM", False),
            func.coalesce(classification["source"].as_string(), "model") != "human",
        ),
    )


def outstanding_review_filter() -> ColumnElement[bool]:
    return and_(
        ~spam_filter(),
        or_(Case.needs_review.is_(True), Case.has_mismatch.is_(True)),
        Case.workflow == "open",
    )


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    input_revision: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(20), default="demo")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Outbox(Base):
    __tablename__ = "outbox"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generation: Mapped[int] = mapped_column(Integer, default=0)


class Budget(Base):
    __tablename__ = "budget"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    prior_spend: Mapped[int] = mapped_column(Integer, default=0)
    development: Mapped[int] = mapped_column(Integer, default=0)
    demo: Mapped[int] = mapped_column(Integer, default=0)


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(20))
    input_usd_per_million: Mapped[str | None] = mapped_column(String(50), nullable=True)
    output_usd_per_million: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    actual_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reconciliation_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Database:
    def __init__(self, url: str):
        if url.startswith("sqlite"):
            Path(".local").mkdir(exist_ok=True)
            self.engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(
                url, pool_pre_ping=True, pool_size=3, max_overflow=0
            )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.sessions()

    def create_local_schema(self) -> None:
        Base.metadata.create_all(self.engine)


@event.listens_for(Case, "before_insert")
@event.listens_for(Case, "before_update")
def project_case(_mapper: object, _connection: object, target: Case) -> None:
    """Index the shared assessment; queue flags never reimplement domain rules."""
    from averis.case_status import assess_case
    from averis.domain import CaseView

    view = CaseView.model_validate(target.state)
    assessment = assess_case(view)
    target.has_mismatch = assessment.has_mismatch
    target.needs_review = assessment.needs_review
    target.workflow, target.received_at, target.subject = (
        view.workflow,
        view.received_at,
        view.subject,
    )
    target.category = view.classification.accepted if view.classification else None
    target.assignee = view.assignee


def rebuild_projections(db: Database, *, batch_size: int = 200) -> int:
    """Recompute queue indexes from stored state without touching evidence.

    Idempotent and batched: only the derived columns (has_mismatch,
    needs_review, workflow, received_at, subject, category, assignee) are
    updated. Evidence, history, revisions and AI are never invoked. Returns the
    number of cases whose projection changed.
    """

    from sqlalchemy import select

    from averis.case_status import assess_case
    from averis.domain import CaseView

    changed = 0
    offset = 0
    while True:
        with db.session() as session, session.begin():
            rows = list(
                session.scalars(
                    select(Case).order_by(Case.id).offset(offset).limit(batch_size)
                )
            )
            if not rows:
                break
            for row in rows:
                view = CaseView.model_validate(row.state)
                assessment = assess_case(view)
                desired = {
                    "has_mismatch": assessment.has_mismatch,
                    "needs_review": assessment.needs_review,
                    "workflow": view.workflow,
                    "received_at": view.received_at,
                    "subject": view.subject,
                    "category": view.classification.accepted
                    if view.classification
                    else None,
                    "assignee": view.assignee,
                }
                for key, value in desired.items():
                    if getattr(row, key) != value:
                        setattr(row, key, value)
                        changed += 1
                        break
            offset += batch_size
            # Break when the last batch was partial; otherwise continue for the
            # next batch. Idempotent: rerunning changes nothing.
            if len(rows) < batch_size:
                break
    return changed
