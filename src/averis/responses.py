"""Read-only HTTP projections; these are never persisted as case state."""

from pydantic import BaseModel, computed_field

from averis.case_status import CaseSummary, summarize_case
from averis.domain import CaseView


class CaseResponse(CaseView):
    @computed_field
    @property
    def summary(self) -> CaseSummary:
        return summarize_case(self)


class CasePageResponse(BaseModel):
    items: list[CaseResponse]
    total: int
    page: int
    page_size: int
