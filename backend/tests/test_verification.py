from typing import Literal, cast

import pytest
from typesafe_sdk import ChoiceAnswer

from averis.contracts import FIELDS, Field
from averis.domain import DocumentEvidence, EvidenceBlock, Location, Reading
from averis.jev import validate_choice_answer
from averis.verification import (
    compare,
    normalize,
    reading_from_evidence,
    shipment_references,
    source_value,
    validate_pair,
)

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)


def evidence(
    document_id: str,
    text: str,
    *,
    method: Literal["native", "ocr"] = "native",
    ocr_confidence: float | None = None,
) -> DocumentEvidence:
    return DocumentEvidence(
        document_id=document_id,
        blocks=[
            EvidenceBlock(
                id=f"{document_id}:b1",
                text=text,
                locations=[Location(kind="text", line_start=1, line_end=1)],
                method=method,
                ocr_confidence=ocr_confidence,
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
        ("Gross Wt (MT): 1.25 MT", "1250"),
    ],
)
def test_normalize_converts_explicit_weight_units(source: str, expected: str) -> None:
    assert normalize("gross_weight_kg", source) == expected


def test_normalize_defaults_bare_weight_to_kg_and_respects_pounds() -> None:
    assert normalize("gross_weight_kg", "Gross Weight: 243588") == "243588"
    assert normalize("gross_weight_kg", "Gross Weight: 10 pounds") == "4.5359237"


def test_source_value_accepts_safe_label_space_and_total_weight_aliases() -> None:
    assert source_value("shipper", "Shipper Averis Trading") == "Averis Trading"
    assert source_value("shipper", "Shipperton Logistics") == "Shipperton Logistics"
    assert normalize("gross_weight_kg", "TOTAL Gross Wt (kgs) 131,322 KG") == "131322"
    assert (
        normalize("gross_weight_kg", "TOTAL Gross Weight (KG) 131,322 KG") == "131322"
    )
    assert normalize("port_of_loading", "Portof Loading Singapore") == "singapore"
    assert normalize("port_of_discharge", "Portof Discharge Sydney") == "sydney"


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


def test_ocr_quality_is_independent_of_high_model_confidence() -> None:
    low_quality = evidence(
        "low",
        "Shipper Aver1s Trading",
        method="ocr",
        ocr_confidence=0.42,
    )
    unknown_quality = evidence("unknown", "Shipper Averis Trading", method="ocr")
    native = evidence("native", "Shipper Averis Trading")

    low = reading_from_evidence("shipper", low_quality, ["low:b1"], confidence=0.99)
    unknown = reading_from_evidence(
        "shipper", unknown_quality, ["unknown:b1"], confidence=0.99
    )
    native_result = reading_from_evidence(
        "shipper", native, ["native:b1"], confidence=0.99
    )

    assert low.normalized == "aver1s trading"
    assert low.issue == "low_ocr_confidence"
    assert unknown.issue == "unknown_ocr_confidence"
    assert native_result.issue is None


def test_verified_ocr_clears_quality_but_not_mixed_source_fields() -> None:
    clean = evidence(
        "clean",
        "Portof Loading Singapore",
        method="ocr",
        ocr_confidence=0.31,
    )
    mixed = evidence(
        "mixed",
        "Notify Party Pacific Office\nPortof Loading Singapore\nPortof Discharge Sydney",
        method="ocr",
        ocr_confidence=0.99,
    )
    wrong = evidence(
        "wrong",
        "Consignee Meridian LLC",
        method="ocr",
        ocr_confidence=0.99,
    )

    verified = reading_from_evidence(
        "port_of_loading", clean, ["clean:b1"], confidence=0.99, verified=True
    )
    invalid_source = reading_from_evidence(
        "port_of_loading", mixed, ["mixed:b1"], confidence=0.99, verified=True
    )
    wrong_source = reading_from_evidence(
        "shipper", wrong, ["wrong:b1"], confidence=0.99, verified=True
    )

    assert verified.normalized == "singapore"
    assert verified.issue is None
    assert invalid_source.normalized is None
    assert invalid_source.issue == "ambiguous_source_fields"
    assert wrong_source.normalized is None
    assert wrong_source.issue == "source_field_mismatch"


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


@pytest.mark.parametrize("bl_count", ["3", "4"])
def test_organizer_example_flags_only_the_changed_container_count(
    bl_count: str,
) -> None:
    """Equal 22,000 kg weights must not become a second discrepancy."""
    source_values: dict[Field, str] = {
        "shipper": "Shipper: Meridian Paper",
        "consignee": "Consignee: Pacific Distribution",
        "notify_party": "Notify Party: Pacific Distribution",
        "port_of_loading": "Port of Loading: Port Klang",
        "port_of_discharge": "Port of Discharge: Singapore",
        "container_count": "Container Count: 3",
        "gross_weight_kg": "Gross Weight: 22,000 kg",
    }
    draft_values = dict(source_values)
    draft_values["container_count"] = f"Total Containers: {bl_count}"
    draft_values["gross_weight_kg"] = "Gross Weight: 22 MT"
    si = {
        field: reading(field, "si", normalize(field, value))
        for field, value in source_values.items()
    }
    bl = {
        field: reading(field, "bl", normalize(field, value))
        for field, value in draft_values.items()
    }

    report = compare(si, bl, revision=1, pair_valid=True)
    outcomes = {finding.field: finding.outcome for finding in report.findings}

    assert len(outcomes) == 7
    assert outcomes == {
        field: "mismatch" if field == "container_count" and bl_count == "4" else "match"
        for field in source_values
    }
    count = next(f for f in report.findings if f.field == "container_count")
    assert count.si.normalized == "3"
    assert count.bl.normalized == bl_count
    weight = next(f for f in report.findings if f.field == "gross_weight_kg")
    assert weight.si.normalized == weight.bl.normalized == "22000"


def test_invalid_pair_preserves_readings_without_confirming_outcomes() -> None:
    readings = {
        field: reading(field, "doc", f"same-{field}") for field in _TYPED_FIELDS
    }

    report = compare(readings, readings, revision=1, pair_valid=False)

    assert len(report.findings) == 7
    assert all(f.outcome == "unresolved" for f in report.findings)
    assert all(
        f.si == readings[f.field] and f.bl == readings[f.field] for f in report.findings
    )
    assert report.issues == ["pair_requires_review"]


def test_unconfirmed_different_values_do_not_become_confirmed_mismatches() -> None:
    si = {
        field: reading(field, "si", "上海华远贸易有限公司") for field in _TYPED_FIELDS
    }
    bl = {
        field: reading(field, "bl", "广州华盛物流有限公司") for field in _TYPED_FIELDS
    }
    pending = compare(si, bl, revision=1, pair_valid=False)
    assert pending.findings[0].si.text == "上海华远贸易有限公司"
    assert pending.findings[0].bl.text == "广州华盛物流有限公司"
    assert all(f.outcome == "unresolved" for f in pending.findings)
    assert all(f.provisional_outcome == "mismatch" for f in pending.findings)
    confirmed = compare(si, bl, revision=2, pair_valid=True)
    assert all(f.outcome == "mismatch" for f in confirmed.findings)
    assert all(f.provisional_outcome is None for f in confirmed.findings)


def test_human_selection_cannot_override_conflicting_shipment_references() -> None:
    si = evidence("si", "Shipment Reference: SIN-1000")
    bl = evidence("bl", "Shipment Reference: SIN-2000")

    assert validate_pair(si, bl, human_selected=True) is False


def test_booking_ref_and_oc_number_labels_preserve_identifier_values() -> None:
    si = evidence("si", "Booking Ref: BK-12345\nOC No.: ORDER-6789")
    bl = evidence("bl", "Booking Reference: BK-12345")
    assert shipment_references(si) == {"BK-12345", "ORDER-6789"}
    assert validate_pair(si, bl) is True


def test_shared_booking_cannot_hide_conflicting_shipment_ids() -> None:
    si = evidence("si", "Booking Ref: BK-12345\nShipment ID: SHIP-1111")
    bl = evidence("bl", "Booking Ref: BK-12345\nShipment ID: SHIP-2222")
    assert validate_pair(si, bl) is False
    assert validate_pair(si, bl, human_selected=True) is False


def test_different_identifier_kinds_do_not_prove_pairing() -> None:
    si = evidence("si", "Booking Ref: SAME-1234")
    bl = evidence("bl", "OC No.: SAME-1234")
    assert validate_pair(si, bl) is False


def test_structured_table_booking_label_can_match_native_text() -> None:
    si = evidence("si", "Booking No. | BK-12345")
    bl = evidence("bl", "Booking Ref: BK-12345")
    assert validate_pair(si, bl) is True


def test_bare_booking_heading_is_a_reference() -> None:
    si = evidence("si", "Booking: BKG-12345")
    bl = evidence("bl", "Booking No. BKG-12345")
    assert validate_pair(si, bl) is True


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


def test_inline_booking_number_in_a_header_validates_pairing() -> None:
    si = evidence(
        "si",
        "B/L NUMBER: OOLU3584143842 BOOKING NO. PSGSE4981829",
    )
    bl = evidence(
        "bl",
        "DRAFT B/L NUMBER: OOLU3584143842 BOOKING NO PSGSE4981829",
    )

    assert shipment_references(si) == {"PSGSE4981829"}
    assert shipment_references(bl) == {"PSGSE4981829"}
    assert shipment_references(evidence("noise", "Rebooking No. PSGSE4981829")) == set()
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


def test_provisional_comparison_preserves_missing_fields():
    si = {field: reading(field, "si", "same") for field in _TYPED_FIELDS}
    bl = {field: reading(field, "bl", "same") for field in _TYPED_FIELDS}
    bl["container_count"] = reading("container_count", "bl", "different")
    bl["gross_weight_kg"] = reading("gross_weight_kg", "bl", None, "missing_value")
    report = compare(si, bl, revision=1, pair_valid=False)
    outcomes = {f.field: f.provisional_outcome for f in report.findings}
    assert outcomes["shipper"] == "match"
    assert outcomes["container_count"] == "mismatch"
    assert outcomes["gross_weight_kg"] == "unresolved"
    assert all(f.outcome == "unresolved" for f in report.findings)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("216950", "216950"),
        ("Gross Weight: 1,234.50", "1234.5"),
        ("Gross Weight (LBS): 10000", "4535.9237"),
        ("Gross Weight (MT): 1.5", "1500"),
        ("Gross Weight: 1000 g", "1"),
        ("Gross Weight (KG): 10 lbs", None),
        ("Gross Weight (LBS): 10 kg", None),
        ("Gross Weight (oz): 10", None),
        ("Gross Weight (oz): 10 ", None),
        ("Gross Weight: 10 oz", None),
        ("Gross Weight: 10 tons", None),
        ("Gross Weight: 10 containers", None),
        ("Gross Weight: ____MT", None),
        ("Gross Weight:", None),
        ("Gross Weight: 10 / 20", None),
    ],
)
def test_weight_default_and_explicit_unit_boundaries(source, expected):
    assert normalize("gross_weight_kg", source) == expected


