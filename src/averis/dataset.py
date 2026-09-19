import json
import os
from pathlib import Path


def data_root() -> Path:
    return Path(os.environ.get("AVERIS_DATA_DIR", "resources/official/bundle"))


def load_emails(root: Path | None = None) -> list[dict]:
    root = root if root is not None else data_root()
    paths = sorted((root / "inbox").glob("email_*.json"))
    if not paths:
        raise FileNotFoundError(f"No inbox records found at {root / 'inbox'}")
    records = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    ids = [e["email_id"] for e in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate email IDs")
    return records
