"""Build the pinned reference snapshot from the unchanged official release ZIP."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

SOURCE_SHA256 = "ad409fc7149b10f98d61190c34d9daf78b78bb8b31464cc66de1a89d09b01b5d"
APPROVED_STATUSES = {"AM", "AA", "AC", "AF", "AI", "AS", "RL"}


def key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def build(source: Path, destination: Path) -> None:
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Expected the pinned UN/LOCODE 2025-1 release ZIP")
    countries: dict[str, str] = {}
    names: defaultdict[str, set[str]] = defaultdict(set)
    ports: set[str] = set()
    with zipfile.ZipFile(source) as archive:
        for path in archive.namelist():
            if "csv/UNLOCODE CodeListPart" not in path:
                continue
            for row in csv.reader(io.StringIO(archive.read(path).decode("utf-8-sig"))):
                if len(row) != 12:
                    raise ValueError("Unexpected directory columns")
                marker, country, location, name, ascii_name, _, function, status, *_ = (
                    row
                )
                if not location:
                    if name.startswith("."):
                        countries[key(name[1:])] = country
                        countries[key(country)] = country
                    continue
                code = country + location
                for alias in {name, ascii_name} - {""}:
                    names[key(alias)].add(code)
                if (
                    marker != "X"
                    and function.startswith("1")
                    and status in APPROVED_STATUSES
                ):
                    ports.add(code)
    content = json.dumps(
        {
            "version": "2025-1",
            "countries": countries,
            "names": {name: sorted(codes) for name, codes in sorted(names.items())},
            "ports": sorted(ports),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    destination.write_bytes(gzip.compress(content, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build(args.source, args.destination)
