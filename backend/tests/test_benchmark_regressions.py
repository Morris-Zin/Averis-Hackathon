"""General regressions discovered by the frozen accuracy benchmark."""

from pathlib import Path

import pytest

from averis.documents import read_document
from averis.documents.pdf import _pdf_lines
from averis.domain import DocumentEvidence, EvidenceBlock, Location
from averis.source_regions import evidence_candidates
from averis.verification import compare, normalize, reading_from_evidence


@pytest.mark.parametrize("separator", [":", "=", "："])
def test_compound_notify_label_is_one_field(separator: str) -> None:
    text = (
        f"Notify Party/Intermediate Consignee{separator} HARBOUR AGENCY\n42 Pier Road"
    )
    document = DocumentEvidence(
        document_id="source",
        blocks=[
            EvidenceBlock(
                id="party",
                text=text,
                locations=[Location(kind="text", line_start=1, line_end=2)],
            )
        ],
    )
    reading = reading_from_evidence("notify_party", document, ["party"])
    assert reading.issue is None
    assert reading.normalized == "harbour agency 42 pier road"
    assert reading.text == text


@pytest.mark.parametrize(
    "text",
    [
        "Notify Party: HARBOUR Consignee: BUYER",
        "Notify Party/Intermediate Consignee: HARBOUR Consignee: BUYER",
        "Notify Party/Intermediate Consignee: HARBOUR\nShipper: EXPORTER",
    ],
)
def test_separate_fields_remain_ambiguous(text: str) -> None:
    document = DocumentEvidence(
        document_id="source",
        blocks=[
            EvidenceBlock(
                id="party",
                text=text,
                locations=[Location(kind="text", line_start=1)],
            )
        ],
    )
    reading = reading_from_evidence("notify_party", document, ["party"])
    assert reading.issue == "ambiguous_source_fields"
    assert reading.normalized is None


def test_pdf_overlapping_font_runs_preserve_the_company_and_address() -> None:
    # A synthetic bold label overlaps the regular-text name by 18 points.
    # The source deliberately reproduces a common form-layout failure.
    path = Path(__file__).parent / "fixtures/font-overlap.pdf"
    document = read_document("overlap", path.name, path.read_bytes())
    assert not document.issues
    block = document.blocks[1]
    assert block.text == (
        "Notify Party/Intermediate Consignee HARBOUR AGENCY\n42 Pier Road"
    )
    assert len(block.locations) == 2
    assert all(location.bbox is not None for location in block.locations)
    reading = reading_from_evidence("notify_party", document, [block.id])
    assert reading.issue is None
    assert reading.normalized == "harbour agency 42 pier road"
    assert document.blocks[2].text == "Port of Loading: PORT KLANG"


@pytest.mark.parametrize("kind", ["pdf", "xlsx", "image"])
def test_complete_party_candidates_keep_original_source_blocks(kind: str) -> None:
    def location(row: int) -> Location:
        if kind == "xlsx":
            return Location(kind="xlsx", sheet="Shipment", cell=f"A{row}")
        return Location(
            kind="pdf" if kind == "pdf" else "image",
            page=1 if kind == "pdf" else None,
            bbox=(40, row * 26, 220, row * 26 + 12),
        )

    document = DocumentEvidence(
        document_id="source",
        blocks=[
            EvidenceBlock(
                id="name", text="Consignee: QUAY TRADING", locations=[location(1)]
            ),
            EvidenceBlock(
                id="address", text="80 Market Street", locations=[location(2)]
            ),
            EvidenceBlock(
                id="next", text="Port of Loading: PORT KLANG", locations=[location(3)]
            ),
        ],
    )
    original = document.model_dump()
    candidates = evidence_candidates(document)
    assert [block.id for block in candidates["name:region"]] == ["name", "address"]
    assert "name" not in candidates
    assert document.model_dump() == original
    partial = reading_from_evidence("consignee", document, ["name"])
    assert partial.issue == "incomplete_party_evidence"
    assert partial.normalized is None
    complete = reading_from_evidence("consignee", document, ["name", "address"])
    assert complete.issue is None
    assert complete.normalized == "quay trading 80 market street"


