"""Regression checks for ownership and trusted checkpoint boundaries."""

import pytest
from test_case_status import complete_case

from averis.domain import Classification, PairAction
from averis.pipeline import Checkpoints, InvalidCheckpoint, ProcessingResult
from averis.review import review_case


@pytest.mark.parametrize(
    "category", ["GENERAL", "SPAM", "INVOICE_QUERY", "SI_REQUEST", None]
)
def test_non_comparison_never_loads_reads_or_extracts_attachments(category):
    from averis.pipeline import ProcessingInput, ShipmentPipeline

    case = complete_case()
    case.classification = Classification(
        suggested=category or "GENERAL",
        accepted=category,
        confidence=1 if category else 0.5,
        probabilities={category or "GENERAL": 1},
        source="human",
        model="fixture",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Non-comparison must not process attachments")

    class NoExtraction:
        extract = forbidden

    pipeline = ShipmentPipeline(
        NoExtraction(), Checkpoints({}, forbidden), forbidden, forbidden, lambda: 480
    )
    result = pipeline.process(ProcessingInput(case, None, {}))
    assert result.report is None
    assert result.attachments == case.attachments


def test_processing_outputs_preserve_reviewer_state_and_original():
    latest = complete_case()
    latest.assignee = "Mei Lin"
    latest.workflow = "waiting"
    latest.revision = 12
    saved = latest.model_dump(mode="json")
    result = ProcessingResult(latest.classification, [], None, ["Select documents"])
    updated = result.apply_to(latest)
    assert (updated.assignee, updated.workflow, updated.revision) == (
        "Mei Lin",
        "waiting",
        12,
    )
    assert updated.report is None
    assert updated.review_reasons == ["Select documents"]
    assert latest.model_dump(mode="json") == saved


def test_invalid_checkpoint_is_not_treated_as_an_absent_stage():
    checkpoints = Checkpoints({"classification": {}}, lambda *_: None)
    with pytest.raises(InvalidCheckpoint):
        checkpoints.load("classification", Classification)
    assert checkpoints.load("absent", Classification) is None


def test_failed_checkpoint_commit_does_not_expose_unsaved_progress():
    def failed_save(*_):
        raise RuntimeError("Database unavailable")

    checkpoints = Checkpoints({}, failed_save)
    with pytest.raises(RuntimeError):
        checkpoints.save("classification", complete_case().classification)
    assert checkpoints.load("classification", Classification) is None


def test_same_document_cannot_fill_both_roles():
    original = complete_case()
    with pytest.raises(ValueError, match="different SI and BL"):
        review_case(
            original,
            PairAction(
                expected_revision=1,
                si_id="same",
                bl_id="same",
                reason="Reviewed",
            ),
            controlled=True,
        )
    assert original.report is not None
