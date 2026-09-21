"""Private document pdf implementation."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from importlib import import_module
from io import BytesIO
from typing import Any, Protocol, cast

from PIL.Image import Image as PillowImage

from averis.documents.evidence import block_id, starts_evidence_field
from averis.documents.images import ocr_blocks
from averis.documents.limits import (
    MAX_OCR_PAGES,
    MAX_PDF_PAGES,
    MAX_RENDER_DIMENSION,
    MAX_RENDER_PIXELS,
)
from averis.documents.ocr import read_page
from averis.domain import DocumentEvidence, EvidenceBlock, Location


class _PdfBitmap(Protocol):
    def to_pil(self) -> PillowImage: ...

    def close(self) -> None: ...


class _PdfPage(Protocol):
    def get_size(self) -> tuple[float, float]: ...

    def render(self, *, scale: float) -> _PdfBitmap: ...

    def close(self) -> None: ...


class _PdfDocument(Protocol):
    def __len__(self) -> int: ...

    def __getitem__(self, page: int) -> _PdfPage: ...

    def close(self) -> None: ...


class PdfiumModule(Protocol):
    PdfDocument: Callable[[bytes], _PdfDocument]


def read_pdf(document_id: str, content: bytes) -> DocumentEvidence:
    import pdfplumber

    result = DocumentEvidence(document_id=document_id)
    ocr_candidates: list[int] = []
    block_number = 0

    with pdfplumber.open(BytesIO(content)) as pdf:
        page_count = len(pdf.pages)
        if page_count > MAX_PDF_PAGES:
            result.issues.append(
                f"pdf_page_limit_exceeded:{page_count}>{MAX_PDF_PAGES}"
            )
        for page_number, page in enumerate(pdf.pages[:MAX_PDF_PAGES], start=1):
            words = page.extract_words(
                x_tolerance=2,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=False,
                # Preserve font runs before spatial grouping. A bold form label
                # may overlap its regular-text value; merging their characters
                # first can corrupt both the label and a company name.
                extra_attrs=["fontname"],
            )
            line_groups = _pdf_lines(words)
            readable = sum(len(line[0].strip()) for line in line_groups)
            # A selectable heading does not make the scanned body readable.
            # Large page images with sparse native text need the OCR path too.
            large_image = any(
                abs(float(image["x1"]) - float(image["x0"]))
                * abs(float(image["bottom"]) - float(image["top"]))
                > float(page.width) * float(page.height) * 0.25
                for image in page.images
            )
            if readable < 4 or (large_image and readable < 200):
                ocr_candidates.append(page_number)
                continue
            for text, locations in _pdf_blocks(line_groups, page_number):
                block_number += 1
                result.blocks.append(
                    EvidenceBlock(
                        id=block_id(document_id, block_number),
                        text=text,
                        locations=locations,
                    )
                )

    if ocr_candidates:
        if len(ocr_candidates) > MAX_OCR_PAGES:
            result.issues.append(
                f"pdf_ocr_page_limit_exceeded:{len(ocr_candidates)}>{MAX_OCR_PAGES}"
            )
        try:
            ocr_blocks, ocr_issues = _ocr_pdf_pages(
                document_id,
                content,
                ocr_candidates[:MAX_OCR_PAGES],
                block_number,
            )
            result.blocks.extend(ocr_blocks)
            result.issues.extend(ocr_issues)
        except Exception as exc:  # noqa: BLE001 - OCR failures are explicit.
            result.issues.append(f"pdf_ocr_unavailable:{type(exc).__name__}")

    if not result.blocks:
        result.issues.append("document_has_no_readable_text")
    return result


def _pdf_lines(
    words: Sequence[dict[str, Any]],
) -> list[tuple[str, tuple[float, float, float, float]]]:
    ordered = sorted(words, key=lambda word: (float(word["top"]), float(word["x0"])))
    rows: list[list[dict[str, Any]]] = []
    for word in ordered:
        if not rows or abs(float(word["top"]) - float(rows[-1][0]["top"])) > 3:
            rows.append([word])
        else:
            rows[-1].append(word)

    lines: list[tuple[str, tuple[float, float, float, float]]] = []
    for row in rows:
        row.sort(key=lambda word: float(word["x0"]))
        text = _pdf_line_text(row)
        if not text:
            continue
        lines.append(
            (
                text,
                (
                    min(float(word["x0"]) for word in row),
                    min(float(word["top"]) for word in row),
                    max(float(word["x1"]) for word in row),
                    max(float(word["bottom"]) for word in row),
                ),
            )
        )
    return lines


def _pdf_line_text(words: Sequence[dict[str, Any]]) -> str:
    """Rejoin touching font fragments, never overlapping label/value runs."""
    parts: list[str] = []
    previous: dict[str, Any] | None = None
    for word in words:
        text = str(word["text"])
        touching_font_change = (
            previous is not None
            and previous.get("fontname") != word.get("fontname")
            and -0.25 <= float(word["x0"]) - float(previous["x1"]) <= 0.5
            and str(previous["text"])[-1:].isalnum()
            and text[:1].isalnum()
        )
        parts.append(("" if touching_font_change or not parts else " ") + text)
        previous = word
    return "".join(parts).strip()


def _pdf_blocks(
    lines: Sequence[tuple[str, tuple[float, float, float, float]]],
    page_number: int,
) -> Iterable[tuple[str, list[Location]]]:
    current: list[tuple[str, tuple[float, float, float, float]]] = []
    previous_bottom: float | None = None
    for line in lines:
        top = line[1][1]
        if current and (
            starts_evidence_field(line[0])
            or (previous_bottom is not None and top - previous_bottom > 12)
        ):
            yield _make_pdf_block(current, page_number)
            current = []
        current.append(line)
        previous_bottom = line[1][3]
    if current:
        yield _make_pdf_block(current, page_number)


def _make_pdf_block(
    lines: Sequence[tuple[str, tuple[float, float, float, float]]],
    page_number: int,
) -> tuple[str, list[Location]]:
    return (
        "\n".join(line[0] for line in lines),
        [Location(kind="pdf", page=page_number, bbox=line[1]) for line in lines],
    )


def _ocr_pdf_pages(
    document_id: str,
    content: bytes,
    page_numbers: Sequence[int],
    starting_block_number: int,
) -> tuple[list[EvidenceBlock], list[str]]:
    pdfium = cast(PdfiumModule, import_module("pypdfium2"))

    blocks: list[EvidenceBlock] = []
    issues: list[str] = []
    block_number = starting_block_number
    document = pdfium.PdfDocument(content)
    try:
        for page_number in page_numbers:
            page = document[page_number - 1]
            try:
                width_points, height_points = page.get_size()
                scale = min(
                    200 / 72,
                    MAX_RENDER_DIMENSION / max(width_points, height_points),
                    math.sqrt(MAX_RENDER_PIXELS / (width_points * height_points)),
                )
                if not math.isfinite(scale) or scale <= 0:
                    issues.append(f"pdf_page_invalid_dimensions:{page_number}")
                    continue
                bitmap = page.render(scale=scale)  # pyright: ignore[reportArgumentType]
                try:
                    image = bitmap.to_pil()
                    try:
                        data = read_page(image)
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()

            page_blocks = ocr_blocks(data, scale)
            if not page_blocks:
                issues.append(f"pdf_page_unreadable:{page_number}")
                continue
            for text, boxes, ocr_confidence in page_blocks:
                block_number += 1
                blocks.append(
                    EvidenceBlock(
                        id=block_id(document_id, block_number),
                        text=text,
                        locations=[
                            Location(kind="pdf", page=page_number, bbox=box)
                            for box in boxes
                        ],
                        method="ocr",
                        ocr_confidence=ocr_confidence,
                    )
                )
    finally:
        document.close()
    return blocks, issues
