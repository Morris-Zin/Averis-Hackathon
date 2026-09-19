from typing import Literal, cast

import pytest
from typesafe_sdk import ChoiceAnswer

from averis.contracts import FIELDS, Field
from averis.domain import DocumentEvidence, EvidenceBlock, Location, Reading
from averis.intelligence import validate_choice_answer
from averis.verification import (
    compare,
    normalize,
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
            )
        ],
    )


def reading(
    field: Field,
    document_id: str,
    normalized: str | None,
    issue: str | None = None,
) -> Reading:
    return Reading(
        field=field,
        document_id=document_id,
        text=normalized,
        normalized=normalized,
        confidence=1,
        issue=issue,
    )


def test_normalize_handles_official_container_labels_and_equipment_suffixes() -> None:
    assert normalize("container_count", "No. of Containers: 3 x 40'HC") == "3"
    assert (
        normalize("container_count", "No. of Containers or Packages: 12 x 20'FCL")
        == "12"
    )
    assert normalize("container_count", "Container Count: 1 container") == "1"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Gross Weight (KG): 1,250 KG", "1250"),
        ("Gross Weight毛重(KGS): 67,311 KG", "67311"),
        ("Gross Wt (kgs): 1.25 MT", "1250"),
    ],
)
def test_normalize_converts_explicit_weight_units(source: str, expected: str) -> None:
    assert normalize("gross_weight_kg", source) == expected


def test_normalize_does_not_guess_units_for_a_bare_weight() -> None:
    assert normalize("gross_weight_kg", "Gross Weight: 243588") is None
    assert normalize("gross_weight_kg", "Gross Weight: 10 pounds") is None


def test_reading_retains_multiline_source_and_marks_low_confidence() -> None:
    document = evidence(
        "si",
        "Shipper: Averis Trading\n77 Robinson Road\nSingapore 068896",
    )

    result = reading_from_evidence(
        "shipper", document, ["si:b1"], confidence=0.7, threshold=0.8
    )

    assert result.text == (
        "Shipper: Averis Trading\n77 Robinson Road\nSingapore 068896"
    )
    assert result.normalized == "averis trading 77 robinson road singapore 068896"
    assert result.evidence_ids == ["si:b1"]
    assert result.issue == "low_field_confidence"


def test_ocr_transcription_requires_verification_before_comparison() -> None:
    document = evidence("scan", "Sh1pper: Aver1s", method="ocr")

    result = reading_from_evidence(
        "shipper", document, ["scan:b1"], transcription="Shipper: Averis"
    )
    verified = reading_from_evidence(
        "shipper",
        document,
        ["scan:b1"],
        transcription="Shipper: Averis",
        verified=True,
    )

    assert result.provenance == "human_transcribed"
    assert result.issue == "unverified_transcription"
    assert verified.provenance == "human_verified"
    assert verified.issue is None


def test_native_evidence_cannot_be_replaced_by_an_ocr_transcription() -> None:
    document = evidence("native", "Shipper: Averis")

    with pytest.raises(ValueError, match="only for OCR evidence"):
        reading_from_evidence(
            "shipper", document, ["native:b1"], transcription="Different value"
        )


def test_compare_preserves_mismatch_beside_an_unresolved_field() -> None:
    si = {field: reading(field, "si", f"same-{field}") for field in _TYPED_FIELDS}
    bl = {field: reading(field, "bl", f"same-{field}") for field in _TYPED_FIELDS}
    bl["consignee"] = reading("consignee", "bl", "different-consignee")
    bl["gross_weight_kg"] = reading("gross_weight_kg", "bl", None, "missing_value")

    report = compare(si, bl, revision=4, pair_valid=True)
    outcomes = {finding.field: finding.outcome for finding in report.findings}

    assert outcomes["consignee"] == "mismatch"
    assert outcomes["gross_weight_kg"] == "unresolved"
    assert len(report.findings) == 7


def test_invalid_pair_never_emits_partial_findings() -> None:
    readings = {
        field: reading(field, "doc", f"same-{field}") for field in _TYPED_FIELDS
    }

    report = compare(readings, readings, revision=1, pair_valid=False)

    assert report.findings == []
    assert report.issues == ["pair_requires_review"]


