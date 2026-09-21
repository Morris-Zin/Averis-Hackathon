from typing import Literal, cast

import pytest

from averis.contracts import FIELDS, Category, Field
from averis.domain import (
    AttachmentView,
    AuditEntry,
    CaseView,
    Classification,
    DocumentEvidence,
    EvidenceBlock,
    Finding,
    Location,
    Reading,
    Report,
)
from averis.exporting import ExportBlocked, adapt_case, export_submission

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)


def document(document_id: str) -> DocumentEvidence:
    return DocumentEvidence(
        document_id=document_id,
        blocks=[
            EvidenceBlock(
                id=f"{document_id}:b1",
                text="Shipping document",
                locations=[Location(kind="text", line_start=1, line_end=1)],
            )
        ],
    )


def classification(
    category: Category = "BL_COMPARISON",
    source: Literal["model", "human", "fixture"] = "model",
) -> Classification:
    return Classification(
        suggested=category,
        accepted=category,
        confidence=1,
        probabilities={category: 1},
        source=source,
        model="test-model",
    )


def case_view(
    *,
    case_id: str = "email_001",
    category: Category = "BL_COMPARISON",
    report: Report | None = None,
    attachments: list[AttachmentView] | None = None,
    source: Literal["model", "human", "fixture"] = "model",
    processing: Literal["queued", "running", "completed", "failed"] = "completed",
    history: list[AuditEntry] | None = None,
) -> CaseView:
    if attachments is None:
        attachments = [
            AttachmentView(
                id="si", filename="si.txt", role="SI", evidence=document("si")
            ),
            AttachmentView(
                id="bl", filename="bl.txt", role="BL", evidence=document("bl")
            ),
        ]
    return CaseView(
        id=case_id,
        subject="Test",
        sender="operator@example.test",
        body="Test",
        received_at="2026-09-19T00:00:00+08:00",
        revision=1,
        input_revision=1,
        classification=classification(category, source),
        processing=processing,
        stage="complete",
        workflow="open",
        assignee="Unassigned",
        review_reasons=[],
        attachments=attachments,
        report=report,
        history=history or [],
    )


def comparison_report(
    *,
    mismatch: set[Field] | None = None,
    unresolved: set[Field] | None = None,
    unresolved_issue: str = "missing_value",
    revision: int = 1,
) -> Report:
    mismatch = mismatch or set()
    unresolved = unresolved or set()
    findings: list[Finding] = []
    for field in _TYPED_FIELDS:
        si = Reading(
            field=field,
            document_id="si",
            normalized=f"same-{field}",
            confidence=1,
        )
        if field in unresolved:
            bl = Reading(
                field=field,
                document_id="bl",
                normalized=None,
                confidence=0.5,
                issue=unresolved_issue,
            )
            outcome: Literal["match", "mismatch", "unresolved"] = "unresolved"
        elif field in mismatch:
            bl = Reading(
                field=field,
                document_id="bl",
                normalized=f"different-{field}",
                confidence=1,
            )
            outcome = "mismatch"
        else:
            bl = Reading(
                field=field,
                document_id="bl",
                normalized=f"same-{field}",
                confidence=1,
            )
            outcome = "match"
        findings.append(
            Finding(
                field=field,
                si=si,
                bl=bl,
                outcome=outcome,
            )
        )
    return Report(
        input_revision=revision,
        pair_valid=True,
        findings=findings,
    )


def test_non_comparison_exports_only_the_unchanged_official_fields() -> None:
    case = case_view(category="GENERAL", report=None, attachments=[])

    exported = export_submission([case], [case.id])
    payload = exported.official_payload()

    assert payload == {
        "email_001": {
            "category": "GENERAL",
            "status": "OK",
            "review_reason": None,
            "has_defect": False,
            "defect_fields": [],
        }
    }
    assert set(payload["email_001"]) == {
        "category",
        "status",
        "review_reason",
        "has_defect",
        "defect_fields",
    }


def test_resolved_mismatch_exports_fields_in_official_order() -> None:
    report = comparison_report(mismatch={"consignee", "gross_weight_kg"})

    decision = adapt_case(case_view(report=report))

    assert decision.prediction is not None
    assert decision.prediction.status == "MISMATCH"
    assert decision.prediction.has_defect is True
    assert decision.prediction.defect_fields == ["consignee", "gross_weight_kg"]
    assert decision.diagnostics.blockers == []


def test_missing_attachment_maps_to_representable_needs_review() -> None:
    decision = adapt_case(case_view(report=None, attachments=[]))

    assert decision.prediction is not None
    assert decision.prediction.status == "NEEDS_REVIEW"
    assert decision.prediction.review_reason == "missing_attachment"
    assert decision.prediction.has_defect is False
    assert decision.prediction.defect_fields == []


