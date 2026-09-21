"""Conservative location identity lookup over one immutable UN/LOCODE snapshot.

The complete value must resolve independently on each side. Unknown qualifiers,
terminals, ambiguous names and contradictory codes cannot establish equivalence.
The snapshot is a bundled cache of the private R2 reference artifact: comparisons
perform no network requests and updates require an explicit versioned release.
"""

import gzip
import hashlib
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

VERSION = "2025-1"
SNAPSHOT_SHA256 = "d6128c5469b2dc59fff48df348a003e672bca70631383b7a236c6dc5369496d6"
_CODE_SUFFIX = re.compile(r"\s*\(([a-z]{2}[a-z2-9]{3})\)$")
_LOG = logging.getLogger(__name__)


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class _Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    countries: dict[str, str]
    names: dict[str, list[str]]
    ports: list[str]


class PortDirectory:
    """Own name ambiguity and whole-value validation; expose proven equivalence."""

    def __init__(self, content: bytes):
        if hashlib.sha256(content).hexdigest() != SNAPSHOT_SHA256:
            raise ValueError("Port directory checksum mismatch")
        snapshot = _Snapshot.model_validate_json(gzip.decompress(content))
        if snapshot.version != VERSION:
            raise ValueError("Port directory version mismatch")
        self._countries = snapshot.countries
        self._names = snapshot.names
        self._ports = frozenset(snapshot.ports)

    def equivalent_code(self, left: str, right: str) -> str | None:
        """Return a corroborated location code, or abstain without guessing."""
        code = self._resolve(left)
        return code if code is not None and code == self._resolve(right) else None

    def _resolve(self, text: str) -> str | None:
        value = _key(text)
        if value.upper() in self._ports:
            named_locations = self._names.get(value, [])
            if named_locations and set(named_locations) != {value.upper()}:
                return None
            return value.upper()
        code: str | None = None
        if suffix := _CODE_SUFFIX.search(value):
            code = suffix[1].upper()
            value = value[: suffix.start()].strip()
            if code not in self._ports:
                return None
        country: str | None = None
        if "," in value:
            name, qualifier = value.rsplit(",", 1)
            country = self._countries.get(qualifier.strip())
            if country:
                value = name.strip()
        candidates = self._names.get(value, [])
        if country:
            candidates = [item for item in candidates if item.startswith(country)]
        if len(candidates) != 1:
            return None
        resolved = candidates[0]
        if resolved not in self._ports or (code is not None and code != resolved):
            return None
        return resolved


@lru_cache(maxsize=1)
def bundled_directory() -> PortDirectory | None:
    """A damaged/missing cache disables alias matching, never manufactures it."""
    path = Path(__file__).parent / "reference_data" / f"unlocode-{VERSION}.json.gz"
    try:
        return PortDirectory(path.read_bytes())
    except (OSError, ValueError, EOFError):
        _LOG.error("port_directory_unavailable", extra={"version": VERSION})
        return None
