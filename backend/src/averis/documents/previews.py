"""Private document previews implementation."""

from __future__ import annotations

import math
import multiprocessing
from importlib import import_module
from io import BytesIO
from multiprocessing.connection import Connection
from pathlib import PurePath
from typing import cast

from PIL import Image as Pillow

from averis.documents.limits import (
    IMAGE_SUFFIXES,
    MAX_DOCUMENT_BYTES,
    MAX_PDF_PAGES,
    MAX_RENDER_DIMENSION,
    MAX_RENDER_PIXELS,
)
from averis.documents.pdf import PdfiumModule
from averis.documents.process_limits import (
    acquire_child_process_tree,
    apply_child_resource_limits,
    stop_process_tree,
)


class DocumentPreviewError(RuntimeError):
    """A stable, user-safe preview failure code."""


def render_preview_bounded(
    filename: str,
    content: bytes,
    page: int = 1,
    timeout_seconds: float = 20.0,
) -> bytes:
    """Render a PDF page or image document to a bounded PNG in a child process.

    Unsupported formats, invalid pages, corrupt documents, and timeouts raise
    :class:`DocumentPreviewError` with a stable failure code suitable for an API
    error response.  No source document content is included in the error.
    """

    if not content:
        raise DocumentPreviewError("preview_empty_document")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentPreviewError(
            f"preview_document_size_limit_exceeded:{len(content)}>{MAX_DOCUMENT_BYTES}"
        )
    suffix = PurePath(filename).suffix.lower()
    if suffix != ".pdf" and suffix not in IMAGE_SUFFIXES:
        raise DocumentPreviewError(
            f"preview_unsupported_document_type:{suffix or 'none'}"
        )
    if page < 1 or page > MAX_PDF_PAGES:
        raise DocumentPreviewError(f"preview_page_out_of_range:{page}")
    if suffix in IMAGE_SUFFIXES and page != 1:
        raise DocumentPreviewError(f"preview_page_out_of_range:{page}")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise DocumentPreviewError("preview_invalid_timeout")

    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_preview_worker,
        args=(send, content, page, suffix),
        daemon=True,
    )
    process.start()
    send.close()
    try:
        if receive.poll(timeout_seconds):
            try:
                payload = receive.recv_bytes()
            except (EOFError, OSError) as exc:
                raise DocumentPreviewError("preview_renderer_failed:no_result") from exc
            if payload[:1] == b"\x00":
                return payload[1:]
            message = payload[1:].decode("utf-8", errors="replace")
            raise DocumentPreviewError(message or "preview_renderer_failed:no_result")

        raise DocumentPreviewError(f"preview_timeout:{timeout_seconds:g}s")
    finally:
        receive.close()
        stop_process_tree(process)


def _preview_worker(
    connection: Connection,
    content: bytes,
    page: int,
    suffix: str,
) -> None:
    try:
        acquire_child_process_tree()
    except OSError:
        connection.send_bytes(b"\x01preview_process_tree_isolation_unavailable")
        connection.close()
        return
    apply_child_resource_limits(20)
    try:
        try:
            preview = (
                _render_pdf_preview(content, page)
                if suffix == ".pdf"
                else _render_image_preview(content, suffix)
            )
            connection.send_bytes(b"\x00" + preview)
        except Exception as exc:  # noqa: BLE001 - isolated parser failures become safe codes.
            if isinstance(exc, DocumentPreviewError):
                issue = str(exc)
            else:
                issue = f"preview_unreadable:{type(exc).__name__}"
            connection.send_bytes(b"\x01" + issue.encode("utf-8"))
    finally:
        connection.close()


def _render_pdf_preview(content: bytes, page_number: int) -> bytes:
    pdfium = cast(PdfiumModule, import_module("pypdfium2"))

    document = pdfium.PdfDocument(content)
    try:
        if page_number > len(document):
            raise DocumentPreviewError(f"preview_page_out_of_range:{page_number}")
        page = document[page_number - 1]
        try:
            width_points, height_points = page.get_size()
            scale = min(
                150 / 72,
                MAX_RENDER_DIMENSION / max(width_points, height_points),
                math.sqrt(MAX_RENDER_PIXELS / (width_points * height_points)),
            )
            if not math.isfinite(scale) or scale <= 0:
                raise DocumentPreviewError(
                    f"preview_page_invalid_dimensions:{page_number}"
                )
            bitmap = page.render(scale=scale)  # pyright: ignore[reportArgumentType]
            try:
                image = bitmap.to_pil()
                try:
                    output = BytesIO()
                    image.save(output, format="PNG")
                    return output.getvalue()
                finally:
                    image.close()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


def _render_image_preview(content: bytes, suffix: str) -> bytes:
    expected_format = "PNG" if suffix == ".png" else "JPEG"
    with Pillow.open(BytesIO(content)) as source:
        if source.format != expected_format:
            raise DocumentPreviewError(f"preview_unreadable:invalid_{suffix[1:]}")
        width, height = source.size
        if (
            width <= 0
            or height <= 0
            or width > MAX_RENDER_DIMENSION
            or height > MAX_RENDER_DIMENSION
            or width * height > MAX_RENDER_PIXELS
        ):
            raise DocumentPreviewError(
                f"preview_image_pixel_limit_exceeded:{width}x{height}>"
                f"{MAX_RENDER_PIXELS}"
            )
        source.load()
        image = source.convert("RGB")
    try:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    finally:
        image.close()
