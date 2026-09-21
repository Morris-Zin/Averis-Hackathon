"""Template recognition must not merge arbitrary identifier namespaces."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from averis.documents import read_document
from averis.domain import DocumentEvidence
from averis.verification import validate_pair


def worksheet(role: str, reference: str = "1234567890") -> DocumentEvidence:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "S.I." if role == "si" else "BL"
    rows = [
        ("Example Trading", None),
        (None, None),
        ("BL INSTRUCTION" if role == "si" else "BILL OF LADING", reference),
        ("Shipper", "Example Trading"),
        ("Consignee", "Customer"),
        ("Notify", "Customer"),
        ("Port of Loading", "Singapore"),
        ("Port of Discharge", "Houston"),
        ("Containers", "2 x 40HC"),
        ("Gross Weight", "20000 KG"),
        ("Vessel", "Example Vessel"),
        ("Description of Goods", "Paper"),
        ("HS CODE", "48109200"),
        ("Booking No." if role == "si" else "B/L No.", "BK-1000"),
        ("FREIGHT", "PREPAID"),
    ]
    for row in rows:
        sheet.append(row)
    content = BytesIO()
    workbook.save(content)
    return read_document(role, role + ".xlsx", content.getvalue())


def test_real_worksheet_reader_preserves_order_reference_pairing() -> None:
    assert validate_pair(worksheet("si"), worksheet("bl"))


@pytest.mark.parametrize("reference", ["9876543210", "12345", "1234567890 extra"])
def test_nonmatching_or_invalid_order_reference_is_not_identity(reference: str) -> None:
    assert not validate_pair(worksheet("si"), worksheet("bl", reference))


@pytest.mark.parametrize("mutation", ["ocr", "sheet", "cell", "issue", "duplicate"])
def test_unsupported_layout_or_evidence_cannot_prove_identity(mutation: str) -> None:
    si, bl = worksheet("si"), worksheet("bl")
    header = next(b for b in bl.blocks if b.text.startswith("BILL OF LADING:"))
    if mutation == "ocr":
        header.method = "ocr"
    elif mutation == "sheet":
        header.locations[0].sheet = "Other"
    elif mutation == "cell":
        header.locations[0].cell = "A2"
    elif mutation == "issue":
        bl.issues.append("xlsx_formula_cache_unavailable")
    else:
        bl.blocks.append(header.model_copy(deep=True))
    assert not validate_pair(si, bl)


def test_order_match_cannot_hide_a_booking_conflict() -> None:
    si, bl = worksheet("si"), worksheet("bl")
    row = next(b for b in bl.blocks if b.text.startswith("B/L No."))
    row.text = "Booking No.: BK-2000"
    assert not validate_pair(si, bl)
    assert not validate_pair(si, bl, human_selected=True)


def test_conflicting_template_orders_cannot_be_human_confirmed() -> None:
    assert not validate_pair(
        worksheet("si"), worksheet("bl", "9876543210"), human_selected=True
    )
