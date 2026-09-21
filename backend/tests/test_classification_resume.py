"""A release cannot silently resume an incompatible classification."""

from unittest.mock import ANY, Mock

import pytest
from test_case_status import complete_case

from averis.domain import AttachmentView, Classification
from averis.pipeline import Checkpoints, ProcessingInput, ShipmentPipeline


@pytest.mark.parametrize(
    ("saved_model", "saved_policy", "calls"),
    [("current", "current", 0), ("old", "current", 1), ("current", "old", 1)],
)
def test_resume_reuses_only_matching_classification_profile(
    saved_model: str, saved_policy: str, calls: int
) -> None:
    saved = Classification(
        suggested="GENERAL",
        accepted="GENERAL",
        confidence=1,
        probabilities={"GENERAL": 1},
        model=saved_model,
        policy_version=saved_policy,
    )
    current = saved.model_copy(update={"model": "current", "policy_version": "current"})
    inference = Mock()
    inference.classify.return_value = current
    persist = Mock()
    checkpoints = Checkpoints(
        {
            "classification": saved.model_dump(mode="json"),
            "document:original": {"unchanged": True},
        },
        persist,
    )
    pipeline = ShipmentPipeline(
        inference,
        checkpoints,
        Mock(),
        Mock(),
        lambda: 400,
        classification_profile=("current", "current"),
    )
    case = complete_case()
    case.classification = None
    result = pipeline.process(ProcessingInput(case, None, {}))
    assert result.classification == current
    assert inference.classify.call_count == calls
    assert persist.call_count == calls
    assert checkpoints._saved["document:original"] == {"unchanged": True}


def test_human_category_takes_priority_over_saved_model_checkpoint() -> None:
    case = complete_case()
    human = Classification(
        suggested="INVOICE_QUERY",
        accepted="INVOICE_QUERY",
        confidence=1,
        probabilities={"INVOICE_QUERY": 1},
        model="reviewer",
        source="human",
    )
    case.classification = human
    inference = Mock()
    pipeline = ShipmentPipeline(
        inference,
        Checkpoints(
            {
                "classification": human.model_copy(
                    update={"source": "model", "accepted": "GENERAL"}
                ).model_dump(mode="json")
            },
            Mock(),
        ),
        Mock(),
        Mock(),
        lambda: 400,
        classification_profile=("current", "current"),
    )
    assert pipeline.process(ProcessingInput(case, None, {})).classification == human
    inference.classify.assert_not_called()


def test_classification_receives_only_current_attachment_names() -> None:
    case = complete_case()
    case.classification = None
    case.attachments = [
        AttachmentView(id="old", filename="old-draft.pdf", superseded=True),
        AttachmentView(id="current", filename="提单草稿.pdf"),
        AttachmentView(id="instruction", filename="shipping-instruction.pdf"),
    ]
    inference = Mock()
    inference.classify.return_value = Classification(
        suggested="GENERAL",
        accepted="GENERAL",
        confidence=1,
        probabilities={"GENERAL": 1},
        model="test",
    )
    pipeline = ShipmentPipeline(
        inference, Checkpoints({}, Mock()), Mock(), Mock(), lambda: 400
    )
    pipeline.process(ProcessingInput(case, None, {}))
    inference.classify.assert_called_once_with(
        case.subject,
        case.body,
        attachment_filenames=("提单草稿.pdf", "shipping-instruction.pdf"),
        load_attachment_previews=ANY,
    )
