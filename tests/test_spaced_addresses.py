"""Wide line spacing must not drop street addresses or absorb nearby notes."""

import pytest

from averis.domain import DocumentEvidence, EvidenceBlock, Location
from averis.source_regions import complete_party_selection
from averis.verification import reading_from_evidence


def document(text: str, *, gap: float = 51, left: float = 66, page: int = 1):
    return DocumentEvidence(
        document_id="scan",
        blocks=[
            EvidenceBlock(
                id="name",
                text="Consignee: QUAY TRADING",
                method="ocr",
                ocr_confidence=0.94,
                locations=[Location(kind="pdf", page=1, bbox=(68, 378, 498, 402))],
            ),
            EvidenceBlock(
                id="next",
                text=text,
                method="ocr",
                ocr_confidence=0.94,
                locations=[
                    Location(
                        kind="pdf", page=page, bbox=(left, 402 + gap, 498, 426 + gap)
                    )
                ],
            ),
        ],
    )


@pytest.mark.parametrize(
    "address",
    ["80 Jalan Pasar", "52 Lorong Melati", "29 Willow Avenue", "上海市中山路88号"],
)
def test_spaced_street_address_retains_both_original_sources(address: str):
    doc = document(address)
    assert complete_party_selection(doc, "consignee", "name") == ["name", "next"]
    assert (
        reading_from_evidence("consignee", doc, ["name"]).issue
        == "incomplete_party_evidence"
    )
    complete = reading_from_evidence("consignee", doc, ["name", "next"])
    assert complete.issue is None
    assert complete.text == "Consignee: QUAY TRADING\n" + address


@pytest.mark.parametrize(
    "text",
    [
        "Release after payment",
        "123 containers pending",
        "2026 September shipment",
        "Notify Party: 80 Jalan Pasar",
        "Warehouse: 80 Jalan Pasar",
    ],
)
def test_extra_space_does_not_absorb_unrelated_text(text: str):
    assert complete_party_selection(document(text), "consignee", "name") == ["name"]


@pytest.mark.parametrize("options", [{"page": 2}, {"left": 180}, {"gap": 90}])
def test_address_marker_does_not_override_layout_boundaries(options):
    assert complete_party_selection(
        document("80 Jalan Pasar", **options), "consignee", "name"
    ) == ["name"]


def test_expanded_address_still_requires_reliable_ocr():
    doc = document("80 Jalan Pasar")
    doc.blocks[1].ocr_confidence = 0.4
    assert (
        reading_from_evidence("consignee", doc, ["name", "next"]).issue
        == "low_ocr_confidence"
    )
