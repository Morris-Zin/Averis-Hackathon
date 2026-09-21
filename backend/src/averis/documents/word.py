"""Private document word implementation."""

from __future__ import annotations

import re
import unicodedata

from averis.documents.evidence import block_id, starts_text_field
from averis.domain import DocumentEvidence, EvidenceBlock, Location
from averis.fields import FIELD_ALIASES as _SHARED_FIELD_ALIASES


def read_docx(document_id: str, content: bytes) -> DocumentEvidence:
    from averis.documents.word_structure import read_word_content

    result = DocumentEvidence(document_id=document_id)
    document = read_word_content(content)
    result.issues.extend(document.issues)
    block_number = 0
    field_paragraphs: list[EvidenceBlock] = []

    def flush_field() -> None:
        if not field_paragraphs:
            return
        first = field_paragraphs[0]
        result.blocks.append(
            first.model_copy(
                update={
                    "text": "\n".join(block.text for block in field_paragraphs),
                    "locations": [
                        location
                        for block in field_paragraphs
                        for location in block.locations
                    ],
                }
            )
        )
        field_paragraphs.clear()

    for item in document.items:
        if item.boundary:
            flush_field()
            continue
        if item.table:
            flush_field()
            cell_texts: list[str] = []
            locations: list[Location] = []
            for cell in item.cells:
                paragraphs: list[str] = []
                for paragraph in cell:
                    if paragraph.text.strip():
                        paragraphs.append(paragraph.text)
                        locations.append(
                            Location(kind="docx", paragraph=paragraph.number)
                        )
                if paragraphs:
                    cell_texts.append("\n".join(paragraphs))
            if cell_texts:
                block_number += 1
                result.blocks.append(
                    EvidenceBlock(
                        id=block_id(document_id, block_number),
                        text=" | ".join(cell_texts),
                        locations=locations,
                    )
                )
        else:
            paragraph = item.cells[0][0]
            if paragraph.text.strip():
                block_number += 1
                block = EvidenceBlock(
                    id=block_id(document_id, block_number),
                    text=paragraph.text,
                    locations=[Location(kind="docx", paragraph=paragraph.number)],
                )
                label_only = any(
                    re.fullmatch(
                        r"\s*" + re.escape(label) + r"\s*:?[ \t]*",
                        paragraph.text,
                        re.IGNORECASE,
                    )
                    for aliases in _SHARED_FIELD_ALIASES.values()
                    for label in aliases
                )
                if starts_text_field(paragraph.text) or label_only:
                    flush_field()
                party_label = any(
                    re.match(
                        r"^\s*" + re.escape(label) + r"(?=\s|[:=|]|$)",
                        unicodedata.normalize("NFKC", paragraph.text),
                        re.IGNORECASE,
                    )
                    for field in ("shipper", "consignee", "notify_party")
                    for label in _SHARED_FIELD_ALIASES[field]
                )
                ambiguous_label_only = (
                    re.fullmatch(
                        r"\s*container\s+(?:number|no\.?|id)\s*[:=|]?\s*",
                        unicodedata.normalize("NFKC", paragraph.text),
                        re.IGNORECASE,
                    )
                    is not None
                )
                if party_label or ambiguous_label_only or field_paragraphs:
                    field_paragraphs.append(block)
                else:
                    result.blocks.append(block)

    flush_field()

    if not result.blocks:
        result.issues.append("document_has_no_readable_text")
    return result
