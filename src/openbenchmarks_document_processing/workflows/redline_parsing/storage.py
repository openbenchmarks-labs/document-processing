from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def cache_key(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(hashlib.sha256((part or "").encode()).digest())
    return digest.hexdigest()


def load_cached(path: Path, key: str) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if payload.get("key") == key else None
