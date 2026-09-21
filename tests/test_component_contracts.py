"""Replaceable inference and reader contracts with deterministic doubles."""

import pytest
from test_case_status import complete_case
from typesafe_sdk import ChoiceAnswer

from averis.documents import SUPPORTED_FORMATS, validate_document_evidence
from averis.domain import (
    DocumentEvidence,
    EvidenceBlock,
    Location,
    evidence_fingerprint,
)
from averis.intelligence import (
    ExtractionResult,
    validate_choice_answer,
    validate_extraction_proposal,
)
from averis.pipeline import Checkpoints, ShipmentPipeline
from averis.verification import reading_from_evidence


def doc(doc_id: str = "doc-1") -> DocumentEvidence:
    return DocumentEvidence(
        document_id=doc_id,
        blocks=[
            EvidenceBlock(
                id=f"{doc_id}:b1",
                text="Shipper: Test Co",
                locations=[Location(kind="text", line_start=1, line_end=1)],
            )
        ],
    )


def answer(choice: str, conf: float, probs: dict[str, float]) -> ChoiceAnswer:
    return ChoiceAnswer(
        type="choice", choice=choice, confidence=conf, probabilities=probs
    )


def test_fake_provider_cannot_inject_trusted_values_or_invalid_refs():
    document = doc()
    # Valid proposal with explicit abstention becomes unresolved, not a match.
    validated = validate_extraction_proposal(
        document.document_id,
        {
            f: ("NONE", 0.9)
            for f in (
                "shipper",
                "consignee",
                "notify_party",
                "port_of_loading",
                "port_of_discharge",
                "container_count",
                "gross_weight_kg",
            )
        },
        frozenset({"doc-1:b1", "NONE"}),
    )
    assert validated["shipper"][0] == "NONE"
    reading = reading_from_evidence("shipper", document, [], confidence=0.9)
    assert reading.normalized is None
    assert reading.issue is not None

    with pytest.raises(ValueError, match="Invalid evidence reference"):
        validate_extraction_proposal(
            document.document_id,
            {
                f: ("evil:b9", 0.9)
                for f in (
                    "shipper",
                    "consignee",
                    "notify_party",
                    "port_of_loading",
                    "port_of_discharge",
                    "container_count",
                    "gross_weight_kg",
                )
            },
            frozenset({"doc-1:b1", "NONE"}),
        )
    with pytest.raises(ValueError, match="exactly the seven"):
        validate_extraction_proposal(
            document.document_id,
            {"shipper": ("doc-1:b1", 0.9)},
            frozenset({"doc-1:b1"}),
        )


def test_explicit_abstention_differs_from_malformed_output():
    good = answer("a", 0.8, {"a": 0.8, "b": 0.2})
    assert validate_choice_answer(good, frozenset({"a", "b"}))[0] == "a"
    bad = answer("a", 0.8, {"a": 0.2, "b": 0.8})
    # Highest-probability check fails: malformed, not abstention.
    with pytest.raises(ValueError, match="highest-probability"):
        validate_choice_answer(bad, frozenset({"a", "b"}))


def test_alternate_reader_works_without_pipeline_branches():
    seen: list[str] = []

    def fake_reader(
        document_id: str, filename: str, content: bytes, *, timeout_seconds: float
    ) -> DocumentEvidence:
        seen.append(filename)
        assert timeout_seconds > 0
        return doc(document_id)

    class FakeIntelligence:
        def classify(
            self, subject: str, body: str, *, attachment_filenames: tuple[str, ...] = ()
        ):
            from averis.domain import Classification

            return Classification(
                suggested="BL_COMPARISON",
                accepted="BL_COMPARISON",
                confidence=1,
                probabilities={"BL_COMPARISON": 1},
                source="fixture",
                model="test-double",
            )

        def extract(self, document: DocumentEvidence) -> ExtractionResult:
            role = "SI" if document.document_id == "si-1" else "BL"
            return ExtractionResult(
                role=role,
                role_confidence=1,
                fields={
                    f: reading_from_evidence(
                        f, document, [f"{document.document_id}:b1"]
                    )
                    for f in (
                        "shipper",
                        "consignee",
                        "notify_party",
                        "port_of_loading",
                        "port_of_discharge",
                        "container_count",
                        "gross_weight_kg",
                    )
                },
            )

    from averis.domain import AttachmentView, Classification
    from averis.pipeline import ProcessingInput

    view = complete_case()
    view.attachments = [
        AttachmentView(id="si-1", filename="si.txt"),
        AttachmentView(id="bl-1", filename="bl.txt"),
    ]
    view.classification = Classification(
        suggested="BL_COMPARISON",
        accepted="BL_COMPARISON",
        confidence=1,
        probabilities={"BL_COMPARISON": 1},
        source="human",
        model="test",
    )
    pipeline = ShipmentPipeline(
        FakeIntelligence(),  # type: ignore[arg-type]
        Checkpoints({}, lambda *_: None),
        lambda doc_id: b"content",
        fake_reader,
        lambda: 400,
    )
    result = pipeline.process(ProcessingInput(view, None, {}))
    assert seen == ["si.txt", "bl.txt"]
    assert result.report is not None


def test_reader_contract_validates_identity_and_locations():
    assert SUPPORTED_FORMATS[".pdf"]["preview"] is True
    assert SUPPORTED_FORMATS[".docx"]["preview"] is False
    bad = DocumentEvidence(document_id="", blocks=[])
    assert "missing_document_identity" in validate_document_evidence(bad)
    dup = doc()
    dup.blocks.append(dup.blocks[0].model_copy(deep=True))
    assert any(
        p.startswith("duplicate_evidence_id") for p in validate_document_evidence(dup)
    )
    assert evidence_fingerprint(doc()) == evidence_fingerprint(doc())
