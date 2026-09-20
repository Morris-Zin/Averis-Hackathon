"""Language handling must retain original evidence and reject unsafe assumptions."""

import pytest

from averis.contracts import FIELDS
from averis.documents import read_document
from averis.verification import (
    compare,
    normalize,
    reading_from_evidence,
    source_value,
    validate_pair,
)


@pytest.mark.parametrize(
    "labels,weight",
    [
        (
            [
                "托运人",
                "收货人",
                "通知方",
                "装货港",
                "卸货港",
                "集装箱数量",
                "毛重（公斤）",
            ],
            "22000 公斤",
        ),
        (
            ["託運人", "收貨人", "通知人", "裝貨港", "卸貨港", "集裝箱數量", "毛重"],
            "22 公噸",
        ),
        (
            [
                "Pengirim",
                "Penerima",
                "Pihak untuk dimaklumkan",
                "Pelabuhan muatan",
                "Pelabuhan pelepasan",
                "Bilangan kontena",
                "Berat kasar (kg)",
            ],
            "22000",
        ),
    ],
)
def test_multilingual_source_blocks_compare_without_translating_names(labels, weight):
    values = [
        "上海商贸",
        "Pacific Retail",
        "Eastern Logistics",
        "上海港",
        "巴生港",
        "3",
        weight,
    ]
    text = "Shipping Instruction\n" + "\n".join(
        f"{label}：{value}" for label, value in zip(labels, values, strict=True)
    )
    si = read_document("si", "si.txt", text.encode())
    assert len(si.blocks) == 8
    assert "\n".join(block.text for block in si.blocks) == text
    assert [block.locations[0].line_start for block in si.blocks] == list(range(1, 9))
    bl = read_document("bl", "bl.txt", text.replace("：3\n", "：4\n").encode())
    assert not validate_pair(si, bl)
    assert validate_pair(si, bl, human_selected=True)
    readings = []
    for document in [si, bl]:
        readings.append(
            {
                field: reading_from_evidence(
                    field,
                    document,
                    [
                        block.id
                        for block in document.blocks
                        if source_value(field, block.text) != block.text.strip()
                    ],
                )
                for field in FIELDS
            }
        )
    result = compare(*readings, revision=1, pair_valid=True)
    assert [f.field for f in result.findings if f.outcome == "mismatch"] == [
        "container_count"
    ]
    assert all(
        f.outcome == "match" for f in result.findings if f.field != "container_count"
    )
    assert readings[0]["gross_weight_kg"].normalized == "22000"


def test_multilingual_mixed_field_evidence_cannot_clear_a_reading():
    document = read_document("si", "si.txt", "托运人：公司甲\n收货人：公司乙".encode())
    reading = reading_from_evidence(
        "shipper", document, [b.id for b in document.blocks]
    )
    assert reading.issue == "ambiguous_source_fields"


@pytest.mark.parametrize(
    "source", ["毛重：22000", "Berat kasar: 22000", "毛重：不详", "毛重：22 tons"]
)
def test_multilingual_weight_never_guesses_missing_or_ambiguous_units(source):
    assert normalize("gross_weight_kg", source) is None


def test_fullwidth_punctuation_preserves_multiline_address():
    document = read_document(
        "si", "si.txt", "托运人：公司甲\n  上海市浦东新区\n收货人：公司乙".encode()
    )
    assert len(document.blocks) == 2
    assert document.blocks[0].text == "托运人：公司甲\n  上海市浦东新区"
    assert normalize("shipper", document.blocks[0].text) == "公司甲 上海市浦东新区"


@pytest.mark.parametrize("label", ["装运编号", "裝運編號", "Rujukan penghantaran"])
def test_localized_references_prove_pairing_but_conflicts_still_block(label):
    si = read_document("si", "si.txt", f"{label}：ABC-1234".encode())
    bl = read_document("bl", "bl.txt", b"Shipment ID: ABC-1234")
    wrong = read_document("wrong", "bl.txt", b"Shipment ID: ABC-5678")
    assert validate_pair(si, bl)
    assert not validate_pair(si, wrong, human_selected=True)
