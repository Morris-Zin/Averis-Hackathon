"""User-visible summaries require current, complete, trustworthy findings."""

import pytest

from averis.api_responses import CaseResponse
from averis.case_status import summarize_case
from averis.contracts import FIELDS
from averis.domain import CaseView, Classification, Finding, Reading, Report


def complete_case():
    return CaseView(
        id="case",
        subject="Shipping documents",
        sender="sender@example.test",
        body="Please compare",
        received_at="2026-09-20T00:00:00Z",
        revision=1,
        input_revision=1,
        processing="completed",
        stage="complete",
        workflow="open",
        assignee="Unassigned",
        review_reasons=[],
        attachments=[],
        history=[],
        classification=Classification(
            suggested="BL_COMPARISON",
            accepted="BL_COMPARISON",
            confidence=1,
            probabilities={"BL_COMPARISON": 1},
            model="test",
        ),
        report=Report(
            input_revision=1,
            pair_valid=True,
            findings=[
                Finding(
                    field=field,
                    outcome="match",
                    si=Reading(field=field, document_id="si"),
                    bl=Reading(field=field, document_id="bl"),
                )
                for field in FIELDS
            ],
        ),
    )


def test_only_complete_current_report_is_clear():
    case = complete_case()
    assert summarize_case(case).kind == "match"
    case.workflow = "completed"
    case.report.findings[0].outcome = "unresolved"
    assert summarize_case(case).kind == "needs_review"
    case.report.findings[1].outcome = "mismatch"
    assert summarize_case(case).model_dump() == {
        "kind": "mismatch_review",
        "mismatches": 1,
    }


@pytest.mark.parametrize(
    "problem", ["stale", "missing", "duplicate", "invalid_pair", "issue", "unaccepted"]
)
def test_incomplete_or_unaccepted_reports_never_appear_clear(problem):
    case = complete_case()
    if problem == "stale":
        case.input_revision += 1
    elif problem == "missing":
        case.report.findings.pop()
    elif problem == "duplicate":
        case.report.findings[-1] = case.report.findings[0].model_copy(deep=True)
    elif problem == "invalid_pair":
        case.report.pair_valid = False
    elif problem == "issue":
        case.report.issues.append("Unreadable page")
    else:
        case.classification.accepted = None
    assert summarize_case(case).kind == "needs_review"


def test_response_summary_does_not_leak_into_persisted_case():
    case = complete_case()
    saved = case.model_dump(mode="json")
    response = CaseResponse.model_validate(saved)
    assert response.model_dump(mode="json")["summary"]["kind"] == "match"
    assert case.model_dump(mode="json") == saved
    assert CaseView.model_validate(saved) == case


@pytest.mark.parametrize("provisional", ["match", "mismatch", "unresolved"])
def test_provisional_results_never_clear_route_as_confirmed_or_export(provisional):
    from averis.case_status import assess_case
    from averis.exporting import adapt_case

    case = complete_case()
    case.report.pair_valid = False
    for finding in case.report.findings:
        finding.outcome = "unresolved"
        finding.provisional_outcome = provisional
    assessment = assess_case(case)
    assert assessment.needs_review
    assert not assessment.can_be_clear
    assert not assessment.has_mismatch
    assert summarize_case(case).kind == "needs_review"
    exported = adapt_case(case)
    assert exported.prediction is None
    assert "pairing_unresolved" in exported.diagnostics.blockers
