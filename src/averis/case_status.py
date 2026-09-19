"""One interpretation of report completeness for all application views."""

from typing import Literal

from pydantic import BaseModel

from averis.contracts import FIELDS
from averis.domain import CaseView


class CaseSummary(BaseModel):
    kind: Literal[
        "queued",
        "running",
        "failed",
        "unclassified",
        "categorized",
        "needs_review",
        "mismatch",
        "mismatch_review",
        "match",
    ]
    mismatches: int = 0


def summarize_case(case: CaseView) -> CaseSummary:
    if case.processing != "completed":
        return CaseSummary(kind=case.processing)
    if case.classification is None:
        return CaseSummary(kind="unclassified")
    if case.classification.accepted is None:
        return CaseSummary(kind="needs_review")
    if case.classification.accepted != "BL_COMPARISON":
        return CaseSummary(
            kind="needs_review" if case.review_reasons else "categorized"
        )
    report = case.report
    if report is None:
        return CaseSummary(kind="needs_review")
    mismatches = sum(finding.outcome == "mismatch" for finding in report.findings)
    complete = len(report.findings) == len(FIELDS) and {
        finding.field for finding in report.findings
    } == set(FIELDS)
    blocked = (
        not report.pair_valid
        or report.input_revision != case.input_revision
        or bool(report.issues)
        or bool(case.review_reasons)
        or not complete
        or any(finding.outcome == "unresolved" for finding in report.findings)
    )
    if mismatches:
        return CaseSummary(
            kind="mismatch_review" if blocked else "mismatch", mismatches=mismatches
        )
    return CaseSummary(kind="needs_review" if blocked else "match")
