"""Uncertain intent can request source context without trusting it as field evidence."""

from unittest.mock import Mock

import pytest
from test_case_status import complete_case
from test_filename_classification import answer
from test_intelligence import jev

from averis.domain import (
    AttachmentView,
    Classification,
    DocumentEvidence,
    EvidenceBlock,
    Location,
)
from averis.intelligence import AttachmentPreview, ExtractionResult
from averis.pipeline import Checkpoints, ProcessingInput, ShipmentPipeline


def source(text="Shipping Instruction", *, method="native", confidence=None):
    return DocumentEvidence(
        document_id="doc",
        blocks=[
            EvidenceBlock(
                id="b1",
                text=text,
                locations=[Location(kind="text", line_start=1)],
                method=method,
                ocr_confidence=confidence,
            )
        ],
    )


@pytest.mark.parametrize(
    "category", ["GENERAL", "BL_COMPARISON", "INVOICE_QUERY", "SI_REQUEST", "SPAM"]
)
def test_clear_intent_never_loads_previews(monkeypatch, category):
    client = jev()
    loader = Mock(
        side_effect=AssertionError("Clear classification must not read files")
    )
    monkeypatch.setattr(client, "_ask", lambda *_: answer(category))
    assert (
        client.classify(
            "Update",
            "For information",
            attachment_filenames=("SI.txt",),
            load_attachment_previews=loader,
        ).accepted
        == category
    )
    loader.assert_not_called()


def test_uncertain_filename_answer_loads_context_then_decides(monkeypatch):
    client = jev()
    loader = Mock(
        return_value=(AttachmentPreview("doc.txt", "Shipping Instruction", False),)
    )
    responses = iter(
        [
            answer("GENERAL", 0.96),
            answer("BL_COMPARISON", 0.77),
            answer("BL_COMPARISON", 0.99),
        ]
    )
    calls = []

    def ask(state, questions):
        calls.append(state)
        return next(responses)

    monkeypatch.setattr(client, "_ask", ask)
    result = client.classify(
        "Check",
        "Check before release",
        attachment_filenames=("doc.txt",),
        load_attachment_previews=loader,
    )
    assert result.accepted == "BL_COMPARISON"
    assert result.confidence == 0.99
    loader.assert_called_once_with()
    assert calls[-1]["attachment_previews"] == [
        {"filename": "doc.txt", "text": "Shipping Instruction", "truncated": False}
    ]


@pytest.mark.parametrize("previews", [(), (AttachmentPreview("bad.pdf", "", True),)])
def test_unreadable_context_keeps_uncertainty_instead_of_old_general(
    monkeypatch, previews
):
    client = jev()
    responses = iter([answer("GENERAL", 0.96), answer("BL_COMPARISON", 0.77)])
    monkeypatch.setattr(client, "_ask", lambda *_: next(responses))
    result = client.classify(
        "Check",
        "Please check",
        attachment_filenames=("bad.pdf",),
        load_attachment_previews=lambda: previews,
    )
    assert result.accepted is None
    assert result.suggested == "BL_COMPARISON"
    assert result.confidence == 0.77


def test_uncertain_content_answer_requires_review(monkeypatch):
    client = jev()
    responses = iter(
        [
            answer("GENERAL", 0.96),
            answer("BL_COMPARISON", 0.77),
            answer("BL_COMPARISON", 0.79),
        ]
    )
    monkeypatch.setattr(client, "_ask", lambda *_: next(responses))
    result = client.classify(
        "Check",
        "Please check",
        attachment_filenames=("doc.txt",),
        load_attachment_previews=lambda: (
            AttachmentPreview("doc.txt", "Ambiguous source", True),
        ),
    )
    assert result.accepted is None
    assert result.confidence == 0.79


def test_preview_scope_is_bounded_and_reader_errors_are_not_hidden(monkeypatch):
    client = jev()
    monkeypatch.setattr(client, "_ask", lambda *_: answer("BL_COMPARISON", 0.7))
    loader = Mock(side_effect=TimeoutError("application_deadline"))
    assert (
        client.classify(
            "Check",
            "Please check",
            attachment_filenames=tuple(f"{i}.txt" for i in range(5)),
            load_attachment_previews=loader,
        ).accepted
        is None
    )
    loader.assert_not_called()
    with pytest.raises(TimeoutError, match="application_deadline"):
        client.classify(
            "Check",
            "Please check",
            attachment_filenames=("one.txt",),
            load_attachment_previews=loader,
        )


def test_preview_keeps_exact_bounded_text_and_excludes_unreliable_ocr():
    evidence = source("字" * 2500)
    preview = AttachmentPreview.from_evidence("文档.txt", evidence)
    assert preview.text == "字" * 2000
    assert preview.truncated
    assert evidence.blocks[0].text == "字" * 2500
    assert (
        AttachmentPreview.from_evidence(
            "scan.pdf", source(method="ocr", confidence=0.3)
        ).text
        == ""
    )
    assert (
        AttachmentPreview.from_evidence(
            "scan.pdf", source(method="ocr", confidence=None)
        ).text
        == ""
    )
    assert (
        AttachmentPreview.from_evidence(
            "scan.pdf", source(method="ocr", confidence=0.95)
        ).text
        == "Shipping Instruction"
    )
    evidence.issues = ["unreadable_document"]
    assert AttachmentPreview.from_evidence("bad.pdf", evidence).text == ""


@pytest.mark.parametrize("accepted", ["BL_COMPARISON", "GENERAL", None])
def test_pipeline_reads_once_and_retains_context_for_sources(accepted):
    case = complete_case()
    case.classification = None
    case.attachments = [AttachmentView(id="doc", filename="source.txt")]
    intelligence = Mock()

    def classify(*args, load_attachment_previews, **kwargs):
        assert load_attachment_previews()[0].text == "Shipping Instruction"
        return Classification(
            suggested="BL_COMPARISON" if accepted is None else accepted,
            accepted=accepted,
            confidence=0.7 if accepted is None else 1,
            probabilities={"BL_COMPARISON": 1},
            model="offline",
        )

    intelligence.classify.side_effect = classify
    intelligence.extract.return_value = ExtractionResult("unknown", 1, {})
    read = Mock(return_value=source())
    load = Mock(return_value=b"Shipping Instruction")
    saved = Checkpoints({}, Mock())
    pipeline = ShipmentPipeline(intelligence, saved, load, read, lambda: 400)
    result = pipeline.process(ProcessingInput(case, None, {}))
    assert read.call_count == load.call_count == 1
    assert result.attachments[0].evidence.blocks[0].text == "Shipping Instruction"
    assert case.attachments[0].evidence is None
    assert intelligence.extract.call_count == int(accepted == "BL_COMPARISON")
    if accepted is None:
        assert result.review_reasons == ["Check category"]
    # A completed classification checkpoint avoids any repeated inference or parsing.
    resumed = pipeline.process(ProcessingInput(case, None, {}))
    assert resumed.attachments[0].evidence.blocks[0].text == "Shipping Instruction"
    assert intelligence.classify.call_count == 1
    assert read.call_count == load.call_count == 1
