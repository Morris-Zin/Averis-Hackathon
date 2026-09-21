"""Read-only HTTP projections; these are never persisted as case state."""

from pydantic import BaseModel, computed_field

from averis.case_status import CaseSummary, summarize_case
from averis.domain import CaseView, Classification


class CaseResponse(CaseView):
    @computed_field
    @property
    def summary(self) -> CaseSummary:
        return summarize_case(self)


class QueueCaseResponse(BaseModel):
    """Queue facts only; document evidence and history belong to case detail."""

    id: str
    subject: str
    sender: str
    received_at: str
    classification: Classification | None
    processing: str
    assignee: str
    summary: CaseSummary

    @classmethod
    def from_case(cls, case: CaseView) -> "QueueCaseResponse":
        return cls(
            id=case.id,
            subject=case.subject,
            sender=case.sender,
            received_at=case.received_at,
            classification=case.classification,
            processing=case.processing,
            assignee=case.assignee,
            summary=summarize_case(case),
        )


class CasePageResponse(BaseModel):
    items: list[QueueCaseResponse]
    total: int
    page: int
    page_size: int
