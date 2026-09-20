"""Focused regressions for source-bound verification and reviewer corrections."""

from typing import Literal, cast

import pytest

from averis.contracts import FIELDS, Field
from averis.domain import (
    AttachmentView,
    CaseView,
    Classification,
    CorrectAction,
    DocumentEvidence,
    EvidenceBlock,
    Location,
    Reading,
)
from averis.review import review_case
from averis.verification import (
    compare,
    reading_from_evidence,
    shipment_references,
    validate_pair,
)

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)


def evidence(
    document_id: str,
    text: str,
    *,
    method: Literal["native", "ocr"] = "native",
) -> DocumentEvidence:
    return DocumentEvidence(
        document_id=document_id,
        blocks=[
            EvidenceBlock(
                id=f"{document_id}:b1",
                text=text,
                locations=[Location(kind="text", line_start=1, line_end=1)],
                method=method,
                ocr_confidence=0.99 if method == "ocr" else None,
            )
        ],
    )


def reading(field: Field, document_id: str, value: str) -> Reading:
    return Reading(
        field=field,
        document_id=document_id,
        text=value,
        normalized=value,
        confidence=1,
    )


def comparison_case(*, bl_evidence: DocumentEvidence) -> CaseView:
    si = {field: reading(field, "si", f"same-{field}") for field in _TYPED_FIELDS}
    bl = {field: reading(field, "bl", f"same-{field}") for field in _TYPED_FIELDS}
    return CaseView(
        id="case-1",
        subject="Review shipment",
        sender="operator@example.test",
        body="Check the attached documents",
        received_at="2026-09-20T00:00:00+00:00",
        revision=1,
        input_revision=1,
        classification=Classification(
            suggested="BL_COMPARISON",
            confidence=1,
            probabilities={"BL_COMPARISON": 1},
            accepted="BL_COMPARISON",
            source="human",
            model="fixture",
        ),
        processing="completed",
        stage="complete",
        workflow="open",
        assignee="Unassigned",
        review_reasons=[],
        attachments=[
            AttachmentView(id="si", filename="si.txt", role="SI"),
            AttachmentView(
                id="bl",
                filename="bl.png",
                role="BL",
                evidence=bl_evidence,
            ),
        ],
        report=compare(si, bl, revision=1, pair_valid=True),
        history=[],
    )


def test_reference_extraction_stays_on_its_label_line() -> None:
    document = evidence(
        "si",
        "Booking Reference:\nShipper: Averis Trading\nShipment ID: SHIP-1234",
    )

    assert shipment_references(document) == {"SHIP-1234"}


@pytest.mark.parametrize("separator", [",", ".", "|", ")"])
def test_punctuated_conflicting_references_still_block_human_pairing(
    separator: str,
) -> None:
    si = evidence("si", f"Shipment ID: SHIP-1111{separator}")
    bl = evidence("bl", f"Shipment ID: SHIP-2222{separator}")

    assert validate_pair(si, bl, human_selected=True) is False


def test_duplicate_evidence_ids_do_not_duplicate_source_text() -> None:
    document = evidence("si", "Shipper: Averis Trading")

    result = reading_from_evidence("shipper", document, ["si:b1", "si:b1"])

    assert result.evidence_ids == ["si:b1"]
    assert result.normalized == "averis trading"


def test_ocr_correction_requires_explicit_original_verification() -> None:
    view = comparison_case(bl_evidence=evidence("bl", "Shipper: Averis", method="ocr"))

    with pytest.raises(ValueError, match="Verify OCR evidence"):
        review_case(
            view,
            CorrectAction(
                expected_revision=1,
                document_id="bl",
                field="shipper",
                evidence_ids=["bl:b1"],
                reason="Use the selected source",
            ),
            controlled=False,
        )


def test_correction_preserves_both_sides_of_unresolved_reason() -> None:
    view = comparison_case(bl_evidence=evidence("bl", "Shipper: Averis Trading"))
    assert view.report is not None
    unresolved = next(
        finding
        for finding in view.report.findings
        if finding.field == "gross_weight_kg"
    )
    unresolved.si.issue = "missing_value"
    unresolved.si.normalized = None
    unresolved.bl.issue = "low_field_confidence"
    unresolved.bl.normalized = None
    unresolved.outcome = "unresolved"

    decision = review_case(
        view,
        CorrectAction(
            expected_revision=1,
            document_id="bl",
            field="shipper",
            evidence_ids=["bl:b1"],
            reason="Confirm the native reading",
        ),
        controlled=False,
    )

    assert decision.view.review_reasons == ["low_field_confidence", "missing_value"]


def test_correction_completes_a_superseded_pending_retry() -> None:
    view = comparison_case(bl_evidence=evidence("bl", "Shipper: Averis Trading"))
    view.processing = "queued"
    view.stage = "retry_requested"
    view.processing_error = "Earlier run failed"

    decision = review_case(
        view,
        CorrectAction(
            expected_revision=1,
            document_id="bl",
            field="shipper",
            evidence_ids=["bl:b1"],
            reason="Confirm the native reading",
        ),
        controlled=False,
    )

    assert decision.needs_processing is False
    assert decision.view.processing == "completed"
    assert decision.view.stage == "reading_corrected"
    assert decision.view.processing_error is None


def test_correction_cannot_complete_a_stale_report() -> None:
    view = comparison_case(bl_evidence=evidence("bl", "Shipper: Averis Trading"))
    view.processing = "queued"
    assert view.report is not None
    view.report.input_revision = view.input_revision - 1

    with pytest.raises(ValueError, match="current valid comparison"):
        review_case(
            view,
            CorrectAction(
                expected_revision=1,
                document_id="bl",
                field="shipper",
                evidence_ids=["bl:b1"],
                reason="Attempt correction from a stale report",
            ),
            controlled=False,
        )

    assert view.processing == "queued"
