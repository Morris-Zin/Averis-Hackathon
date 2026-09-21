"""Pairing proves shipment identity, never similarity of comparison values."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_case_status import complete_case

from averis.domain import DocumentEvidence, EvidenceBlock
from averis.pairing import PairingProposal, accept_pairing, prepare_pairing
from averis.pipeline import Checkpoints, ProcessingInput, ShipmentPipeline
from averis.verification import validate_pair


def document(identity, text):
    return DocumentEvidence(
        document_id=identity,
        blocks=[EvidenceBlock(id=identity + "-1", text=text, locations=[])],
    )


def documents():
    return (
        document("si", "BL INSTRUCTION: ORD-123456\nContainers: 3"),
        document("bl", "Order No: ORD-123456\nContainers: 4"),
    )


def proposal(selected="R1", confidence=0.98):
    return PairingProposal(
        selected=selected,
        confidence=confidence,
        probabilities={
            "R1": 0.98 if selected == "R1" else 0.02,
            "NONE": 0.02 if selected == "R1" else 0.98,
        },
        model="test",
    )


def test_different_shipment_values_do_not_prevent_source_bound_pairing():
    si, bl = documents()
    request = prepare_pairing("Check draft", "Please compare", si, bl)
    assert request is not None
    proof = accept_pairing(request, proposal())
    assert proof is not None
    assert proof.reference == "ORD-123456"
    assert proof.si_evidence_ids == ["si-1"]
    assert proof.bl_evidence_ids == ["bl-1"]
    assert (proof.si_document_id, proof.bl_document_id) == ("si", "bl")


@pytest.mark.parametrize("answer", [proposal("NONE"), proposal(confidence=0.94)])
def test_uncertainty_never_confirms_pair(answer):
    request = prepare_pairing("", "", *documents())
    assert request is not None
    assert accept_pairing(request, answer) is None


@pytest.mark.parametrize(
    "label",
    ["Shipment ID", "Booking No", "Order No", "BL INSTRUCTION", "Bill of Lading No"],
)
def test_conflicting_references_override_shared_reference_and_human_selection(label):
    si = document("si", f"{label}: REF-123456\nShipment ID: SAME-123456")
    bl = document("bl", f"{label}: REF-654321\nShipment ID: SAME-123456")
    assert not validate_pair(si, bl, human_selected=True)
    assert prepare_pairing("", "", si, bl) is None


@pytest.mark.parametrize(
    "problem",
    [
        "same_document",
        "no_reference",
        "blocking_issue",
        "weak_ocr",
        "unknown_ocr",
        "too_large",
    ],
)
def test_unsupported_identity_stays_unknown(problem):
    si, bl = documents()
    if problem == "same_document":
        bl.document_id = si.document_id
    elif problem == "no_reference":
        si.blocks[0].text = "Acme company; containers 3"
    elif problem == "blocking_issue":
        si.issues = ["unreadable_page"]
    elif problem in {"weak_ocr", "unknown_ocr"}:
        si.blocks[0].method = "ocr"
        si.blocks[0].ocr_confidence = 0.89 if problem == "weak_ocr" else None
    elif problem == "too_large":
        si.blocks[0].text += " text" * 20000
    assert (
        prepare_pairing("REF-123456", "These definitely belong together", si, bl)
        is None
    )


def test_source_mutation_invalidates_selected_reference():
    si, bl = documents()
    request = prepare_pairing("", "", si, bl)
    assert request is not None
    si.blocks[0].text = "Order: OTHER-777777"
    with pytest.raises(ValueError, match="no longer match"):
        accept_pairing(request, proposal())


def test_forged_candidate_cannot_supply_a_reference():
    request = prepare_pairing("", "", *documents())
    assert request is not None
    forged = replace(
        request, candidates=(replace(request.candidates[0], value="INVENTED-123456"),)
    )
    with pytest.raises(ValueError, match="no longer match"):
        accept_pairing(forged, proposal())


@pytest.mark.parametrize(
    "probabilities",
    [
        {"R1": 1},
        {"R1": 0.8, "NONE": 0.8},
        {"R1": 0.1, "NONE": 0.9},
        {"R1": float("nan"), "NONE": 0},
    ],
)
def test_malformed_provider_output_is_a_failure(probabilities):
    request = prepare_pairing("", "", *documents())
    assert request is not None
    with pytest.raises(ValueError, match="probability"):
        accept_pairing(
            request, proposal().model_copy(update={"probabilities": probabilities})
        )


def pipeline(judge, checkpoints=None, remaining=480, model="test"):
    return ShipmentPipeline(
        Mock(),
        checkpoints or Checkpoints({}, Mock()),
        Mock(),
        Mock(),
        lambda: remaining,
        classification_profile=(model, "test"),
        pairing_judge=judge,
    )


def test_duplicate_attempt_reuses_paid_judgment():
    judge = Mock(return_value=proposal())
    checkpoints = Checkpoints({}, Mock())
    inputs = ProcessingInput(complete_case(), None, {})
    si, bl = documents()
    first = pipeline(judge, checkpoints)._pair(si, bl, inputs)
    second = pipeline(judge, checkpoints)._pair(si, bl, inputs)
    assert first == second
    assert first[0]
    assert judge.call_count == 1


@pytest.mark.parametrize("change", ["email", "source", "identity", "model"])
def test_changed_input_does_not_reuse_pairing_checkpoint(change):
    judge = Mock(return_value=proposal())
    checkpoints = Checkpoints({}, Mock())
    inputs = ProcessingInput(complete_case(), None, {})
    si, bl = documents()
    pipeline(judge, checkpoints)._pair(si, bl, inputs)
    if change == "email":
        inputs.case.body = "Different request"
    elif change == "source":
        si.blocks[0].text += "\nConsignee: Someone else"
    elif change == "identity":
        si.document_id = "revision-2"
    pipeline(judge, checkpoints, model="new" if change == "model" else "test")._pair(
        si, bl, inputs
    )
    assert judge.call_count == 2


def test_existing_reference_and_reviewed_pair_do_not_call_judge():
    judge = Mock(side_effect=AssertionError("No paid call expected"))
    inputs = ProcessingInput(complete_case(), None, {})
    assert pipeline(judge)._pair(
        document("si", "Shipment ID: SAME-123456"),
        document("bl", "Shipment ID: SAME-123456"),
        inputs,
    ) == (True, None)
    assert pipeline(judge)._pair(
        *documents(), replace(inputs, accepted_pair=["si", "bl"])
    ) == (True, None)


def test_offline_pipeline_does_not_implicitly_enable_provider():
    assert pipeline(None)._pair(
        *documents(), ProcessingInput(complete_case(), None, {})
    ) == (False, None)


def test_deadline_stops_new_paid_pairing():
    judge = Mock()
    with pytest.raises(TimeoutError):
        pipeline(judge, remaining=44)._pair(
            *documents(), ProcessingInput(complete_case(), None, {})
        )
    judge.assert_not_called()


def test_provider_failure_is_not_saved_as_pairing_success():
    saved = {}
    judge = Mock(side_effect=RuntimeError("Provider unavailable"))
    with pytest.raises(RuntimeError, match="Provider unavailable"):
        pipeline(judge, Checkpoints(saved, Mock()))._pair(
            *documents(), ProcessingInput(complete_case(), None, {})
        )
    assert "pairing" not in saved


def test_reading_correction_keeps_pairing_source_proof():
    from test_domain_review import comparison_case, evidence

    from averis.domain import CorrectAction
    from averis.review import review_case

    si, bl = documents()
    request = prepare_pairing("", "", si, bl)
    assert request is not None
    proof = accept_pairing(request, proposal())
    case = comparison_case(bl_evidence=evidence("bl", "Container count: 4"))
    case.report.pairing_evidence = proof
    result = review_case(
        case,
        CorrectAction(
            expected_revision=1,
            document_id="bl",
            field="container_count",
            evidence_ids=["bl:b1"],
            reason="Checked original",
            verified=True,
        ),
        controlled=True,
    )
    assert result.view.report.pairing_evidence == proof