def test_missing_field_maps_to_needs_review_without_fabricating_a_match() -> None:
    report = comparison_report(unresolved={"gross_weight_kg"})

    decision = adapt_case(case_view(report=report))

    assert decision.prediction is not None
    assert decision.prediction.status == "NEEDS_REVIEW"
    assert decision.prediction.review_reason == "missing_value"


def test_missing_field_preserves_known_findings_in_review_sidecar() -> None:
    report = comparison_report(mismatch={"consignee"}, unresolved={"gross_weight_kg"})

    decision = adapt_case(case_view(report=report))

    assert decision.prediction is not None
    assert decision.prediction.status == "NEEDS_REVIEW"
    assert decision.prediction.review_reason == "missing_value"
    assert decision.prediction.defect_fields == []
    assert decision.diagnostics.known_mismatches == ["consignee"]
    assert decision.diagnostics.unresolved_fields == ["gross_weight_kg"]


@pytest.mark.parametrize(
    "issue", ["low_field_confidence", "low_ocr_confidence", "provider_disagreement"]
)
def test_known_mismatch_survives_unrelated_selection_uncertainty(issue: str) -> None:
    from averis.case_status import assess_case

    case = case_view(
        report=comparison_report(
            mismatch={"container_count"},
            unresolved={"gross_weight_kg"},
            unresolved_issue=issue,
        )
    )
    case.review_reasons = ["Some fields need review"]
    before = case.model_dump(mode="json")
    exported = export_submission([case], [case.id])
    official = exported.official_payload()[case.id]
    assert official["status"] == "MISMATCH"
    assert official["defect_fields"] == ["container_count"]
    assert set(official) == {
        "category",
        "status",
        "review_reason",
        "has_defect",
        "defect_fields",
    }
    diagnostic = exported.diagnostics[case.id]
    assert diagnostic.known_mismatches == ["container_count"]
    assert diagnostic.unresolved_fields == ["gross_weight_kg"]
    assert diagnostic.review_reasons == ["Some fields need review"]
    assert case.model_dump(mode="json") == before
    assert assess_case(case).needs_review
    assert not assess_case(case).can_be_clear


@pytest.mark.parametrize("issue", ["unknown_failure", "ambiguous_source_fields"])
def test_unrecognized_field_problem_does_not_gain_mismatch_export(issue: str) -> None:
    case = case_view(
        report=comparison_report(
            mismatch={"container_count"},
            unresolved={"gross_weight_kg"},
            unresolved_issue=issue,
        )
    )
    decision = adapt_case(case)
    assert decision.prediction is None
    assert decision.diagnostics.blockers == ["mixed_outcomes_unrepresentable"]
    assert decision.diagnostics.known_mismatches == ["container_count"]


@pytest.mark.parametrize("location", ["document", "report", "case"])
def test_document_wide_problem_still_blocks_mixed_mismatch_export(
    location: str,
) -> None:
    report = comparison_report(
        mismatch={"consignee"},
        unresolved={"gross_weight_kg"},
        unresolved_issue="low_field_confidence",
    )
    case = case_view(report=report)
    if location == "document":
        assert case.attachments[0].evidence is not None
        case.attachments[0].evidence.issues.append("docx_hidden_text_requires_review")
    elif location == "report":
        report.issues.append("shipment_reference_conflict")
    else:
        case.review_reasons.append("unexpected_processing_problem")
    decision = adapt_case(case)
    assert decision.prediction is None
    assert decision.diagnostics.blockers == ["mixed_outcomes_unrepresentable"]


@pytest.mark.parametrize("invalid", ["pair", "revision", "duplicate"])
def test_invalid_report_never_exports_known_mismatches(invalid: str) -> None:
    report = comparison_report(mismatch={"consignee"}, unresolved={"gross_weight_kg"})
    if invalid == "pair":
        report.pair_valid = False
    elif invalid == "revision":
        report.input_revision = 0
    else:
        report.findings[-1] = report.findings[0]
    decision = adapt_case(case_view(report=report))
    assert decision.prediction is None
    assert decision.diagnostics.known_mismatches == []


def test_low_confidence_unknown_is_not_relabelled_as_an_official_reason() -> None:
    report = comparison_report(
        unresolved={"gross_weight_kg"}, unresolved_issue="low_field_confidence"
    )

    decision = adapt_case(case_view(report=report))

    assert decision.prediction is None
    assert decision.diagnostics.blockers == ["review_reason_unrepresentable"]


