"""Pure shipment policy: evidence in, reproducible findings out."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Final, Literal, cast

from averis.contracts import FIELDS, Field
from averis.domain import (
    DocumentEvidence,
    EvidenceBlock,
    Finding,
    Issue,
    Reading,
    Report,
)
from averis.fields import FIELD_ALIASES

LABELS: Final[dict[Field, tuple[str, ...]]] = dict(FIELD_ALIASES)

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)
OCR_CONFIDENCE_THRESHOLD: Final = 0.8
_SIMPLE_NUMBER = re.compile(
    r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*"
    r"(kg|kgs|kilograms?|mt|tonnes?|tons?|containers?|units?)?",
    re.IGNORECASE,
)
_CONTAINER_WITH_EQUIPMENT = re.compile(
    r"([0-9]+(?:,[0-9]{3})*)\s*[x×]\s*"
    r"[0-9]+(?:\.[0-9]+)?\s*(?:ft|')?\s*[a-z0-9/-]*",
    re.IGNORECASE,
)


def source_value(field: Field, text: str) -> str:
    """Remove only a recognized leading field label from source text."""

    for label in sorted(LABELS[field], key=len, reverse=True):
        result = re.sub(
            r"^\s*"
            + re.escape(label)
            + r"(?:\s*\([^()\r\n]*\))*"
            + r"(?:(?:\s*[:=\t|]\s*)|\s+)(?=\S)",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        if result != text:
            return result.strip()
    return text.strip()


def normalize(field: Field, text: str) -> str | None:
    """Normalize a source value without guessing a missing or ambiguous value."""

    normalized_source = unicodedata.normalize("NFKC", text)
    value = source_value(field, normalized_source).strip()
    if not value or value.casefold() in {
        "n/a",
        "none",
        "unknown",
        "-",
        "not provided",
    }:
        return None
    if field not in {"container_count", "gross_weight_kg"}:
        return " ".join(value.casefold().split())

    if field == "container_count":
        equipment = _CONTAINER_WITH_EQUIPMENT.fullmatch(value)
        if equipment:
            return str(int(equipment[1].replace(",", "")))

    match = _SIMPLE_NUMBER.fullmatch(value)
    if not match:
        return None
    try:
        number = Decimal(match[1].replace(",", ""))
    except InvalidOperation:
        return None
    unit = (match[2] or "").lower()
    if field == "container_count":
        if (
            unit not in {"", "container", "containers", "unit", "units"}
            or number != number.to_integral()
        ):
            return None
    else:
        if unit in {"mt", "tonne", "tonnes"}:
            number *= 1000
        elif unit not in {"kg", "kgs", "kilogram", "kilograms"} and not (
            unit == "" and re.search(r"\bkg\b|kilogram", text, re.IGNORECASE)
        ):
            # The value must establish kilograms; an arbitrary bare number is unsafe.
            return None
    return format(number.normalize(), "f")


def reading_from_evidence(
    field: Field,
    document: DocumentEvidence,
    ids: Sequence[str],
    confidence: float = 1,
    threshold: float = 0.8,
    transcription: str | None = None,
    verified: bool = False,
) -> Reading:
    """Create one reading while retaining selected source evidence and uncertainty."""

    blocks = {block.id: block for block in document.blocks}
    evidence_ids = list(dict.fromkeys(ids))
    if not evidence_ids or any(
        evidence_id not in blocks for evidence_id in evidence_ids
    ):
        return Reading(
            field=field,
            document_id=document.document_id,
            issue="missing_value",
        )
    selected = [blocks[evidence_id] for evidence_id in evidence_ids]
    if transcription is not None and not all(
        block.method == "ocr" for block in selected
    ):
        raise ValueError("Transcription is available only for OCR evidence")
    source_issue = _source_field_issue(field, selected)
    text = (
        transcription
        if transcription is not None
        else "\n".join(block.text for block in selected)
    )
    provenance: Literal["machine", "human_transcribed", "human_verified"]
    if verified:
        provenance = "human_verified"
    elif transcription is not None:
        provenance = "human_transcribed"
    else:
        provenance = "machine"
    normalized = None if source_issue is not None else normalize(field, text)
    ocr_blocks = [block for block in selected if block.method == "ocr"]
    issue: str | None = None
    if source_issue is not None:
        issue = source_issue
    elif normalized is None:
        issue = "missing_or_ambiguous_value"
    elif transcription is not None and not verified:
        issue = "unverified_transcription"
    elif not verified and any(block.ocr_confidence is None for block in ocr_blocks):
        issue = "unknown_ocr_confidence"
    elif not verified and any(
        cast(float, block.ocr_confidence) < OCR_CONFIDENCE_THRESHOLD
        for block in ocr_blocks
    ):
        issue = "low_ocr_confidence"
    elif confidence < threshold:
        issue = "low_field_confidence"
    return Reading(
        field=field,
        document_id=document.document_id,
        evidence_ids=evidence_ids,
        text=text,
        normalized=normalized,
        confidence=confidence,
        provenance=provenance,
        issue=issue,
    )


def _source_field_issue(field: Field, selected: Sequence[EvidenceBlock]) -> str | None:
    """Reject evidence that visibly belongs to another official field.

    Value-only blocks remain valid. When recognizable labels are present, a
    selected block must contain labels for only the requested field. Human OCR
    verification cannot clear this source-selection error.
    """

    detected: set[Field] = set()
    for block in selected:
        for line in block.text.splitlines():
            stripped = line.strip()
            for candidate in _TYPED_FIELDS:
                if source_value(candidate, stripped) != stripped:
                    detected.add(candidate)
    wrong = detected - {field}
    if not wrong:
        return None
    return "ambiguous_source_fields" if field in detected else "source_field_mismatch"


def compare(
    si: Mapping[str, Reading],
    bl: Mapping[str, Reading],
    revision: int,
    pair_valid: bool,
    issues: Sequence[str | Issue] | None = None,
) -> Report:
    """Compare all seven fields and preserve known results beside unknown ones."""

    report = Report(
        input_revision=revision,
        pair_valid=pair_valid,
        issues=list(issues or ()),
    )
    if not pair_valid:
        report.issues.append("pair_requires_review")
        return report
    for name in _TYPED_FIELDS:
        si_reading = si[name]
        bl_reading = bl[name]
        outcome: Literal["match", "mismatch", "unresolved"]
        if (
            si_reading.issue
            or bl_reading.issue
            or si_reading.normalized is None
            or bl_reading.normalized is None
        ):
            outcome = "unresolved"
        elif si_reading.normalized == bl_reading.normalized:
            outcome = "match"
        else:
            outcome = "mismatch"
        report.findings.append(
            Finding(field=name, si=si_reading, bl=bl_reading, outcome=outcome)
        )
    return report


def shipment_references(document: DocumentEvidence) -> set[str]:
    return {
        value for values in _references_by_kind(document).values() for value in values
    }


def _references_by_kind(document: DocumentEvidence) -> dict[str, set[str]]:
    """Keep identifier namespaces separate; a shared booking cannot mask a conflict."""
    text = "\n".join(block.text for block in document.blocks)
    labels = {
        "shipment": r"(?>shipment[ \t]*(?:id|ref(?:erence)?\.?))",
        "booking": r"(?>booking\b(?:[ \t]*(?:no\.?|number|ref(?:erence)?\.?))?)",
        "oc": r"(?>OC\b(?:[ \t]*(?:no\.?|number|ref(?:erence)?\.?))?)",
    }
    return {
        kind: {
            match.upper()
            for match in re.findall(
                r"(?<![A-Za-z0-9])"
                + label
                + r"[ \t]*[:#|=]?[ \t]*"
                + r"([A-Za-z0-9][A-Za-z0-9/-]{3,})"
                + r"(?=\s|$|[,;:|)\]}]|[.](?=\s|$))",
                text,
                re.IGNORECASE,
            )
        }
        for kind, label in labels.items()
    }


def validate_pair(
    si: DocumentEvidence,
    bl: DocumentEvidence,
    human_selected: bool = False,
) -> bool:
    """Reject same-document and known-conflicting pairs, even when human selected."""

    if si.document_id == bl.document_id:
        return False
    si_references = _references_by_kind(si)
    bl_references = _references_by_kind(bl)
    shared = False
    for kind, values in si_references.items():
        other = bl_references[kind]
        if values and other:
            if values != other:
                return False
            shared = True
    return human_selected or shared
