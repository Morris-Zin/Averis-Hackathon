"""Pure shipment policy: evidence in, reproducible findings out."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Final, Literal, cast

from averis.contracts import FIELDS, Field
from averis.domain import DocumentEvidence, Finding, Reading, Report

LABELS: Final[dict[Field, tuple[str, ...]]] = {
    "shipper": ("shipper/exporter", "shipper", "exporter"),
    "consignee": ("to the order of", "consignee"),
    "notify_party": ("notify party/intermediate consignee", "notify party", "notify"),
    "port_of_loading": ("port of loading", "load port", "pol"),
    "port_of_discharge": ("port of discharge", "discharge port", "pod"),
    "container_count": (
        "number of containers or packages",
        "no. of containers or packages",
        "number of containers",
        "no. of containers",
        "container count",
        "total containers",
        "containers",
    ),
    "gross_weight_kg": (
        "gross weight毛重(kgs)",
        "gross weight (kg)",
        "gross wt (kgs)",
        "gross weight kg",
        "gross weight",
        "gross wt",
    ),
}

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)
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
            r"^\s*" + re.escape(label) + r"(?:\s*\([^()\r\n]*\))*\s*(?:[:=\t]|\|)\s*",
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
    if not ids or any(evidence_id not in blocks for evidence_id in ids):
        return Reading(
            field=field,
            document_id=document.document_id,
            issue="missing_value",
        )
    selected = [blocks[evidence_id] for evidence_id in ids]
    if transcription is not None and not all(
        block.method == "ocr" for block in selected
    ):
        raise ValueError("Transcription is available only for OCR evidence")
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
    normalized = normalize(field, text)
    issue: str | None = None
    if normalized is None:
        issue = "missing_or_ambiguous_value"
    elif transcription is not None and not verified:
        issue = "unverified_transcription"
    elif confidence < threshold:
        issue = "low_field_confidence"
    return Reading(
        field=field,
        document_id=document.document_id,
        evidence_ids=list(ids),
        text=text,
        normalized=normalized,
        confidence=confidence,
        provenance=provenance,
        issue=issue,
    )


def compare(
    si: Mapping[str, Reading],
    bl: Mapping[str, Reading],
    revision: int,
    pair_valid: bool,
    issues: Sequence[str] | None = None,
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
    return {value for values in _references_by_kind(document).values() for value in values}


def _references_by_kind(document: DocumentEvidence) -> dict[str, set[str]]:
    """Keep identifier namespaces separate; a shared booking cannot mask a conflict."""
    text = "\n".join(block.text for block in document.blocks)
    labels = {
        "shipment": r"shipment\s*(?:id|ref(?:erence)?\.?)",
        "booking": r"booking\s*(?:no\.?|number|ref(?:erence)?\.?)",
        "oc": r"OC\b(?:\s*(?:no\.?|number|ref(?:erence)?\.?))?",
    }
    return {
        kind: {match.upper() for match in re.findall(
            r"(?:^|\n)\s*" + label
            + r"\s*[:#|=]?\s*([A-Za-z0-9][A-Za-z0-9/-]{3,})(?=\s|$)",
            text, re.IGNORECASE,
        )}
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
