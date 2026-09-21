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
from averis.source_regions import has_omitted_continuation

LABELS: Final[dict[Field, tuple[str, ...]]] = dict(FIELD_ALIASES)

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)
OCR_CONFIDENCE_THRESHOLD: Final = 0.8
_SIMPLE_NUMBER = re.compile(
    r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*"
    r"(kg|kgs|kilograms?|mt|tonnes?|tons?|公斤|千克|公吨|公噸|吨|噸|kilogram|tan|containers?|units?|kontena|个|個|箱)?",
    re.IGNORECASE,
)
_CONTAINER_WITH_EQUIPMENT = re.compile(
    r"([0-9]+(?:,[0-9]{3})*)\s*[x×]\s*"
    r"[0-9]+(?:\.[0-9]+)?\s*(?:ft|')?\s*[a-z0-9/-]*",
    re.IGNORECASE,
)
_INLINE_FIELD_LABELS = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(label)
        for label in sorted(
            {label for aliases in LABELS.values() for label in aliases},
            key=len,
            reverse=True,
        )
    )
    + r")\s*[:=|]",
    re.IGNORECASE,
)


def source_value(field: Field, text: str) -> str:
    """Remove only a recognized leading field label from source text."""

    canonical = unicodedata.normalize("NFKC", text)
    for label in sorted(LABELS[field], key=len, reverse=True):
        result = re.sub(
            r"^\s*"
            + re.escape(label)
            + r"(?:\s*\([^()\r\n]*\))*"
            + r"(?:(?:\s*[:=\t|]\s*)|\s+)(?=\S)",
            "",
            canonical,
            count=1,
            flags=re.IGNORECASE,
        )
        if result != canonical:
            return result.strip()
    return text.strip()


def normalize(field: Field, text: str) -> str | None:
    """Normalize a source value without guessing a missing or ambiguous value."""

    normalized_source = unicodedata.normalize("NFKC", text)
    value = source_value(field, normalized_source).strip()
    missing_marker = value.casefold().strip(" .:;!?")
    if not value or missing_marker in {
        "n/a",
        "none",
        "unknown",
        "-",
        "not provided",
        "not available",
        "n.a",
        "n.a.",
    }:
        return None
    if field in {"port_of_loading", "port_of_discharge"} and missing_marker in {
        "tba",
        "tbd",
        "to be advised",
        "to be confirmed",
        "to be determined",
    }:
        return None
    if field in {"port_of_loading", "port_of_discharge"} and any(
        separator in value for separator in ":=|"
    ):
        # A leftover labelled expression is not a clean port reading. In
        # particular, a provider selecting an unfamiliar "Port ...:" label
        # must not turn that whole label into a confident port value.
        return None
    if field not in {"container_count", "gross_weight_kg"}:
        if field in {"shipper", "consignee", "notify_party"}:
            # Table-cell and address-line separators are layout, not content.
            # Preserve punctuation inside names, numbers and postcodes.
            value = re.sub(r"\s+[|]\s+|;(?=\s)", "\n", value)
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
        ambiguous_label = any(
            "packages" in label
            and normalized_source.casefold().lstrip().startswith(label)
            for label in LABELS[field]
        )
        if ambiguous_label and unit not in {"container", "containers", "kontena"}:
            return None
        if (
            unit
            not in {
                "",
                "container",
                "containers",
                "unit",
                "units",
                "kontena",
                "个",
                "個",
                "箱",
            }
            or number != number.to_integral()
        ):
            return None
    else:
        if unit in {"mt", "tonne", "tonnes", "公吨", "公噸", "吨", "噸", "tan"}:
            number *= 1000
        elif unit not in {
            "kg",
            "kgs",
            "kilogram",
            "kilograms",
            "公斤",
            "千克",
        } and not (
            unit == ""
            and re.search(r"\bkgs?\b|kilogram|公斤|千克", text, re.IGNORECASE)
        ):
            # The value must establish kilograms; an arbitrary bare number is unsafe.
            return None
    return format(number.normalize(), "f")