def test_weight_assumption_provenance_and_uncertainty():
    doc = evidence("si", "Gross Weight: 10000")
    result = reading_from_evidence("gross_weight_kg", doc, ["si:b1"])
    assert result.normalized == "10000"
    assert result.unit_source == "default_kg"
    assert result.text == "Gross Weight: 10000"
    assert result.issue is None
    uncertain = reading_from_evidence("gross_weight_kg", doc, ["si:b1"], confidence=0.2)
    assert uncertain.issue == "low_field_confidence"
    lbs = evidence("bl", "Gross Weight: 10000 lb")
    other = reading_from_evidence("gross_weight_kg", lbs, ["bl:b1"])
    assert other.unit_source == "explicit"
    si = {f: reading(f, "si", "same") for f in _TYPED_FIELDS}
    bl = {f: reading(f, "bl", "same") for f in _TYPED_FIELDS}
    si["gross_weight_kg"] = result
    bl["gross_weight_kg"] = other
    report = compare(si, bl, 1, True)
    assert (
        next(f for f in report.findings if f.field == "gross_weight_kg").outcome
        == "mismatch"
    )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("10000", "10000", "match"),
        ("10000", "10001", "mismatch"),
        ("10000", "10 MT", "match"),
        ("10000", "10000 lb", "mismatch"),
        ("10000", "N/A", "unresolved"),
        ("10000", "Gross Weight (kg): 10 lb", "unresolved"),
    ],
)
def test_weight_default_comparison_policy(left, right, expected):
    si = {f: reading(f, "si", "same") for f in _TYPED_FIELDS}
    bl = {f: reading(f, "bl", "same") for f in _TYPED_FIELDS}
    for target, name, text in [(si, "si", left), (bl, "bl", right)]:
        doc = evidence(name, text)
        target["gross_weight_kg"] = reading_from_evidence(
            "gross_weight_kg", doc, [name + ":b1"]
        )
    result = compare(si, bl, 1, True)
    assert (
        next(f for f in result.findings if f.field == "gross_weight_kg").outcome
        == expected
    )


def test_default_kg_does_not_clear_weak_ocr():
    doc = evidence("si", "Gross Weight: 10000", method="ocr", ocr_confidence=0.5)
    result = reading_from_evidence("gross_weight_kg", doc, ["si:b1"])
    assert result.normalized == "10000"
    assert result.unit_source == "default_kg"
    assert result.issue == "low_ocr_confidence"
