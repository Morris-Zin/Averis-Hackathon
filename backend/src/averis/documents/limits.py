"""Private document limits implementation."""

from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024

MAX_ARCHIVE_ENTRY_BYTES = 50 * 1024 * 1024

MAX_ARCHIVE_ENTRIES = 10_000

MAX_PDF_PAGES = 20

MAX_OCR_PAGES = 3

MAX_RENDER_PIXELS = 4_000_000

MAX_RENDER_DIMENSION = 3_000

MAX_XLSX_SHEETS = 50

MAX_XLSX_ROWS_PER_SHEET = 20_000

MAX_XLSX_COLUMNS = 256

MAX_XLSX_CELLS = 200_000

DEFAULT_TIMEOUT_SECONDS = 30.0

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def check_office_archive(content: bytes) -> str | None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                return (
                    f"archive_entry_limit_exceeded:{len(entries)}>{MAX_ARCHIVE_ENTRIES}"
                )
            expanded = 0
            for entry in entries:
                if entry.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                    return (
                        "archive_member_size_limit_exceeded:"
                        f"{entry.file_size}>{MAX_ARCHIVE_ENTRY_BYTES}"
                    )
                expanded += entry.file_size
                if expanded > MAX_ARCHIVE_BYTES:
                    return f"archive_size_limit_exceeded:{expanded}>{MAX_ARCHIVE_BYTES}"
    except BadZipFile:
        return "document_unreadable:invalid_office_archive"
    return None
