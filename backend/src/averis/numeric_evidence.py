"""Bounded numeric source choices and independent verification of their spans.

Models select candidates; this module copies source text and applies the existing
numeric policy. It never accepts generated values or inferred weight units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from averis.contracts import Field
from averis.domain import DocumentEvidence, NumericSelection, Reading
from averis.verification import normalize, reading_from_evidence

_NUMBER = re.compile(r"(?<![\w.,/-])[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?(?![\w.,/-])")
_UNIT = re.compile(
    r"(?<![A-Za-z])(?:kilograms?|kgs?|tonnes?|mt|公斤|千克|公吨|公噸|吨|噸|tan)(?![A-Za-z])",
    re.IGNORECASE,
)
NUMERIC_FIELDS: tuple[Field, ...] = ("container_count", "gross_weight_kg")
_REPAIRABLE = {
    "missing_or_ambiguous_value",
    "source_field_mismatch",
    "ambiguous_source_fields",
}


@dataclass(frozen=True)
class NumericCandidate:
    id: str
    selection: NumericSelection
    value: str
    line: str
    unit: str | None

    @property
    def source_value(self) -> str:
        return self.value + (" " + self.unit if self.unit else "")


def can_repair(document: DocumentEvidence, reading: Reading, threshold: float) -> bool:
    """Only repair confidently selected but unparseable native PDF readings."""
    return (
        reading.field in NUMERIC_FIELDS
        and reading.issue in _REPAIRABLE
        and reading.provenance == "machine"
        and reading.confidence is not None
        and reading.confidence >= threshold
        and bool(document.blocks)
        and all(
            block.method == "native"
            and bool(block.locations)
            and all(location.kind == "pdf" for location in block.locations)
            for block in document.blocks
        )
    )


def numeric_candidates(document: DocumentEvidence) -> list[NumericCandidate]:
    candidates: list[NumericCandidate] = []
    for block in document.blocks:
        if block.method != "native":
            continue
        offset = 0
        for line in block.text.splitlines(keepends=True):
            units = list(_UNIT.finditer(line))
            scales = {
                normalize("gross_weight_kg", "1 " + unit.group()) for unit in units
            }
            unit = units[0] if units and len(scales) == 1 else None
            for number in _NUMBER.finditer(line):
                candidates.append(
                    NumericCandidate(
                        id=f"V{len(candidates) + 1}",
                        selection=NumericSelection(
                            block_id=block.id,
                            start=offset + number.start(),
                            end=offset + number.end(),
                            unit_start=offset + unit.start() if unit else None,
                            unit_end=offset + unit.end() if unit else None,
                        ),
                        value=number.group(),
                        line=line.strip(),
                        unit=unit.group() if unit else None,
                    )
                )
                if len(candidates) > 120:
                    return []
            offset += len(line)
    return candidates


def bind_numeric_selection(
    document: DocumentEvidence,
    field: Field,
    selection: NumericSelection,
    confidence: float | None,
    model: str | None,
    threshold: float = 0.8,
) -> Reading:
    """Rebuild a selected value exclusively from this exact document version."""
    reading = reading_from_evidence(
        field,
        document,
        [selection.block_id],
        confidence,
        threshold,
        selection_model=model,
    )
    candidate = next(
        (item for item in numeric_candidates(document) if item.selection == selection),
        None,
    )
    if candidate is None or field not in NUMERIC_FIELDS:
        raise ValueError("Numeric selection does not identify a valid source span")
    block = next(block for block in document.blocks if block.id == selection.block_id)
    if not block.locations or any(
        location.kind != "pdf" for location in block.locations
    ):
        raise ValueError("Numeric assistance requires native PDF evidence")
    value = normalize(field, candidate.source_value)
    reading.normalized = value
    reading.numeric_selection = selection
    reading.issue = (
        "missing_or_ambiguous_value"
        if value is None
        else "low_field_confidence"
        if confidence is None or confidence < threshold
        else None
    )
    return reading
