"""Local OCR selection and validated text lines behind one page-reading interface.

The multilingual probe selects a recognizer, never shipment values. English
keeps its existing engine; Chinese uses a bundled recognizer with character
scores. Document grouping, source identity and comparison live elsewhere.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Protocol, TypedDict, cast

from PIL.Image import Image as PillowImage


@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: tuple[float, float, float, float]
    confidence: float | None
    paragraph: tuple[int, int]
    order: int


_HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_MALAY = re.compile(
    r"\b(?:pengirim|penerima|pelabuhan|penghantaran|muatan|kontena|berat|dimaklumkan)\b",
    re.IGNORECASE,
)


def read_page(image: PillowImage) -> list[OcrLine]:
    """Read one bounded image; unavailable engines raise to the reader boundary."""
    probe = _tesseract_lines(image, "eng+msa+chi_sim+chi_tra")
    text = "\n".join(line.text for line in probe)
    if len(_HAN.findall(text)) >= 4:
        return _chinese_lines(image)
    language = "eng+msa" if len(set(_MALAY.findall(text.casefold()))) >= 2 else "eng"
    return _tesseract_lines(image, language)


def _tesseract_lines(image: PillowImage, language: str) -> list[OcrLine]:
    engine = cast(_OcrModule, import_module("pytesseract"))
    data = _validated_ocr_data(
        engine.image_to_data(
            image, lang=language, config="--psm 6", output_type="dict", timeout=10
        )
    )
    groups: dict[tuple[int, int, int], list[int]] = {}
    for index, text in enumerate(data["text"]):
        if not str(text).strip():
            continue
        key = tuple(
            _ocr_int(data[name][index]) for name in ("block_num", "par_num", "line_num")
        )
        groups.setdefault(cast(tuple[int, int, int], key), []).append(index)
    lines: list[OcrLine] = []
    for (block, paragraph, order), indices in sorted(groups.items()):
        indices.sort(key=lambda index: _ocr_int(data["left"][index]))
        left = min(_ocr_int(data["left"][index]) for index in indices)
        top = min(_ocr_int(data["top"][index]) for index in indices)
        right = max(
            _ocr_int(data["left"][index]) + _ocr_int(data["width"][index])
            for index in indices
        )
        bottom = max(
            _ocr_int(data["top"][index]) + _ocr_int(data["height"][index])
            for index in indices
        )
        lines.append(
            OcrLine(
                " ".join(str(data["text"][index]).strip() for index in indices),
                (float(left), float(top), float(right), float(bottom)),
                _minimum_ocr_confidence(data, indices),
                (block, paragraph),
                order,
            )
        )
    return lines


class _RapidOutput(Protocol):
    txts: object
    boxes: object
    word_results: object


class _Array(Protocol):
    def tolist(self) -> object: ...


class _RapidEngine(Protocol):
    def __call__(
        self, image: PillowImage, *, return_word_box: bool, return_single_char_box: bool
    ) -> _RapidOutput: ...


def _sequence(value: object) -> list[object]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("OCR output is not a sequence")
    return list(cast(Sequence[object], value))


def _score(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    return score if math.isfinite(score) and 0 <= score <= 1 else None


def _character_confidence(text: str, words: object) -> float | None:
    """Keep every value character, including decimal points and name punctuation.

    Only a label's colon and parentheses preceding it are structural. Do not
    substitute a line-average score for an uncertain character.
    """
    if words is None:
        return None
    characters: list[tuple[str, float]] = []
    for raw in _sequence(words):
        word = _sequence(raw)
        if len(word) != 3 or not isinstance(word[0], str):
            return None
        visible = "".join(char for char in word[0] if not char.isspace())
        if not visible:
            continue
        score = _score(word[1])
        if score is None:
            return None
        characters.extend((char, score) for char in visible)
    expected = "".join(char for char in text if not char.isspace())
    if "".join(char for char, _ in characters) != expected:
        return None
    separator = next((i for i, char in enumerate(expected) if char in ":："), -1)
    scores = [
        score
        for i, (char, score) in enumerate(characters)
        if i != separator and not (i < separator and char in "()（）")
    ]
    return min(scores) if scores else None


@lru_cache(maxsize=1)
def _chinese_engine() -> _RapidEngine:
    """One engine per isolated reader process; no request-time model downloads."""
    module = import_module("rapidocr")
    if module.__file__ is None:
        raise RuntimeError("OCR package location is unavailable")
    model_directory = Path(module.__file__).parent / "models"
    models = {
        "Det.model_path": model_directory / "PP-OCRv6_det_small.onnx",
        "Cls.model_path": model_directory / "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        "Rec.model_path": model_directory / "PP-OCRv6_rec_small.onnx",
    }
    if not all(path.is_file() for path in models.values()):
        raise FileNotFoundError("Bundled OCR model is missing")
    runtime = import_module("onnxruntime")
    cast(Callable[[], None], runtime.disable_telemetry_events)()
    factory = cast(Callable[..., _RapidEngine], module.RapidOCR)
    return factory(
        params={
            **{key: str(path) for key, path in models.items()},
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Global.text_score": 0.0,
            "Global.log_level": "error",
        }
    )


def _chinese_lines(image: PillowImage) -> list[OcrLine]:
    engine = _chinese_engine()
    result = engine(image, return_word_box=True, return_single_char_box=True)
    if result.txts is None:
        return []
    texts = _sequence(result.txts)
    boxes = _sequence(cast(_Array, result.boxes).tolist())
    words = _sequence(result.word_results)
    if not len(texts) == len(boxes) == len(words):
        raise ValueError("OCR line arrays disagree")
    lines: list[OcrLine] = []
    for order, (text, polygon, characters) in enumerate(
        zip(texts, boxes, words, strict=True)
    ):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("OCR text is empty or invalid")
        points = [_sequence(point) for point in _sequence(polygon)]
        if len(points) != 4 or any(len(point) != 2 for point in points):
            raise ValueError("OCR source region is invalid")
        coordinates = [
            float(cast(float, coordinate)) for point in points for coordinate in point
        ]
        if not all(math.isfinite(coordinate) for coordinate in coordinates):
            raise ValueError("OCR source region is not finite")
        xs, ys = coordinates[::2], coordinates[1::2]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        if not (
            0 <= bbox[0] < bbox[2] <= image.width
            and 0 <= bbox[1] < bbox[3] <= image.height
        ):
            raise ValueError("OCR source region is outside the image")
        lines.append(
            OcrLine(text, bbox, _character_confidence(text, characters), (1, 1), order)
        )
    return lines


class _OcrModule(Protocol):
    def image_to_data(
        self,
        image: PillowImage,
        *,
        lang: str,
        config: str,
        output_type: str,
        timeout: int,
    ) -> object: ...


class _OcrData(TypedDict):
    text: list[object]
    conf: list[object] | None
    block_num: list[object]
    par_num: list[object]
    line_num: list[object]
    left: list[object]
    top: list[object]
    width: list[object]
    height: list[object]


def _validated_ocr_data(value: object) -> _OcrData:
    if not isinstance(value, dict):
        raise TypeError("OCR result is not a dictionary")
    mapping = cast(dict[object, object], value)

    def column(name: str) -> list[object]:
        raw = mapping.get(name)
        if not isinstance(raw, list):
            raise TypeError(f"OCR result is missing column: {name}")
        return cast(list[object], raw)

    data = _OcrData(
        text=column("text"),
        conf=column("conf") if mapping.get("conf") is not None else None,
        block_num=column("block_num"),
        par_num=column("par_num"),
        line_num=column("line_num"),
        left=column("left"),
        top=column("top"),
        width=column("width"),
        height=column("height"),
    )
    expected_length = len(data["text"])
    columns = (
        data["block_num"],
        data["par_num"],
        data["line_num"],
        data["left"],
        data["top"],
        data["width"],
        data["height"],
    )
    if data["conf"] is not None:
        columns = (*columns, data["conf"])
    if any(len(values) != expected_length for values in columns):
        raise ValueError("OCR result columns have inconsistent lengths")
    return data


def _ocr_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError("OCR coordinate is not numeric")
    return int(value)


def _minimum_ocr_confidence(data: _OcrData, indices: Sequence[int]) -> float | None:
    """Return the weakest meaningful word score, or unknown if any score is unsafe.

    Tesseract reports confidence per word on a 0..100 scale. A block is only as
    trustworthy as its weakest nonblank word because a single corrupted number
    or place name can change a shipment finding. Missing, non-finite, sentinel,
    or out-of-range scores make the aggregate unknown instead of optimistic.
    """

    raw_confidences = data["conf"]
    if raw_confidences is None or not indices:
        return None
    confidences: list[float] = []
    for index in indices:
        raw = raw_confidences[index]
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return None
        try:
            confidence = float(raw)
        except ValueError:
            return None
        if not math.isfinite(confidence) or not 0 <= confidence <= 100:
            return None
        confidences.append(confidence / 100)
    return min(confidences) if confidences else None
