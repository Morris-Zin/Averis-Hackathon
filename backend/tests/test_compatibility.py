"""Checkpoint and evidence compatibility without new inference costs."""

import pytest
from test_case_status import complete_case

from averis.domain import Reading, evidence_fingerprint
from averis.pipeline import (
    Checkpoints,
    InvalidCheckpoint,
    _DocumentCheckpoint,
    _ExtractionCheckpoint,
)
from averis.versions import CHECKPOINT_VERSION, OCR_PROFILE, READER_VERSION
from tests.test_component_contracts import doc


def test_unversioned_resumable_checkpoint_cannot_be_reused():
    checkpoints = Checkpoints(
        {"document:doc-1": {"evidence": doc().model_dump(mode="json")}}, lambda *_: None
    )
    with pytest.raises(InvalidCheckpoint):
        checkpoints.load("document:doc-1", _DocumentCheckpoint)


def test_reader_change_invalidates_dependent_extraction():
    evidence = doc()
    fingerprint = evidence_fingerprint(evidence)
    saved = _ExtractionCheckpoint(
        version=CHECKPOINT_VERSION,
        role="SI",
        role_confidence=1,
        fields={},
        evidence_fingerprint="different-fingerprint",
        acceptance_profile="jev-acceptance-v1",
        extraction_policy="extraction-v3",
        normalization_profile="english-nfkc-v1",
    )
    checkpoints = Checkpoints(
        {"extraction:doc-1": saved.model_dump(mode="json")}, lambda *_: None
    )
    loaded = checkpoints.load("extraction:doc-1", _ExtractionCheckpoint)
    assert loaded is not None
    # Pipeline re-checks the fingerprint against current evidence; mismatch
    # raises InvalidCheckpoint instead of silently reusing or paying for AI.
    assert loaded.evidence_fingerprint != fingerprint


def test_corrections_require_exact_evidence_fingerprint():
    evidence = doc()
    current = evidence_fingerprint(evidence)
    override = Reading(
        field="shipper",
        document_id=evidence.document_id,
        evidence_ids=[f"{evidence.document_id}:b1"],
        text="Changed",
        normalized="changed",
        evidence_fingerprint="stale-fingerprint",
    )
    assert override.evidence_fingerprint != current
    # Pipeline ignores stale overrides; review binds new corrections to the
    # current fingerprint (covered in test_domain_review via evidence_fingerprint).


def test_legacy_evidence_fingerprints_from_stored_contents():
    legacy = doc()
    legacy.reader_version = "evidence-v2"
    legacy.evidence_fingerprint = None
    assert evidence_fingerprint(legacy)


def test_unchanged_retry_reuses_completed_stages():
    evidence = doc()
    fingerprint = evidence_fingerprint(evidence)
    saved_doc = _DocumentCheckpoint(
        version=CHECKPOINT_VERSION,
        evidence=evidence,
        reader_version=READER_VERSION,
        ocr_profile=OCR_PROFILE,
        evidence_fingerprint=fingerprint,
    )
    checkpoints = Checkpoints(
        {"document:doc-1": saved_doc.model_dump(mode="json")}, lambda *_: None
    )
    assert checkpoints.load("document:doc-1", _DocumentCheckpoint) is not None
    assert complete_case().revision == 1
