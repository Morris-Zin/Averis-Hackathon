"""Source-bound shipment pairing; providers select evidence, never declare truth.

The module owns reference candidates, conflict checks and acceptance. A judge
receives the email and two independently read documents, then selects a shared
reference or abstains. Comparison-field similarity is never proof of identity.
"""

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from averis.domain import DocumentEvidence, PairingEvidence, normalize_issue
from averis.verification import validate_pair
from averis.versions import PAIRING_POLICY_VERSION

PAIRING_THRESHOLD = 0.95
_TOKEN = re.compile(r"(?<![\w/-])([A-Za-z0-9][A-Za-z0-9/-]{3,39})(?![\w/-])")


@dataclass(frozen=True)
class ReferenceCandidate:
    id: str
    value: str
    si_blocks: tuple[int, ...]
    bl_blocks: tuple[int, ...]

    def criteria(self) -> dict[str, object]:
        return {
            "id": self.id,
            "reference": self.value,
            "si_blocks": [f"S{i + 1}" for i in self.si_blocks],
            "bl_blocks": [f"B{i + 1}" for i in self.bl_blocks],
        }


@dataclass(frozen=True)
class PairingRequest:
    si: DocumentEvidence
    bl: DocumentEvidence
    candidates: tuple[ReferenceCandidate, ...]
    state: dict[str, object]

    def fingerprint(self, model: str | None) -> str:
        payload = {
            "state": self.state,
            "si": self.si.model_dump(mode="json"),
            "bl": self.bl.model_dump(mode="json"),
            "policy": PAIRING_POLICY_VERSION,
            "model": model,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()


class PairingProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected: str
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]
    model: str
    request_id: str | None = None


PairingJudge = Callable[[PairingRequest], PairingProposal]


def _tokens(document: DocumentEvidence) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for index, block in enumerate(document.blocks):
        if block.method == "ocr" and (block.ocr_confidence or 0) < 0.9:
            continue
        for match in _TOKEN.finditer(block.text):
            value = match.group(1).upper()
            if not any(c.isdigit() for c in value) or (
                value.isdigit() and len(value) < 6
            ):
                continue
            positions = found.setdefault(value, [])
            if index not in positions:
                positions.append(index)
    return found


def _blocks(document: DocumentEvidence, prefix: str) -> list[dict[str, object]]:
    return [
        {
            "id": f"{prefix}{i + 1}",
            "text": block.text,
            "confidence": (block.ocr_confidence or 0) if block.method == "ocr" else 1,
        }
        for i, block in enumerate(document.blocks)
    ]


def prepare_pairing(
    subject: str, body: str, si: DocumentEvidence, bl: DocumentEvidence
) -> PairingRequest | None:
    """Find verbatim shared candidates; no candidate means honest abstention."""
    if not validate_pair(si, bl, human_selected=True) or any(
        normalize_issue(issue).blocking
        for document in (si, bl)
        for issue in document.issues
    ):
        return None
    left, right = _tokens(si), _tokens(bl)
    shared = sorted(left.keys() & right.keys())
    if not shared or len(shared) > 32:
        return None
    candidates = tuple(
        ReferenceCandidate(f"R{i + 1}", value, tuple(left[value]), tuple(right[value]))
        for i, value in enumerate(shared)
    )
    state: dict[str, object] = {
        "email": {"subject": subject, "body": body},
        "si_blocks": _blocks(si, "S"),
        "bl_blocks": _blocks(bl, "B"),
        "candidates": [candidate.criteria() for candidate in candidates],
    }
    if len(json.dumps(state, ensure_ascii=False).encode()) > 80_000:
        return None
    return PairingRequest(si, bl, candidates, state)


def accept_pairing(
    request: PairingRequest, proposal: PairingProposal
) -> PairingEvidence | None:
    """Bind a validated selection back to both immutable document sources."""
    choices = {candidate.id: candidate for candidate in request.candidates}
    if proposal.selected not in {*choices, "NONE"}:
        raise ValueError("Pairing selected an unknown reference")
    probabilities = proposal.probabilities
    if (
        set(probabilities) != {*choices, "NONE"}
        or any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values())
        or not math.isclose(sum(probabilities.values()), 1, abs_tol=0.02)
        or probabilities[proposal.selected] < max(probabilities.values())
    ):
        raise ValueError("Invalid pairing probability distribution")
    if proposal.selected == "NONE" or proposal.confidence < PAIRING_THRESHOLD:
        return None
    # Rebuild from the current sources; forged/stale candidate objects cannot
    # attest values that no longer occur in the cited source blocks.
    current = prepare_pairing("", "", request.si, request.bl)
    if current is None or current.candidates != request.candidates:
        raise ValueError("Pairing candidates no longer match document evidence")
    candidate = choices[proposal.selected]
    return PairingEvidence(
        si_document_id=request.si.document_id,
        bl_document_id=request.bl.document_id,
        reference=candidate.value,
        si_evidence_ids=[request.si.blocks[i].id for i in candidate.si_blocks],
        bl_evidence_ids=[request.bl.blocks[i].id for i in candidate.bl_blocks],
        confidence=proposal.confidence,
        model=proposal.model,
        request_id=proposal.request_id,
        policy_version=PAIRING_POLICY_VERSION,
    )