def reading_from_evidence(
    field: Field,
    document: DocumentEvidence,
    ids: Sequence[str],
    confidence: float | None = 1,
    threshold: float = 0.8,
    transcription: str | None = None,
    verified: bool = False,
    acceptance_basis: Literal["probability", "explicit_source"] = "probability",
    selection_model: str | None = None,
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
    if (
        field == "port_of_discharge"
        and any(
            block.text.casefold().lstrip().startswith("destination port")
            for block in selected
        )
        and any(
            source_value("port_of_discharge", line.strip()) != line.strip()
            and not line.casefold().lstrip().startswith("destination port")
            for block in document.blocks
            if block.id not in evidence_ids
            for line in block.text.splitlines()
        )
    ):
        # A destination can be beyond the discharge port on a through shipment.
        # Prefer explicit discharge evidence instead of silently equating them.
        source_issue = "destination_port_requires_review"
    if field in {"shipper", "consignee", "notify_party"} and has_omitted_continuation(
        document, evidence_ids
    ):
        source_issue = source_issue or "incomplete_party_evidence"
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
    elif acceptance_basis == "probability" and (
        confidence is None or confidence < threshold
    ):
        issue = "low_field_confidence"
    return Reading(
        field=field,
        document_id=document.document_id,
        evidence_ids=evidence_ids,
        text=text,
        normalized=normalized,
        confidence=confidence,
        acceptance_basis=acceptance_basis,
        selection_model=selection_model,
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
            # Consume the longest complete label before looking for another.
            # "Notify Party/Intermediate Consignee:" is one notify-party label,
            # while "Notify Party: A Consignee: B" still names two fields.
            for match in _INLINE_FIELD_LABELS.finditer(
                unicodedata.normalize("NFKC", stripped)
            ):
                label = match[0].rstrip(":=| ").casefold()
                detected.update(
                    candidate
                    for candidate, aliases in LABELS.items()
                    if label in aliases
                )
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
            Finding(
                field=name,
                si=si_reading,
                bl=bl_reading,
                outcome=outcome if pair_valid else "unresolved",
                provisional_outcome=outcome if not pair_valid else None,
            )
        )
    return report


def shipment_references(document: DocumentEvidence) -> set[str]:
    return {
        value for values in _references_by_kind(document).values() for value in values
    }


def _references_by_kind(document: DocumentEvidence) -> dict[str, set[str]]:
    """Keep identifier namespaces separate; a shared booking cannot mask a conflict."""
    text = unicodedata.normalize(
        "NFKC", "\n".join(block.text for block in document.blocks)
    )
    labels = {
        "shipment": r"(?>shipment[ \t]*(?:id|ref(?:erence)?\.?)|装运编号|裝運編號|货运编号|貨運編號|rujukan[ \t]+penghantaran)",
        "booking": r"(?>booking\b(?:[ \t]*(?:no\.?|number|ref(?:erence)?\.?))?|订舱号|訂艙號|nombor[ \t]+tempahan)",
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

    if si.document_id == bl.document_id or _additional_reference_conflict(si, bl):
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


_ADDITIONAL_REFERENCE_LABELS = {
    "order": r"(?:order(?:[ \t]+(?:no\.?|number|ref(?:erence)?))?|订单(?:编号|号|参考号)|訂單(?:編號|號)|no\.?[ \t]+pesanan)",
    "instruction": r"(?:bl[ \t]+instruction|提单补料编号|提單補料編號|arahan[ \t]+bl)",
    "bill": r"(?:bill[ \t]+of[ \t]+lading(?:[ \t]+(?:no\.?|number))?|b/l[ \t]*(?:no\.?|number)|提单(?:编号|号|参考号)|提單(?:編號|號))",
}


def _additional_reference_conflict(si: DocumentEvidence, bl: DocumentEvidence) -> bool:
    """Never let a matching identifier hide another explicit conflict."""
    for label in _ADDITIONAL_REFERENCE_LABELS.values():
        pattern = re.compile(
            r"(?<!\w)(?>"
            + label
            + r")(?:[ \t]*[:#|=][ \t]*|[ \t]+)([A-Za-z0-9][A-Za-z0-9/-]{3,39})(?![\w/-])",
            re.IGNORECASE,
        )
        left, right = [
            {
                m.group(1).upper()
                for block in document.blocks
                for m in pattern.finditer(block.text)
                if any(c.isdigit() for c in m.group(1))
            }
            for document in (si, bl)
        ]
        if left and right and (left != right or len(left) > 1):
            return True
    return False
