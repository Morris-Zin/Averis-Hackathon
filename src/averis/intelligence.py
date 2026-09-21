"""Provider-neutral intelligence boundary and shared interpretation.

Providers propose a category, document role and seven evidence selections with
uncertainty and metadata. This boundary validates proposals, applies the
configured acceptance policy, copies source text and produces validated domain
readings. Providers cannot supply authoritative normalized values or comparison
outcomes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast, get_args

from typesafe_sdk import ChoiceAnswer

from averis.contracts import FIELDS, Category, Field
from averis.domain import Classification, DocumentEvidence, Reading

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)
_CATEGORIES = cast(tuple[Category, ...], get_args(Category))


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    role: str
    role_confidence: float
    fields: dict[str, Reading]


class Intelligence(Protocol):
    def classify(
        self, subject: str, body: str, *, attachment_filenames: tuple[str, ...] = ()
    ) -> Classification: ...

    def extract(self, document: DocumentEvidence) -> ExtractionResult: ...


class ProviderPermanentError(ValueError):
    """Configuration, request or malformed-response failure: stop visibly."""


class ProviderTransientError(RuntimeError):
    """Transport/service failure: existing bounded retries apply."""


class ProviderCapacityError(RuntimeError):
    """Capacity limitation: visible unsupported-input review outcome."""


def validate_choice_answer(
    answer: ChoiceAnswer,
    allowed: frozenset[str],
) -> tuple[str, float, dict[str, float]]:
    """Reject malformed provider state rather than converting it into a decision."""

    if answer.choice not in allowed:
        raise ValueError(f"Invalid choice response: {answer.choice}")
    if not math.isfinite(answer.confidence) or not 0 <= answer.confidence <= 1:
        raise ValueError("Invalid choice confidence")
    probabilities = dict(answer.probabilities)
    if set(probabilities) != set(allowed):
        raise ValueError("Choice probabilities do not match the requested criteria")
    if any(
        not math.isfinite(probability) or not 0 <= probability <= 1
        for probability in probabilities.values()
    ):
        raise ValueError("Invalid choice probabilities")
    if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.02):
        raise ValueError("Choice probabilities do not sum to one")
    if probabilities[answer.choice] < max(probabilities.values()):
        raise ValueError("Selected choice is not the highest-probability criterion")
    return answer.choice, answer.confidence, probabilities


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
