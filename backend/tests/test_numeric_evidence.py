from unittest.mock import Mock

import pytest
from typesafe_sdk import SystemOneResponse

from averis.config import Settings
from averis.domain import DocumentEvidence, EvidenceBlock, Location
from averis.jev import Jev
from averis.numeric_evidence import (
    bind_numeric_selection,
    can_repair,
    numeric_candidates,
)
from averis.verification import reading_from_evidence


def document(text):
    return DocumentEvidence(
        document_id="pdf",
        blocks=[
            EvidenceBlock(id="b1", text=text, locations=[Location(kind="pdf", page=1)])
        ],
    )


def test_joined_fields_copy_exact_spans_and_keep_original_evidence():
    doc = document(
        "Total Containers: 4 x 40'HC\nTOTAL Gross Weightnn (KGS): 117,770 KG"
    )
    choices = numeric_candidates(doc)
    count = bind_numeric_selection(
        doc, "container_count", choices[0].selection, 0.97, "jev"
    )
    weight = bind_numeric_selection(
        doc, "gross_weight_kg", choices[2].selection, 0.89, "jev"
    )
    assert (count.normalized, weight.normalized) == ("4", "117770")
    assert count.issue is weight.issue is None
    assert count.text == weight.text == doc.blocks[0].text
    assert count.provenance == weight.provenance == "machine"
    assert (
        doc.blocks[0].text[count.numeric_selection.start : count.numeric_selection.end]
        == "4"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"start": 1},
        {"end": 999},
        {"block_id": "another-document"},
        {"unit_start": 0, "unit_end": 2},
    ],
)
def test_invalid_or_forged_source_spans_are_rejected(change):
    doc = document("Gross weight: 12345 kg")
    selection = numeric_candidates(doc)[0].selection.model_copy(update=change)
    with pytest.raises(ValueError):
        bind_numeric_selection(doc, "gross_weight_kg", selection, 1, "jev")


@pytest.mark.parametrize(
    "text",
    [
        "Gross weight: 12345",
        "Gross weight: 12345\nNet weight: 12000 kg",
        "Gross weight: 12 tonnes (12000 kg)",
        "Gross weight: 12345 lb",
    ],
)
def test_missing_wrong_row_or_ambiguous_units_cannot_become_kg(text):
    doc = document(text)
    reading = bind_numeric_selection(
        doc, "gross_weight_kg", numeric_candidates(doc)[0].selection, 1, "jev"
    )
    assert reading.normalized is None
    assert reading.issue == "missing_or_ambiguous_value"


def test_low_confidence_preserves_uncertainty():
    doc = document("Gross weight: 12345 kg")
    reading = bind_numeric_selection(
        doc, "gross_weight_kg", numeric_candidates(doc)[0].selection, 0.79, "jev"
    )
    assert reading.issue == "low_field_confidence"


def test_no_new_calls_for_good_low_confidence_ocr_or_non_pdf_readings():
    doc = document("Gross weight: 12345 kg")
    good = reading_from_evidence("gross_weight_kg", doc, ["b1"])
    assert not can_repair(doc, good, 0.8)
    broken = good.model_copy(update={"issue": "missing_or_ambiguous_value"})
    assert can_repair(doc, broken, 0.8)
    assert not can_repair(doc, broken.model_copy(update={"confidence": 0.5}), 0.8)
    doc.blocks[0].method = "ocr"
    assert not can_repair(doc, broken, 0.8)
    assert numeric_candidates(doc) == []
    doc.blocks[0].method = "native"
    doc.blocks[0].locations = [Location(kind="text", line_start=1)]
    assert not can_repair(doc, broken, 0.8)


def test_candidates_are_bounded_and_do_not_read_embedded_or_negative_numbers():
    assert numeric_candidates(document(" ".join(str(i) for i in range(121)))) == []
    assert numeric_candidates(document("ID A123; count -7; gross -12000 kg")) == []


def test_numeric_assistance_preserves_good_fields_and_binds_source(monkeypatch):
    doc = document(
        "Total Containers: 4 x 40'HC\nTOTAL Gross Weightnn (KGS): 117,770 KG"
    )
    count = reading_from_evidence("container_count", doc, ["b1"], 0.99)
    weight = reading_from_evidence("gross_weight_kg", doc, ["b1"], 0.99)
    good = reading_from_evidence("shipper", document("Shipper: Test Co"), ["b1"])
    provider = Jev(Settings(), Mock(), "run", "development")

    def ask(state, questions):
        assert state["blocks"][0]["text"] == doc.blocks[0].text
        answers = {}
        for field, question in questions.items():
            chosen = "V1" if field == "container_count" else "V3"
            answers[field] = {
                "type": "choice",
                "choice": chosen,
                "confidence": 0.9,
                "probabilities": {
                    key: 1 if key == chosen else 0 for key in question.criteria
                },
            }
        return SystemOneResponse.model_validate(
            {
                "model": "jev",
                "answers": answers,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )

    monkeypatch.setattr(provider, "_ask", ask)
    results = provider.repair_numeric(
        doc, {"container_count": count, "gross_weight_kg": weight, "shipper": good}
    )
    assert results["shipper"] is good
    assert results["container_count"].normalized == "4"
    assert results["gross_weight_kg"].normalized == "117770"


def test_optional_provider_failure_preserves_original_uncertainty(monkeypatch):
    doc = document("Containers: 4\nGross Weightnn: 10000 kg")
    reading = reading_from_evidence("container_count", doc, ["b1"])
    provider = Jev(Settings(), Mock(), "run", "development")
    monkeypatch.setattr(
        provider, "_ask", Mock(side_effect=ValueError("invalid response"))
    )
    result = provider.repair_numeric(doc, {"container_count": reading})[
        "container_count"
    ]
    assert result.issue == reading.issue
    assert result.normalized == reading.normalized
    assert result.assistance_error == "numeric_provider_unavailable"


def test_pipeline_rebinds_numeric_spans_instead_of_trusting_provider_values():
    from averis.intelligence import ExtractionResult
    from averis.pipeline import Checkpoints, ShipmentPipeline

    doc = document("Total Containers: 4 x 40HC\nGross Weightnn: 117770 kg")
    reading = bind_numeric_selection(
        doc, "gross_weight_kg", numeric_candidates(doc)[-1].selection, 0.9, "jev"
    )
    reading.normalized = "999999"
    reading.text = "fabricated"
    intelligence = Mock()
    intelligence.extract.return_value = ExtractionResult(
        "BL", 1, {"gross_weight_kg": reading}
    )
    pipeline = ShipmentPipeline(
        intelligence, Checkpoints({}, lambda *_: None), Mock(), Mock(), lambda: 480
    )
    saved = pipeline._extract(doc)
    assert saved.fields["gross_weight_kg"].normalized == "117770"
    assert saved.fields["gross_weight_kg"].text == doc.blocks[0].text
    assert (
        saved.fields["gross_weight_kg"].numeric_selection == reading.numeric_selection
    )
