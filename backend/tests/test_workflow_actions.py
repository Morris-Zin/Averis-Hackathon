"""Typed actions, monotonic revisions and untouched processing inputs."""

import pytest
from pydantic import TypeAdapter, ValidationError
from test_case_status import complete_case

from averis.domain import (
    Action,
    AssignAction,
    CorrectAction,
    PairAction,
    RetryAction,
)
from averis.review import review_case


def test_required_payloads_fail_at_http_boundary():
    adapter = TypeAdapter(Action)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "pair", "expected_revision": 1, "si_id": "a"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "correct", "expected_revision": 1})
    valid = adapter.validate_python(
        {"kind": "retry", "expected_revision": 2, "reason": "retry"}
    )
    assert isinstance(valid, RetryAction)


def test_source_bound_corrections_and_monotonic_revisions():
    from tests.test_domain_review import comparison_case, evidence

    view = comparison_case(bl_evidence=evidence("bl", "Shipper: Test Co"))
    before = (view.revision, view.input_revision, view.model_dump(mode="json"))
    decision = review_case(
        view,
        CorrectAction(
            expected_revision=1,
            field="shipper",
            document_id="bl",
            evidence_ids=["bl:b1"],
            reason="Confirm",
        ),
        controlled=False,
    )
    # Review determines the next input revision once; workflow only bumps case revision.
    assert decision.next_input_revision == view.input_revision + 1
    assert decision.view.input_revision == decision.next_input_revision
    assert decision.reading_override is not None
    key, reading = decision.reading_override
    assert key == "bl:shipper"
    assert reading.evidence_fingerprint
    # Original inputs are untouched (review works on a private copy).
    assert view.model_dump(mode="json") == before[2]


def test_pair_action_binds_to_case_documents():
    from tests.test_domain_review import comparison_case, evidence

    view = comparison_case(bl_evidence=evidence("bl", "Shipper: Test Co"))
    # comparison_case has si without evidence; pairing requires read documents.
    with pytest.raises(ValueError, match="Choose two read documents"):
        review_case(
            view,
            PairAction(expected_revision=1, si_id="missing", bl_id="bl", reason="x"),
            controlled=False,
        )


def test_assign_action_owns_reviewer_membership():
    view = complete_case()
    with pytest.raises(ValueError, match="Unknown reviewer"):
        review_case(
            view, AssignAction(expected_revision=1, assignee="Nobody"), controlled=False
        )
