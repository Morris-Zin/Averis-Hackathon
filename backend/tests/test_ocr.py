"""OCR routing and source confidence must not turn bad readings into matches."""

from types import SimpleNamespace

import pytest
from PIL import Image

from averis import ocr


def line(text: str) -> ocr.OcrLine:
    return ocr.OcrLine(text, (0, 0, 20, 10), 0.91, (1, 1), 1)


@pytest.mark.parametrize(
    ("probe", "expected"),
    [("Shipper: Example Ltd", "eng"), ("PENGIRIM: A\nPenerima: B", "eng+msa")],
)
def test_latin_routing_keeps_the_selected_tesseract_reading(
    monkeypatch, probe, expected
):
    calls = []
    accepted = [line("source reading")]

    def recognize(image, language):
        calls.append(language)
        return [line(probe)] if len(calls) == 1 else accepted

    monkeypatch.setattr(ocr, "_tesseract_lines", recognize)
    monkeypatch.setattr(
        ocr, "_chinese_lines", lambda _: pytest.fail("Unexpected engine")
    )
    with Image.new("RGB", (30, 30)) as image:
        assert ocr.read_page(image) is accepted
    assert calls == ["eng+msa+chi_sim+chi_tra", expected]


def test_chinese_routing_retains_original_recognizer_text(monkeypatch):
    accepted = [line("发货人：晨光公司")]
    monkeypatch.setattr(ocr, "_tesseract_lines", lambda *_: [line("发货人收货人")])
    monkeypatch.setattr(ocr, "_chinese_lines", lambda _: accepted)
    with Image.new("RGB", (30, 30)) as image:
        assert ocr.read_page(image) is accepted


def characters(text, low_character=None):
    return [(char, 0.2 if char == low_character else 0.99, []) for char in text]


@pytest.mark.parametrize(
    "text,uncertain",
    [
        ("Weight: 18.75 kg", "."),
        ("Shipper: A-B", "-"),
        ("Consignee: A (HK)", "("),
        ("装货港：上海港", "装"),
    ],
)
def test_uncertain_value_punctuation_and_label_letters_are_not_averaged_away(
    text, uncertain
):
    assert ocr._character_confidence(text, characters(text, uncertain)) == 0.2


def test_only_structural_label_punctuation_is_excluded_from_confidence():
    text = "Gross Weight (kg): 18750"
    assert ocr._character_confidence(text, characters(text, "(")) == 0.99
    assert ocr._character_confidence(text, characters(text, ":")) == 0.99


@pytest.mark.parametrize(
    "words", [None, [], [("18", 0.99, [])], [("18750", float("nan"), [])]]
)
def test_missing_or_invalid_character_scores_remain_unknown(words):
    assert ocr._character_confidence("18750", words) is None


class Boxes:
    def __init__(self, polygon):
        self.polygon = polygon

    def tolist(self):
        return [self.polygon]


def test_chinese_source_region_and_weakest_character_survive_adapter(monkeypatch):
    text = "毛重：18.75公斤"
    output = SimpleNamespace(
        txts=[text],
        boxes=Boxes([[2, 3], [25, 3], [25, 15], [2, 15]]),
        word_results=[characters(text, ".")],
    )
    monkeypatch.setattr(ocr, "_chinese_engine", lambda: lambda *_, **__: output)
    with Image.new("RGB", (30, 30)) as image:
        result = ocr._chinese_lines(image)
    assert result == [ocr.OcrLine(text, (2, 3, 25, 15), 0.2, (1, 1), 0)]


def test_out_of_image_source_region_is_rejected(monkeypatch):
    output = SimpleNamespace(
        txts=["甲"],
        boxes=Boxes([[-1, 0], [20, 0], [20, 10], [-1, 10]]),
        word_results=[characters("甲")],
    )
    monkeypatch.setattr(ocr, "_chinese_engine", lambda: lambda *_, **__: output)
    with (
        Image.new("RGB", (30, 30)) as image,
        pytest.raises(ValueError, match="outside"),
    ):
        ocr._chinese_lines(image)


def test_missing_bundled_models_fail_without_network_or_engine_creation(
    monkeypatch, tmp_path
):
    ocr._chinese_engine.cache_clear()
    module = SimpleNamespace(
        __file__=str(tmp_path / "__init__.py"),
        RapidOCR=lambda **_: pytest.fail("Must not initialize or download"),
    )
    monkeypatch.setattr(ocr, "import_module", lambda _: module)
    with pytest.raises(FileNotFoundError, match="Bundled"):
        ocr._chinese_engine()
    ocr._chinese_engine.cache_clear()
