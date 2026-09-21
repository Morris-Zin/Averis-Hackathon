"""Workspace-scoped case queries; SQL and queue counts stay behind this interface."""

from dataclasses import dataclass

from sqlalchemy import func, select

from averis.domain import CaseView
from averis.persistence import Case, Database, outstanding_review_filter, spam_filter
from averis.workflow import view_of


class InvalidCaseQuery(ValueError):
    """Unsupported queue or invalid pagination/search input."""


@dataclass(frozen=True)
class CasePage:
    items: list[CaseView]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


def list_cases(
    db: Database,
    workspace_id: str,
    *,
    view: str = "all",
    q: str = "",
    page: int = 1,
    page_size: int = 25,
    category: str = "",
    assignee: str = "",
) -> CasePage:
    """Return one page and workspace counts; reject invalid input explicitly."""
    if page < 1 or not 1 <= page_size <= 100 or len(q) > 200:
        raise InvalidCaseQuery("Invalid pagination or search")
    with db.session() as session:
        query = select(Case).where(Case.workspace_id == workspace_id)
        if q:
            query = query.where(Case.subject.ilike(f"%{q}%"))
        if category:
            query = query.where(
                spam_filter() if category == "SPAM" else Case.category == category
            )
        if assignee:
            query = query.where(Case.assignee == assignee)
        if view == "mismatches":
            query = query.where(Case.has_mismatch.is_(True), ~spam_filter())
        elif view == "spam":
            query = query.where(spam_filter())
        elif view == "review":
            query = query.where(outstanding_review_filter())
        elif view in {"waiting", "completed"}:
            query = query.where(Case.workflow == view, ~spam_filter())
        elif view != "all":
            raise InvalidCaseQuery("Unknown inbox view")
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = [
            view_of(row)
            for row in session.scalars(
                query.order_by(Case.received_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ]
        counts = {
            name: session.scalar(
                select(func.count())
                .select_from(Case)
                .where(Case.workspace_id == workspace_id, predicate)
            )
            or 0
            for name, predicate in {
                "spam": spam_filter(),
                "review": outstanding_review_filter(),
            }.items()
        }
    return CasePage(
        items=items, total=total, page=page, page_size=page_size, counts=counts
    )
