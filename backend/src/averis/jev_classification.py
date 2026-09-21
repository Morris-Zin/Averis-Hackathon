"""Conservative, lossless plain-text email segmentation for classification.

Public capability: prepare the same subject/body as named sections. Formatting
heuristics never discard text; ambiguous signatures and interleaved replies stay
in the current body. Source offsets permit exact reconstruction and auditing.
"""

import re
from typing import TypedDict


class _Segment(TypedDict):
    section: str
    start: int
    end: int
    text: str


HISTORY = re.compile(
    r"(?m)^(?:_{5,}|-{5,}|-{2,}\s*Original Message\s*-{2,})[^\S\n]*\n(?=From:)",
    re.IGNORECASE,
)
SIGNATURE = re.compile(
    r"(?im)^(?:best regards|kind regards|regards|sincerely|best wishes)[,.]?[^\S\n]*(?:\n|$)"
)
CONTACT = re.compile(
    r"(?im)(?:\bwebsite\s*:|\bDID\s*:|\b(?:tel|phone|mobile)\s*:|www\.|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})"
)
POSTSCRIPT = re.compile(
    r"(?im)^\s*(?:p\.?s\.?\s*:|please\b|kindly\b|also\b|one more\b|correction\s*:|note\s*:)"
)


def _segments(body: str) -> list[_Segment]:
    """Partition exact original characters; avoid retyping or normalizing names."""
    boundaries: list[tuple[int, str]] = []
    for match in HISTORY.finditer(body):
        header = body[match.end() :].split("\n\n", 1)[0]
        if re.search(r"(?m)^Sent:", header) and re.search(r"(?m)^Subject:", header):
            boundaries.append((match.start(), "quoted_history"))
            break
    quote_start = boundaries[0][0] if boundaries else len(body)
    prefix_end = 0
    first_paragraph = body[:quote_start].split("\n\n", 1)[0]
    if (
        first_paragraph.startswith("WARNING:")
        and re.search(r"email originated outside", first_paragraph, re.IGNORECASE)
        and "\n\n" in body[:quote_start]
    ):
        prefix_end = len(first_paragraph) + 2
    current = body[prefix_end:quote_start]
    signature_start = quote_start
    # Only move a trailing signature with contact evidence and no action-like
    # postscript. Otherwise leave it in body; nothing is hidden or removed.
    candidates = list(SIGNATURE.finditer(current))
    if len(candidates) == 1:
        match = candidates[0]
        tail = current[match.end() :]
        if (
            current[: match.start()].strip()
            and CONTACT.search(tail)
            and not POSTSCRIPT.search(tail)
            and len(tail.splitlines()) <= 20
        ):
            signature_start = prefix_end + match.start()
    ranges = [
        ("automatic_notice", 0, prefix_end),
        ("current_message", prefix_end, signature_start),
        ("signature", signature_start, quote_start),
        ("quoted_history", quote_start, len(body)),
    ]
    result: list[_Segment] = [
        {"section": kind, "start": start, "end": end, "text": body[start:end]}
        for kind, start, end in ranges
        if end > start
    ]
    assert "".join(p["text"] for p in result) == body
    return result


def prepare_email(subject: str, body: str) -> dict[str, str]:
    """Prepare lossless sections; ambiguous formatting stays in the body."""
    named = {part["section"]: part["text"] for part in _segments(body)}
    return {
        "subject": subject,
        "body": named.get("current_message", ""),
        "quoted_history": named.get("quoted_history", ""),
        "signature": named.get("signature", ""),
        "automatic_notices": named.get("automatic_notice", ""),
    }
