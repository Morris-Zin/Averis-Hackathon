"""Private document text implementation."""

from __future__ import annotations

from averis.documents.evidence import block_id, starts_text_field
from averis.domain import DocumentEvidence, EvidenceBlock, Location


def read_text(document_id: str, content: bytes) -> DocumentEvidence:
    result = DocumentEvidence(document_id=document_id)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        result.issues.append("text_decode_failed:utf-8")
        return result

    lines = text.splitlines()
    block_number = 0
    current: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal block_number
        if not current:
            return
        block_number += 1
        result.blocks.append(
            EvidenceBlock(
                id=block_id(document_id, block_number),
                text="\n".join(line for _, line in current),
                locations=[
                    Location(kind="text", line_start=number, line_end=number)
                    for number, _ in current
                ],
            )
        )
        current.clear()

    for number, line in enumerate(lines, start=1):
        if line.strip():
            if current and starts_text_field(line):
                flush()
            current.append((number, line))
        else:
            flush()
    flush()
    if not result.blocks:
        result.issues.append("document_has_no_readable_text")
    return result