@pytest.mark.parametrize(
    "following",
    [
        "Remarks: RELEASE AFTER PAYMENT",
        "Vessel OCEAN STAR",
        "Consignee: BUYER",
        "Unfamiliar Field: VALUE",
    ],
)
def test_party_region_does_not_consume_following_fields(following: str) -> None:
    document = DocumentEvidence(
        document_id="source",
        blocks=[
            EvidenceBlock(
                id="name",
                text="Shipper: QUAY TRADING",
                locations=[Location(kind="pdf", page=1, bbox=(40, 20, 220, 32))],
            ),
            EvidenceBlock(
                id="next",
                text=following,
                locations=[Location(kind="pdf", page=1, bbox=(40, 46, 220, 58))],
            ),
        ],
    )
    assert list(evidence_candidates(document)) == ["name", "next"]
    assert (
        reading_from_evidence("shipper", document, ["name"]).normalized
        == "quay trading"
    )


@pytest.mark.parametrize("second_page,left", [(2, 40), (1, 350)])
def test_party_regions_do_not_cross_pages_or_columns(
    second_page: int, left: int
) -> None:
    document = DocumentEvidence(
        document_id="source",
        blocks=[
            EvidenceBlock(
                id="name",
                text="Shipper: QUAY",
                locations=[Location(kind="pdf", page=1, bbox=(40, 20, 220, 32))],
            ),
            EvidenceBlock(
                id="next",
                text="UNRELATED",
                locations=[
                    Location(
                        kind="pdf", page=second_page, bbox=(left, 46, left + 100, 58)
                    )
                ],
            ),
        ],
    )
    assert list(evidence_candidates(document)) == ["name", "next"]


def test_correcting_another_field_cannot_hide_an_omitted_address_difference() -> None:
    def readings(address: str):
        document = DocumentEvidence(
            document_id=address,
            blocks=[
                EvidenceBlock(
                    id="name",
                    text="Consignee: QUAY",
                    locations=[Location(kind="xlsx", sheet="S", cell="A1")],
                ),
                EvidenceBlock(
                    id="address",
                    text=address,
                    locations=[Location(kind="xlsx", sheet="S", cell="A2")],
                ),
            ],
        )
        values = {
            "shipper": "EXPORTER",
            "notify_party": "AGENT",
            "port_of_loading": "PORT KLANG",
            "port_of_discharge": "SINGAPORE",
            "container_count": "3",
            "gross_weight_kg": "22000 KG",
        }
        for field, value in values.items():
            document.blocks.append(
                EvidenceBlock(
                    id=field,
                    text=value,
                    locations=[Location(kind="text", line_start=1)],
                )
            )
        result = {
            field: reading_from_evidence(field, document, [field]) for field in values
        }
        result["consignee"] = reading_from_evidence("consignee", document, ["name"])
        return result, document

    si, si_document = readings("80 Market Street")
    bl, bl_document = readings("81 Market Street")
    report = compare(si, bl, 1, True)
    assert [f.outcome for f in report.findings].count("match") == 6
    assert (
        next(f for f in report.findings if f.field == "consignee").outcome
        == "unresolved"
    )
    si["consignee"] = reading_from_evidence(
        "consignee", si_document, ["name", "address"]
    )
    bl["consignee"] = reading_from_evidence(
        "consignee", bl_document, ["name", "address"]
    )
    report = compare(si, bl, 2, True)
    assert (
        next(f for f in report.findings if f.field == "consignee").outcome == "mismatch"
    )


def test_malay_loading_label_and_port_placeholders() -> None:
    assert normalize("port_of_loading", "Pelabuhan muat: Pelabuhan Klang") == normalize(
        "port_of_loading", "Port of Loading: Pelabuhan Klang"
    )
    assert normalize("port_of_discharge", "Port of Discharge: TBA") is None
    assert normalize("shipper", "TBA") == "tba"


def test_font_change_inside_a_company_name_does_not_add_a_space() -> None:
    words = [
        {
            "text": "HAR",
            "x0": 40,
            "x1": 60,
            "top": 20,
            "bottom": 32,
            "fontname": "Helvetica-Bold",
        },
        {
            "text": "BOUR",
            "x0": 60,
            "x1": 88,
            "top": 20,
            "bottom": 32,
            "fontname": "Helvetica",
        },
        {
            "text": "AGENCY",
            "x0": 91,
            "x1": 140,
            "top": 20,
            "bottom": 32,
            "fontname": "Helvetica",
        },
    ]
    assert _pdf_lines(words) == [("HARBOUR AGENCY", (40, 20, 140, 32))]