def test_stale_report_is_blocked_instead_of_exported() -> None:
    report = comparison_report(revision=0)

    decision = adapt_case(case_view(report=report))

    assert decision.prediction is None
    assert decision.diagnostics.blockers == ["comparison_missing"]


def test_superseded_document_issues_do_not_block_current_report() -> None:
    attachments = [
        AttachmentView(
            id="old-bl",
            filename="old.pdf",
            role="unknown",
            evidence=DocumentEvidence(
                document_id="old-bl",
                issues=["document_unreadable:PdfminerException"],
            ),
            superseded=True,
        ),
        AttachmentView(id="si", filename="si.txt", role="SI", evidence=document("si")),
        AttachmentView(id="bl", filename="bl.txt", role="BL", evidence=document("bl")),
    ]

    decision = adapt_case(
        case_view(report=comparison_report(), attachments=attachments)
    )

    assert decision.prediction is not None
    assert decision.prediction.status == "OK"
    assert decision.diagnostics.blockers == []


def test_reviewer_assistance_stays_in_external_diagnostics() -> None:
    report = comparison_report(mismatch={"consignee"})
    report.findings[1].bl.provenance = "human_verified"
    case = case_view(
        report=report,
        source="human",
        history=[
            AuditEntry(
                at="2026-09-19T01:00:00+08:00",
                actor="John Tan",
                action="correct",
                detail="Verified consignee against source",
            )
        ],
    )

    exported = export_submission([case], [case.id])
    official = exported.official_payload()
    diagnostic = exported.diagnostics_payload()[case.id]

    assert "reviewer_assisted" not in official[case.id]
    assert diagnostic["reviewer_assisted"] is True
    assert diagnostic["reviewer_actions"] == ["category", "correct"]


def test_incomplete_id_set_blocks_payload_without_placeholder_rows() -> None:
    case = case_view(category="GENERAL", report=None, attachments=[])
    exported = export_submission([case], [case.id, "email_002"])

    assert "email_002" not in exported.predictions
    assert exported.global_blockers == ["missing_expected_case:email_002"]
    with pytest.raises(ExportBlocked, match="missing_expected_case:email_002"):
        exported.official_payload()


def test_processing_state_must_be_final_before_export() -> None:
    decision = adapt_case(case_view(processing="running"))

    assert decision.prediction is None
    assert decision.diagnostics.blockers == ["processing_incomplete"]


def test_export_command_writes_blockers_without_fake_submission(tmp_path):
    import json

    from averis.cli import export_cases

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for identifier in ("email_001", "email_002"):
        (inbox / f"{identifier}.json").write_text(
            json.dumps(
                {
                    "email_id": identifier,
                    "from": "test@example.test",
                    "subject": "Test",
                    "body": "",
                    "attachments": [],
                }
            )
        )
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "email_001": case_view(
                    case_id="application-uuid", category="GENERAL"
                ).model_dump(mode="json")
            }
        )
    )
    submission = tmp_path / "submission.json"
    diagnostic = tmp_path / "diagnostic.json"
    assert not export_cases(snapshot, submission, diagnostic, tmp_path)
    assert not submission.exists()
    result = json.loads(diagnostic.read_text())
    assert result["automatic_coverage"] == 0.5
    assert result["abstentions"] == 1
    assert result["global_blockers"] == ["missing_expected_case:email_002"]


def test_export_command_keeps_official_payload_separate(tmp_path):
    import json

    from averis.cli import export_cases

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "email_001.json").write_text(
        json.dumps(
            {
                "email_id": "email_001",
                "from": "test@example.test",
                "subject": "Test",
                "body": "",
                "attachments": [],
            }
        )
    )
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "email_001": case_view(
                    case_id="application-uuid", category="GENERAL"
                ).model_dump(mode="json")
            }
        )
    )
    submission = tmp_path / "submission.json"
    diagnostic = tmp_path / "diagnostic.json"
    assert export_cases(snapshot, submission, diagnostic, tmp_path)
    assert set(json.loads(submission.read_text())) == {"email_001"}
    with pytest.raises(ValueError, match="never overwritten"):
        export_cases(snapshot, submission, diagnostic, tmp_path)


def test_illustrative_demo_is_never_scored_as_automatic_inference():
    decision = adapt_case(case_view(category="GENERAL", source="fixture"))
    assert decision.prediction is None
    assert decision.diagnostics.blockers == ["illustrative_demo"]


def test_unaccepted_pair_is_not_fabricated_as_wrong_document_type():
    report = comparison_report()
    report.pair_valid = False
    decision = adapt_case(case_view(report=report))
    assert decision.prediction is None
    assert decision.diagnostics.blockers == ["pairing_unresolved"]
