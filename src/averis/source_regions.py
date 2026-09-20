"""Complete party candidates over immutable, located source blocks.

Callers receive source references, never rewritten values. This module owns
conservative continuation geometry and excludes partial alternatives when the
source clearly supplies a continuation. The same regions constrain automated
selection and source-bound reviewer corrections.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from averis.domain import DocumentEvidence, EvidenceBlock, Location
from averis.fields import DOCUMENT_BOUNDARY_LABELS, FIELD_ALIASES

_PARTIES = ("shipper", "consignee", "notify_party")
_PARTY_START = re.compile(
    r"^\s*(?:"
    + "|".join(
        re.escape(alias)
        for alias in sorted(
            {
                alias
                for field, aliases in FIELD_ALIASES.items()
                if field in _PARTIES
                for alias in aliases
            },
            key=len,
            reverse=True,
        )
    )
    + r")(?=\s|[:=|]|$)",
    re.IGNORECASE,
)
_FIELD_START = re.compile(
    r"^\s*(?:"
    + "|".join(
        re.escape(alias)
        for alias in sorted(
            {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
            | set(DOCUMENT_BOUNDARY_LABELS),
            key=len,
            reverse=True,
        )
    )
    + r")(?=\s|[:=|]|$)",
    re.IGNORECASE,
)
_OTHER_LABEL = re.compile(r"^\s*[^\n:=]{1,80}[:=]")
_CELL = re.compile(r"([A-Z]+)([1-9][0-9]*)$")


def evidence_candidates(document: DocumentEvidence) -> dict[str, list[EvidenceBlock]]:
    """Return complete selection options, retaining every original source ID."""
    candidates: dict[str, list[EvidenceBlock]] = {}
    index = 0
    while index < len(document.blocks):
        block = document.blocks[index]
        region = [block]
        index += 1
        if _PARTY_START.match(unicodedata.normalize("NFKC", block.text)):
            while index < len(document.blocks) and _continues(
                region, document.blocks[index]
            ):
                region.append(document.blocks[index])
                index += 1
        identifier = block.id if len(region) == 1 else block.id + ":region"
        candidates[identifier] = region
    return candidates


def has_omitted_continuation(
    document: DocumentEvidence, selected_ids: Sequence[str]
) -> bool:
    """A selection cannot present a fragment of a known party region as complete."""
    selected = set(selected_ids)
    for region in evidence_candidates(document).values():
        ids = {block.id for block in region}
        if selected & ids and not ids <= selected:
            return True
    return False


def complete_party_selection(
    document: DocumentEvidence, field: str, selected_id: str
) -> list[str]:
    """Expand a machine-selected party anchor to its complete located region.

    The provider still chooses the source, with its original confidence. Layout
    supplies only adjacent continuation lines; it never copies another document
    or invents missing text. Reviewer selections remain explicit and are checked
    by has_omitted_continuation instead of being silently expanded.
    """
    if selected_id == "NONE":
        return []
    if field in _PARTIES:
        for region in evidence_candidates(document).values():
            ids = [block.id for block in region]
            if selected_id in ids:
                return ids
    return [selected_id]


def _continues(region: Sequence[EvidenceBlock], following: EvidenceBlock) -> bool:
    previous = region[-1]
    text = unicodedata.normalize("NFKC", following.text)
    if _FIELD_START.match(text) or _OTHER_LABEL.match(text):
        return False
    if not previous.locations or not following.locations:
        return False
    before, after = previous.locations[-1], following.locations[0]
    if before.kind != after.kind or previous.method != following.method:
        return False
    if before.kind == "xlsx":
        return _adjacent_cells(
            [location for block in region for location in block.locations],
            following.locations,
        )
    if before.kind not in {"pdf", "image"} or before.page != after.page:
        return False
    if before.bbox is None or after.bbox is None:
        return False
    _, top, _, bottom = before.bbox
    anchor = region[0].locations[0].bbox
    if anchor is None:
        return False
    left, _, right, _ = anchor
    next_left, next_top, _, next_bottom = after.bbox
    line_height = max(bottom - top, next_bottom - next_top)
    return (
        line_height > 0
        and 0 <= next_top - bottom <= 2 * line_height
        and left - 2 <= next_left <= right + 2
    )


def _cell_position(location: Location) -> tuple[int, int] | None:
    match = _CELL.fullmatch(location.cell or "")
    if match is None:
        return None
    column = 0
    for character in match[1]:
        column = column * 26 + ord(character) - ord("A") + 1
    return int(match[2]), column


def _adjacent_cells(before: Sequence[Location], after: Sequence[Location]) -> bool:
    sheets = {location.sheet for location in (*before, *after)}
    if len(sheets) != 1 or None in sheets:
        return False
    a = [_cell_position(location) for location in before]
    b = [_cell_position(location) for location in after]
    if any(position is None for position in (*a, *b)):
        return False
    first = [position for position in a if position is not None]
    second = [position for position in b if position is not None]
    adjacent_row = min(row for row, _ in second) == max(row for row, _ in first) + 1
    first_column = min(column for _, column in first)
    last_column = max(column for _, column in first)
    next_column = min(column for _, column in second)
    return adjacent_row and first_column <= next_column <= last_column
