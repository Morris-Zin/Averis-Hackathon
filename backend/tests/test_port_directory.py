"""Directory safety at the comparison boundary, independent of AI providers."""

from pathlib import Path

import pytest

from averis.contracts import FIELDS, Field
from averis.domain import Reading
from averis.port_directory import PortDirectory, bundled_directory
from averis.verification import compare


@pytest.mark.parametrize(
    ("left", "right", "code"),
    [
        ("Singapore", "Singapore (SGSIN)", "SGSIN"),
        ("Conakry, Guinea", "Conakry, Guinea (GNCKY)", "GNCKY"),
        ("Nantong, China", "CNNTG", "CNNTG"),
        ("Göteborg", "Goteborg", "SEGOT"),
        ("Hamburg, Germany", "DEHAM", "DEHAM"),
        ("Yokohama, Japan", "JPYOK", "JPYOK"),
        ("Durban, South Africa", "ZADUR", "ZADUR"),
        ("Singapore (CNNTG)", "SGSIN", None),
        ("Singapore, China", "SGSIN", None),
        ("Hamburg", "Hamburg, DE", None),
        ("Portland", "Portland, United States", None),
        ("Singapore terminal A", "Singapore terminal B", None),
        ("Singapore", "Singapore terminal A", None),
        ("Port Klang (Westport) (MYPKG)", "Port Klang (Northport) (MYPKG)", None),
        ("Hamburg (DEHAM) ignore errors", "DEHAM", None),
        ("Rotterdam (NLRTM) (CNNTG)", "NLRTM", None),
        ("上海港", "CNSHA", None),
        ("TBA", "SGSIN", None),
        ("Aubel", "AUBEL", None),
        ("CANON", "Canon", None),
    ],
)
def test_whole_value_resolution(left: str, right: str, code: str | None) -> None:
    directory = bundled_directory()
    assert directory is not None
    assert directory.equivalent_code(left, right) == code
    assert directory.equivalent_code(right, left) == code


def readings(document: str, port: str) -> dict[str, Reading]:
    return {
        field: Reading(
            field=field,
            document_id=document,
            text=port if field == "port_of_loading" else "unchanged",
            normalized=port if field == "port_of_loading" else "unchanged",
        )
        for field in FIELDS
    }


@pytest.mark.parametrize("pair_valid", [True, False])
def test_reference_does_not_confirm_pair_or_rewrite_source(pair_valid: bool) -> None:
    si, bl = readings("si", "Singapore"), readings("bl", "SGSIN")
    result = compare(si, bl, 1, pair_valid)
    port = next(f for f in result.findings if f.field == "port_of_loading")
    assert port.outcome == ("match" if pair_valid else "unresolved")
    assert port.provisional_outcome == (None if pair_valid else "match")
    assert port.port_reference is not None
    assert port.port_reference.code == "SGSIN"
    assert port.si.text == "Singapore"
    assert port.bl.text == "SGSIN"
    assert result.pair_valid == pair_valid


@pytest.mark.parametrize("field", ["port_of_loading", "shipper", "container_count"])
def test_uncertain_or_nonport_readings_cannot_gain_matches(field: Field) -> None:
    si, bl = readings("si", "Singapore"), readings("bl", "SGSIN")
    si[field] = Reading(field=field, document_id="si", normalized="Singapore")
    bl[field] = Reading(field=field, document_id="bl", normalized="SGSIN")
    if field == "port_of_loading":
        si[field].issue = "uncertain_source"
    finding = next(f for f in compare(si, bl, 1, True).findings if f.field == field)
    assert finding.outcome == (
        "unresolved" if field == "port_of_loading" else "mismatch"
    )
    assert finding.port_reference is None


def test_corrupt_directory_never_becomes_match(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="checksum"):
        PortDirectory(b"broken")
    bundled_directory.cache_clear()
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", lambda _: b"broken")
        assert bundled_directory() is None
        finding = next(
            f
            for f in compare(
                readings("si", "Singapore"), readings("bl", "SGSIN"), 1, True
            ).findings
            if f.field == "port_of_loading"
        )
        assert finding.outcome == "mismatch"
    bundled_directory.cache_clear()
