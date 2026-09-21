"""Provider-neutral intelligence boundary and shared interpretation.

Providers propose a category, document role and seven evidence selections with
uncertainty and metadata. This boundary validates proposals, applies the
configured acceptance policy, copies source text and produces validated domain
readings. Providers cannot supply authoritative normalized values or comparison
outcomes.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast, get_args

from averis.contracts import FIELDS, Category, Field
from averis.domain import Classification, DocumentEvidence, Reading, issue_is_blocking

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)
_CATEGORIES = cast(tuple[Category, ...], get_args(Category))


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    role: str
    role_confidence: float
    fields: dict[str, Reading]


MAX_CLASSIFICATION_DOCUMENTS = 4
MAX_PREVIEW_CHARACTERS = 2_000


@dataclass(frozen=True, slots=True)
class AttachmentPreview:
    """Partial source context for intent, never a document role or field reading."""

    filename: str
    text: str
    truncated: bool

    @classmethod
    def from_evidence(
        cls, filename: str, evidence: DocumentEvidence
    ) -> AttachmentPreview:
        if any(issue_is_blocking(issue) for issue in evidence.issues):
            return cls(filename, "", True)
        reliable = [
            block
            for block in evidence.blocks
            if block.method != "ocr"
            or (block.ocr_confidence is not None and block.ocr_confidence >= 0.8)
        ]
        text = "\n".join(block.text for block in reliable)
        return cls(
            filename,
            text[:MAX_PREVIEW_CHARACTERS],
            len(text) > MAX_PREVIEW_CHARACTERS or len(reliable) != len(evidence.blocks),
        )


AttachmentLoader = Callable[[], tuple[AttachmentPreview, ...]]


class Intelligence(Protocol):
    def classify(
        self,
        subject: str,
        body: str,
        *,
        attachment_filenames: tuple[str, ...] = (),
        load_attachment_previews: AttachmentLoader | None = None,
    ) -> Classification: ...

    def extract(self, document: DocumentEvidence) -> ExtractionResult: ...


class ProviderPermanentError(ValueError):
    """Configuration, request or malformed-response failure: stop visibly."""


class ProviderTransientError(RuntimeError):
    """Transport/service failure: existing bounded retries apply."""


class ProviderCapacityError(RuntimeError):
    """Capacity limitation: visible unsupported-input review outcome."""


def validate_extraction_proposal(
    document_id: str,
    selections: Mapping[str, tuple[str, float]],
    candidate_ids: frozenset[str],
) -> dict[str, tuple[str, float]]:
    """Require exactly the seven known fields, correct identity and valid refs.

    Explicit absent/ambiguous answers (NONE) become unresolved readings via the
    caller; malformed responses raise and become processing failures.
    """

    if set(selections) != set(_TYPED_FIELDS):
        raise ValueError("Extraction proposal must contain exactly the seven fields")
    if not document_id:
        raise ValueError("Extraction proposal has no document identity")
    validated: dict[str, tuple[str, float]] = {}
    for name in _TYPED_FIELDS:
        selected, confidence = selections[name]
        if selected not in candidate_ids:
            raise ValueError(f"Invalid evidence reference for {name}: {selected}")
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(f"Invalid field confidence for {name}")
        validated[name] = (selected, confidence)
    return validated
