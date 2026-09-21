"""Private document evidence implementation."""

from __future__ import annotations

import re
import unicodedata

from averis.domain import DocumentEvidence
from averis.fields import DOCUMENT_BOUNDARY_LABELS
from averis.fields import FIELD_ALIASES as _SHARED_FIELD_ALIASES
from averis.versions import OCR_PROFILE, READER_VERSION

_TEXT_LABEL = re.compile(r"^[^\s:\r\n][^:\r\n]{0,80}:\s*\S")


def validate_document_evidence(evidence: DocumentEvidence) -> list[str]:
    """Validate identity, unique IDs, locations and partial-reading outcomes.

    Returns a list of completeness problems; empty means the evidence is
    structurally valid. Shipping values are never interpreted here.
    """

    problems: list[str] = []
    if not evidence.document_id:
        problems.append("missing_document_identity")
    seen: set[str] = set()
    for block in evidence.blocks:
        if block.id in seen:
            problems.append(f"duplicate_evidence_id:{block.id}")
        seen.add(block.id)
        if not block.text.strip():
            problems.append(f"empty_evidence_text:{block.id}")
        if not block.locations:
            problems.append(f"missing_location:{block.id}")
        for location in block.locations:
            if location.kind == "docx" and location.page is not None:
                problems.append(f"invented_docx_page:{block.id}")
    if not evidence.blocks and not evidence.issues:
        problems.append("empty_reading_without_issue")
    return problems


def with_metadata(
    document_id: str, content: bytes, evidence: DocumentEvidence
) -> DocumentEvidence:
    """Stamp immutable source identity, reader version and evidence fingerprint."""

    from hashlib import sha256

    from averis.domain import evidence_fingerprint

    evidence.document_id = document_id
    evidence.reader_version = READER_VERSION
    evidence.ocr_profile = OCR_PROFILE
    try:
        evidence.source_sha256 = sha256(content).hexdigest()
    except Exception:  # noqa: BLE001 - hashing never blocks evidence return
        evidence.source_sha256 = None
    try:
        evidence.evidence_fingerprint = evidence_fingerprint(evidence)
    except Exception:  # noqa: BLE001 - fingerprint failures stay explicit
        evidence.evidence_fingerprint = None
    return evidence


def starts_text_field(line: str) -> bool:
    """Start a source block at a labelled field, including unfamiliar fields.

    Known shipment labels may omit punctuation, while an unfamiliar label must
    start at the left margin and use a colon. Indented address continuations
    such as ``P.O. BOX: 123`` therefore stay with their owning field.
    """

    return (
        starts_evidence_field(line)
        or _TEXT_LABEL.match(unicodedata.normalize("NFKC", line)) is not None
    )


_EVIDENCE_FIELD_LABEL = re.compile(
    r"^\s*(?:"
    r"shipper|exporter|consignee|notify\s*party|notify|"
    r"port\s*of\s*loading|load\s+port|pol|"
    r"port\s*of\s*discharge|discharge\s+port|pod|"
    r"number\s+of\s+containers(?:\s+or\s+packages)?|"
    r"no\.\s*of\s+containers(?:\s+or\s+packages)?|"
    r"container\s+count|containers|"
    r"(?:total\s+)?gross\s+weight(?:毛重)?(?:\s*\([^)]*\)|\s+kgs?)?|"
    r"(?:total\s+)?gross\s+wt(?:\s*\([^)]*\)|\s+kgs?)?|"
    r"b/l\s+(?:no|number)|bill\s+of\s+lading\s+(?:no|number)|"
    r"booking(?:\s+(?:no|number|ref|reference))?|"
    r"ocean\s+vessel|vessel|voyage|export\s+carrier|container\s+no|hs\s+code"
    r")(?=\s*[:=|]\s*\S|\.?\s+\S)",
    re.IGNORECASE,
)


def official_field_aliases() -> dict[str, tuple[str, ...]]:
    """Return the shared official aliases; layout grouping stays private.

    The segmentation regex above covers these official aliases plus
    parser-only headings (vessel, voyage, booking, B/L number, HS code).
    Multiline addresses are preserved because only a new label starts a block.
    """

    return {str(key): value for key, value in _SHARED_FIELD_ALIASES.items()}


def starts_evidence_field(text: str) -> bool:
    """Recognize a new official field without dropping continuation lines."""

    normalized = unicodedata.normalize("NFKC", text)
    return (
        _EVIDENCE_FIELD_LABEL.match(normalized) is not None
        or _SHARED_FIELD_LABEL.match(normalized) is not None
        or _DOCUMENT_BOUNDARY_LABEL.match(normalized) is not None
    )


_DOCUMENT_BOUNDARY_LABEL = re.compile(
    r"^\s*(?:"
    + "|".join(
        re.escape(label)
        for label in sorted(DOCUMENT_BOUNDARY_LABELS, key=len, reverse=True)
    )
    + r")(?=\s|[:=|]|$)",
    re.IGNORECASE,
)

_SHARED_FIELD_LABEL = re.compile(
    r"^\s*(?:"
    + "|".join(
        re.escape(label)
        for label in sorted(
            {label for aliases in _SHARED_FIELD_ALIASES.values() for label in aliases},
            key=len,
            reverse=True,
        )
    )
    + r")(?:\s*\([^()\r\n]*\))*(?=\s*[:=|]\s*\S|\s+\S)",
    re.IGNORECASE,
)


def block_id(document_id: str, number: int) -> str:
    return f"{document_id}:b{number:04d}"
