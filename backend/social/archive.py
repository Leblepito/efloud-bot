"""JSONL archive helpers for social doctrine snapshots.

Archive data is research-only. It records public social content plus deterministic
parser output so candidate strategy hypotheses are traceable and reproducible.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _dedup_key(item: dict[str, Any], digest: str) -> str:
    source = str(item.get("source", "unknown"))
    item_id = str(item.get("id", ""))
    return f"{source}:{item_id}:{digest}"


def load_doctrine_snapshots(path: str | Path) -> list[dict[str, Any]]:
    archive_path = Path(path)
    if not archive_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with archive_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def append_doctrine_snapshot(
    path: str | Path,
    item: dict[str, Any],
    doctrine: dict[str, Any],
) -> dict[str, Any]:
    """Append a doctrine snapshot unless its dedup key already exists."""
    archive_path = Path(path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    digest = content_hash(str(item.get("content", "")))
    dedup_key = _dedup_key(item, digest)

    existing_keys = {row.get("dedup_key") for row in load_doctrine_snapshots(archive_path)}
    row = {
        "archived_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "dedup_key": dedup_key,
        "content_hash": digest,
        "item": item,
        "doctrine": doctrine,
    }
    if dedup_key in existing_keys:
        return {"written": False, "dedup_key": dedup_key, "row": row}

    tmp_path = archive_path.with_suffix(archive_path.suffix + ".tmp")
    existing = ""
    if archive_path.exists():
        existing = archive_path.read_text(encoding="utf-8")
    with tmp_path.open("w", encoding="utf-8") as fh:
        if existing:
            fh.write(existing)
            if not existing.endswith("\n"):
                fh.write("\n")
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
        fh.write("\n")
    os.replace(tmp_path, archive_path)

    return {"written": True, "dedup_key": dedup_key, "row": row}
