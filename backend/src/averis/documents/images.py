"""Private document images implementation."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from typing import cast

from PIL import Image as Pillow

from averis.documents.evidence import block_id, starts_evidence_field
from averis.documents.limits import MAX_RENDER_DIMENSION, MAX_RENDER_PIXELS
from averis.documents.ocr import OcrLine, read_page
from averis.domain import DocumentEvidence, EvidenceBlock, Location


def read_image(
    document_id: str,
    content: bytes,
    suffix: str,
) -> DocumentEvidence:
    result = DocumentEvidence(document_id=document_id)
    expected_format = "PNG" if suffix == ".png" else "JPEG"
    with Pillow.open(BytesIO(content)) as source:
        if source.format != expected_format:
            result.issues.append(f"document_unreadable:invalid_{suffix[1:]}")
            return result
        width, height = source.size
        if (
            width <= 0
            or height <= 0
            or width > MAX_RENDER_DIMENSION
            or height > MAX_RENDER_DIMENSION
            or width * height > MAX_RENDER_PIXELS
        ):
            result.issues.append(
                f"image_pixel_limit_exceeded:{width}x{height}>{MAX_RENDER_PIXELS}"
            )
            return result
        source.load()
        image = source.convert("RGB")
    try:
        data = read_page(image)
    finally:
        image.close()

    for block_number, (text, boxes, ocr_confidence) in enumerate(
        ocr_blocks(data), start=1
    ):
        result.blocks.append(
            EvidenceBlock(
                id=block_id(document_id, block_number),
                text=text,
                locations=[Location(kind="image", bbox=box) for box in boxes],
                method="ocr",
                ocr_confidence=ocr_confidence,
            )
        )
    if not result.blocks:
        result.issues.append("document_has_no_readable_text")
    return result


def ocr_blocks(
    recognized_lines: list[OcrLine],
    scale: float = 1.0,
) -> list[tuple[str, list[tuple[float, float, float, float]], float | None]]:
    paragraphs: dict[
        tuple[int, int],
        list[tuple[int, str, tuple[float, float, float, float], float | None]],
    ] = {}
    for line in recognized_lines:
        left, top, right, bottom = line.bbox
        paragraphs.setdefault(line.paragraph, []).append(
            (
                line.order,
                line.text,
                (left / scale, top / scale, right / scale, bottom / scale),
                line.confidence,
            )
        )

    blocks: list[tuple[str, list[tuple[float, float, float, float]], float | None]] = []
    for lines in paragraphs.values():
        lines.sort(key=lambda line: (line[0], line[2][1], line[2][0]))
        current: list[
            tuple[int, str, tuple[float, float, float, float], float | None]
        ] = []
        for line in lines:
            if current and starts_evidence_field(line[1]):
                blocks.append(_make_ocr_block(current))
                current = []
            current.append(line)
        if current:
            blocks.append(_make_ocr_block(current))
    return blocks


def _make_ocr_block(
    lines: Sequence[tuple[int, str, tuple[float, float, float, float], float | None]],
) -> tuple[str, list[tuple[float, float, float, float]], float | None]:
    confidences = [line[3] for line in lines]
    confidence = (
        min(cast(list[float], confidences))
        if confidences and all(value is not None for value in confidences)
        else None
    )
    return (
        "\n".join(line[1] for line in lines),
        [line[2] for line in lines],
        confidence,
    )
