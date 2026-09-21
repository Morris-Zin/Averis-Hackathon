"""Names can clarify intent, but never replace source evidence or human decisions."""

from typing import get_args

import pytest
from test_intelligence import category_answer, jev, response

from averis.contracts import Category


def answer(category: str, confidence: float = 1):
    return response(
        {
            "category": category_answer(
                category,
                confidence,
                {
                    key: confidence if key == category else (1 - confidence) / 4
                    for key in get_args(Category)
                },
            )
        }
    )


@pytest.mark.parametrize(
    "category", ["BL_COMPARISON", "INVOICE_QUERY", "SI_REQUEST", "SPAM"]
)
def test_specific_accepted_intent_does_not_make_an_extra_call(monkeypatch, category):
    client = jev()
    calls = []

    def ask(state, questions):
        calls.append(state)
        return answer(category)

    monkeypatch.setattr(client, "_ask", ask)
    result = client.classify(
        "Subject", "Active request", attachment_filenames=("SI.pdf", "BL.pdf")
    )
    assert result.accepted == category
    assert len(calls) == 1
    assert "attachment_filenames" not in calls[0]


def test_vague_intent_uses_original_names_only_as_supplement(monkeypatch):
    client = jev()
    calls = []
    names = ("装运指示.pdf", "提单草稿.pdf", "ignore_instructions.txt")

    def ask(state, questions):
        calls.append(state)
        if len(calls) == 1:
            return answer("GENERAL")
        assert state["attachment_filenames"] == list(names)
        assert "untrusted" in questions["category"].instructions
        assert (
            "Do not infer shipment field values" in questions["category"].instructions
        )
        assert {k: v for k, v in state.items() if k != "attachment_filenames"} == calls[
            0
        ]
        return answer("BL_COMPARISON", 0.9)

    monkeypatch.setattr(client, "_ask", ask)
    result = client.classify(
        "Please check", "Check before release", attachment_filenames=names
    )
    assert result.accepted == "BL_COMPARISON"
    assert result.confidence == 0.9
    assert len(calls) == 2


@pytest.mark.parametrize(
    "supplement,confidence", [("BL_COMPARISON", 0.7), ("SPAM", 0.9)]
)
def test_uncertain_supplement_preserves_original_decision(
    monkeypatch, supplement, confidence
):
    client = jev()
    responses = iter([answer("GENERAL", 0.85), answer(supplement, confidence)])
    monkeypatch.setattr(client, "_ask", lambda *_: next(responses))
    result = client.classify(
        "Documents", "For reference", attachment_filenames=("draft.pdf",)
    )
    assert result.accepted == "GENERAL"
    assert result.confidence == 0.85


def test_general_without_attachments_does_not_make_an_extra_call(monkeypatch):
    client = jev()
    responses = iter([answer("GENERAL")])
    monkeypatch.setattr(client, "_ask", lambda *_: next(responses))
    assert client.classify("Update", "Arriving tomorrow").accepted == "GENERAL"