def test_human_selection_cannot_override_conflicting_shipment_references() -> None:
    si = evidence("si", "Booking No.: SIN-1000")
    bl = evidence("bl", "Shipment Reference: SIN-2000")

    assert validate_pair(si, bl, human_selected=True) is False


def test_human_selection_can_pair_distinct_documents_without_references() -> None:
    si = evidence("si", "Shipping Instruction")
    bl = evidence("bl", "Bill of Lading")

    assert validate_pair(si, bl, human_selected=True) is True


def test_zero_values_remain_known_while_missing_markers_are_unresolved() -> None:
    assert normalize("container_count", "Container Count: 0 containers") == "0"
    assert normalize("gross_weight_kg", "Gross Weight: 0 kg") == "0"
    assert normalize("container_count", "Container Count: -") is None
    assert normalize("gross_weight_kg", "Gross Weight: not provided") is None


def test_docx_pipe_delimiter_preserves_the_same_multiline_value() -> None:
    expected = "averis trading 77 robinson road"
    assert (
        normalize("shipper", "Shipper | Averis Trading\n77 Robinson Road") == expected
    )
    assert normalize("shipper", "Shipper: Averis Trading\n77 Robinson Road") == expected


@pytest.mark.parametrize(
    ("field", "source", "expected"),
    [
        ("shipper", "Shipper/Exporter (发货人) | Averis Trading", "averis trading"),
        ("consignee", "To the Order of (收货人) | Meridian LLC", "meridian llc"),
        (
            "notify_party",
            "Notify Party/Intermediate Consignee (通知人) | Nagappa Exports",
            "nagappa exports",
        ),
    ],
)
def test_supplied_docx_label_variants_are_removed(
    field: Field,
    source: str,
    expected: str,
) -> None:
    assert normalize(field, source) == expected


def test_document_word_cannot_be_misread_as_an_oc_reference() -> None:
    si = evidence("si", "Document: Shipping Instruction")
    bl = evidence("bl", "Document: Draft Bill of Lading")

    assert shipment_references(si) == set()
    assert shipment_references(bl) == set()
    assert validate_pair(si, bl) is False


def test_standalone_oc_labels_still_validate_a_pair() -> None:
    si = evidence("si", "OC: SIN-1000")
    bl = evidence("bl", "OC SIN-1000")

    assert shipment_references(si) == {"SIN-1000"}
    assert shipment_references(bl) == {"SIN-1000"}
    assert validate_pair(si, bl) is True


def test_choice_validation_accepts_complete_finite_distribution() -> None:
    answer = ChoiceAnswer(
        type="choice",
        choice="GENERAL",
        confidence=0.9,
        probabilities={"GENERAL": 0.9, "SPAM": 0.1},
    )

    choice, confidence, probabilities = validate_choice_answer(
        answer, frozenset({"GENERAL", "SPAM"})
    )

    assert choice == "GENERAL"
    assert confidence == 0.9
    assert probabilities == {"GENERAL": 0.9, "SPAM": 0.1}


@pytest.mark.parametrize(
    "answer",
    [
        ChoiceAnswer(
            type="choice",
            choice="UNKNOWN",
            confidence=0.9,
            probabilities={"GENERAL": 0.9, "SPAM": 0.1},
        ),
        ChoiceAnswer(
            type="choice",
            choice="GENERAL",
            confidence=float("nan"),
            probabilities={"GENERAL": 0.9, "SPAM": 0.1},
        ),
        ChoiceAnswer(
            type="choice",
            choice="GENERAL",
            confidence=0.9,
            probabilities={"GENERAL": 1.0},
        ),
        ChoiceAnswer(
            type="choice",
            choice="GENERAL",
            confidence=0.9,
            probabilities={"GENERAL": 0.4, "SPAM": 0.4},
        ),
        ChoiceAnswer(
            type="choice",
            choice="GENERAL",
            confidence=0.9,
            probabilities={"GENERAL": 0.4, "SPAM": 0.6},
        ),
    ],
)
def test_choice_validation_rejects_malformed_or_unknown_answers(
    answer: ChoiceAnswer,
) -> None:
    with pytest.raises(ValueError):
        validate_choice_answer(answer, frozenset({"GENERAL", "SPAM"}))
