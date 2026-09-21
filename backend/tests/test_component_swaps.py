"""Implementation swaps must not reuse another component's completed work."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_case_status import complete_case

from averis.config import Settings
from averis.domain import AttachmentView, Classification
from averis.intelligence import ExtractionResult
from averis.jev_prompts import DEFAULT_PROMPTS
from averis.pipeline import Checkpoints, InvalidCheckpoint, ShipmentPipeline
from averis.processing import Processor
from averis.processing_components import RunIntelligence
from averis.processing_setup import application_components
from averis.verification import reading_from_evidence
from tests.test_component_contracts import doc


def pipeline(saved, *, reader_profile=("reader-a", "ocr-a"), extraction="ai-a"):
    intelligence = Mock()
    evidence = doc()
    intelligence.extract.return_value = ExtractionResult(
        "SI", 1, {"shipper": reading_from_evidence("shipper", evidence, ["doc-1:b1"])}
    )
    reader = Mock(return_value=evidence)
    result = ShipmentPipeline(
        intelligence,
        Checkpoints(saved, lambda *_: None),
        lambda _: b"original",
        reader,
        lambda: 400,
        reader_profile=reader_profile,
        extraction_profile=extraction,
    )
    return result, intelligence, reader


@pytest.mark.parametrize("changed", ["reader", "ocr"])
def test_reader_swap_rejects_saved_document_before_inference(changed):
    first, _, _ = pipeline({})
    attachment = AttachmentView(id="doc-1", filename="source.txt")
    first._read(attachment)
    profile = ("reader-b", "ocr-a") if changed == "reader" else ("reader-a", "ocr-b")
    second, intelligence, reader = pipeline(
        first._checkpoints._saved, reader_profile=profile
    )
    with pytest.raises(InvalidCheckpoint, match="reader profile"):
        second._read(attachment)
    reader.assert_not_called()
    intelligence.extract.assert_not_called()


def test_same_binding_reuses_reading_and_extraction_without_calls():
    first, _, _ = pipeline({})
    attachment = AttachmentView(id="doc-1", filename="source.txt")
    evidence = first._read(attachment)
    first._extract(evidence)
    second, intelligence, reader = pipeline(first._checkpoints._saved)
    second._extract(second._read(attachment))
    reader.assert_not_called()
    intelligence.extract.assert_not_called()


def test_provider_swap_rejects_saved_extraction():
    first, _, _ = pipeline({})
    first._extract(doc())
    second, intelligence, _ = pipeline(first._checkpoints._saved, extraction="ai-b")
    with pytest.raises(InvalidCheckpoint, match="provider profile"):
        second._extract(doc())
    intelligence.extract.assert_not_called()


def test_classification_prompt_change_reclassifies_without_erasing_documents():
    saved = Classification(
        suggested="GENERAL",
        accepted="GENERAL",
        confidence=1,
        probabilities={"GENERAL": 1},
        model="same-model",
    )
    checkpoints = Checkpoints(
        {
            "classification": {**saved.model_dump(), "implementation": "old-prompt"},
            "document:original": {"retained": True},
        },
        lambda *_: None,
    )
    ai = Mock()
    ai.classify.return_value = saved.model_copy(
        update={"accepted": "SI_REQUEST", "suggested": "SI_REQUEST"}
    )
    p = ShipmentPipeline(
        ai,
        checkpoints,
        Mock(),
        Mock(),
        lambda: 400,
        classification_identity="new-prompt",
    )
    case = complete_case()
    case.classification = None
    assert p._classify(case, []).accepted == "SI_REQUEST"
    ai.classify.assert_called_once()
    assert checkpoints._saved["document:original"] == {"retained": True}


def test_runtime_model_and_assistance_have_distinct_extraction_identities():
    settings = Settings(_env_file=None, env="test")
    plain = application_components(Mock(), settings)
    model = application_components(
        Mock(), settings.model_copy(update={"jev_model": "other"})
    )
    assisted = application_components(
        Mock(), settings.model_copy(update={"deepseek_fields_enabled": True})
    )
    assert (
        len(
            {
                plain.extraction_profile,
                model.extraction_profile,
                assisted.extraction_profile,
            }
        )
        == 3
    )
    assert plain.reader_profile == model.reader_profile == assisted.reader_profile
    assert plain.classification_identity == assisted.classification_identity
    assert plain.classification_identity != model.classification_identity
    assert (
        replace(plain, pairing_profile="replacement-pairing").pairing_profile
        != plain.pairing_profile
    )


def test_prompt_swap_changes_only_relevant_identities():
    settings = Settings(_env_file=None, env="test")
    original = application_components(Mock(), settings)
    prompts = replace(DEFAULT_PROMPTS, pairing=DEFAULT_PROMPTS.pairing + " New policy.")
    candidate = application_components(Mock(), settings, prompts=prompts)
    assert candidate.pairing_profile != original.pairing_profile
    assert candidate.extraction_profile == original.extraction_profile
    assert candidate.classification_identity == original.classification_identity
    assert candidate.create_intelligence("run", "development").pairing_judge is not None


def test_custom_provider_keeps_its_own_pairing_capability():
    settings = Settings(_env_file=None, env="test")
    intelligence, judge = Mock(), Mock()
    selected = replace(
        application_components(Mock(), settings),
        create_intelligence=lambda *_: RunIntelligence(intelligence, judge),
        extraction_profile="another-provider-v1",
        pairing_profile="another-judge-v1",
    )
    processor = Processor(Mock(), settings, Mock(), components=selected)
    adapters = processor.components.create_intelligence("run", "development")
    assert adapters.intelligence is intelligence
    assert adapters.pairing_judge is judge


def test_production_rejects_unversioned_factory():
    settings = Settings(_env_file=None, env="production")
    with pytest.raises(ValueError, match="versioned components"):
        Processor(Mock(), settings, Mock(), factory=Mock())


def test_registered_format_uses_common_reading_boundary(monkeypatch):
    from averis import documents

    handler = Mock(return_value=doc())
    monkeypatch.setitem(
        documents.FORMAT_READERS, ".example", documents.FormatReader(handler)
    )
    result = documents.read_document("doc-1", "source.example", b"original")
    assert result.blocks[0].text == "Shipper: Test Co"
    assert result.source_sha256 is not None
    handler.assert_called_once_with("doc-1", b"original", ".example")


def test_office_archive_guard_cannot_be_skipped_by_handler(monkeypatch):
    from averis import documents

    handler = Mock()
    monkeypatch.setitem(
        documents.FORMAT_READERS,
        ".docx",
        documents.FormatReader(handler, office_archive=True),
    )
    result = documents.read_document("doc-1", "source.docx", b"invalid ZIP")
    assert result.issues
    handler.assert_not_called()
