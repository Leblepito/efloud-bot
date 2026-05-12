from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JournalEntry:
    trade_id: str
    mae_pct: float | None
    mfe_pct: float | None


def _first_float(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def load_journal(path: str | Path) -> tuple[dict[str, JournalEntry], list[str]]:
    p = Path(path)
    warnings: list[str] = []
    if not p.exists():
        return {}, [f"Journal missing: {p}"]

    entries: dict[str, JournalEntry] = {}
    try:
        with p.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    warnings.append(f"Malformed journal line {lineno}: skipped")
                    continue
                trade_id = data.get("trade_id") or data.get("id")
                if not trade_id:
                    warnings.append(f"Malformed journal line {lineno}: missing trade_id")
                    continue
                entries[str(trade_id)] = JournalEntry(
                    trade_id=str(trade_id),
                    mae_pct=_first_float(data, "mae_pct", "max_adverse_excursion_pct"),
                    mfe_pct=_first_float(data, "mfe_pct", "max_favorable_excursion_pct"),
                )
    except OSError as exc:
        warnings.append(f"Journal read failed: {exc}")
    return entries, warnings
