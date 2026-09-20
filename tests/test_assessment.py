"""Shared assessment matrices for summary, queue flags and export."""

from test_case_status import complete_case

from averis.case_status import assess_case, summarize_case
from averis.domain import AttachmentView, DocumentEvidence, EvidenceBlock, Location
from averis.exporting import adapt_case


def evidence(doc_id: str, issues: list[str] | None = None) -> DocumentEvidence:
    return DocumentEvidence(
        document_id=doc_id,
        blocks=[
            EvidenceBlock(
                id=f"{doc_id}:b1",
                text="Shipper: Test",
                locations=[Location(kind="text", line_start=1, line_end=1)],
            )
        ],
        issues=issues or [],
    )


def test_matrices_cover_stale_incomplete_duplicate_unaccepted_mixed():
    base = complete_case()
    assert assess_case(base).can_be_clear is True
    assert summarize_case(base).kind == "match"

    stale = complete_case()
    stale.input_revision += 1
    assert assess_case(stale).report_current is False
    assert summarize_case(stale).kind == "needs_review"

    incomplete = complete_case()
    assert incomplete.report is not None
    incomplete.report.findings.pop()
    assert assess_case(incomplete).fields_complete_unique is False

    duplicate = complete_case()
    assert duplicate.report is not None
    duplicate.report.findings[-1] = duplicate.report.findings[0].model_copy(deep=True)
    assert assess_case(duplicate).fields_complete_unique is False

    unaccepted = complete_case()
    assert unaccepted.classification is not None
    unaccepted.classification.accepted = None
    assert assess_case(unaccepted).classification_accepted is None

    mixed = complete_case()
    assert mixed.report is not None
    mixed.report.findings[0].outcome = "mismatch"
    mixed.report.findings[1].outcome = "unresolved"
    mixed.report.findings[1].si.issue = "missing_value"
    mixed.report.findings[1].si.normalized = None
    mixed.report.findings[1].bl.normalized = None
    assessment = assess_case(mixed)
    assert assessment.mismatches and assessment.unresolved
    assert adapt_case(mixed).prediction is None


def test_unexplained_blocking_reason_never_emits_ok():
    case = complete_case()
    assert case.report is not None
    case.report.issues.append("mysterious_legacy_failure")
    assessment = assess_case(case)
    assert assessment.blocking_issues
    decision = adapt_case(case)
    assert decision.prediction is None
    assert summarize_case(case).kind == "needs_review"


def test_selected_pair_uses_own_evidence_unused_becomes_warning():
    case = complete_case()
    case.attachments = [
        AttachmentView(id="si", filename="si.txt", role="SI", evidence=evidence("si")),
        AttachmentView(id="bl", filename="bl.txt", role="BL", evidence=evidence("bl")),
        AttachmentView(
            id="extra",
            filename="extra.txt",
            role="unknown",
            evidence=evidence("extra", ["extra_page_unreadable"]),
        ),
    ]
    assessment = assess_case(case)
    assert assessment.selected_pair == ["si", "bl"]
    assert assessment.unused_warnings == ["extra_page_unreadable"]
    # Selected-pair comparison can still be clear; unused stays visible.
    assert assessment.can_be_clear is True
    assert assessment.needs_review is True
    assert summarize_case(case).kind == "needs_review"


def test_without_selection_handling_stays_conservative():
    case = complete_case()
    case.attachments = [
        AttachmentView(
            id="a", filename="a.txt", role="unknown", evidence=evidence("a", ["a_bad"])
        ),
        AttachmentView(
            id="b", filename="b.txt", role="unknown", evidence=evidence("b", ["b_bad"])
        ),
    ]
    assert case.report is not None
    case.report.pair_valid = False
    assessment = assess_case(case)
    assert assessment.selected_pair is None
    assert set(assessment.blocking_issues) >= {"a_bad", "b_bad"}
