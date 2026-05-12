from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .secrets import assert_no_secrets

CSV_COLUMNS = [
    "trade_id",
    "symbol",
    "direction",
    "entry",
    "sl",
    "exit",
    "reason",
    "pnl",
    "pnl_pct",
    "size",
    "opened_at",
    "closed_at",
    "sl_distance",
    "sl_distance_pct",
    "atr14",
    "sl_atr_ratio",
    "mae_pct",
    "mfe_pct",
    "journal_present",
    "entry_score",
    "sl_score",
    "rr_score",
    "overall_score",
    "outcome",
    "audit_present",
    "trace_id_used",
]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Any) -> float | None:
    d = _decimal(value)
    return float(d) if d is not None else None


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _notes(row: dict[str, Any]) -> dict[str, Any]:
    notes = row.get("notes") or {}
    if isinstance(notes, str):
        try:
            parsed = json.loads(notes)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return notes if isinstance(notes, dict) else {}


def enrich_row(row: dict[str, Any], journal_entries: dict[str, Any] | None = None) -> dict[str, Any]:
    out = dict(row)
    notes = _notes(row)
    entry = _decimal(out.get("entry"))
    sl = _decimal(out.get("sl"))
    if entry is not None and sl is not None:
        dist = abs(entry - sl)
        out["sl_distance"] = float(dist)
        out["sl_distance_pct"] = float((dist / entry) * Decimal("100")) if entry != 0 else None
    else:
        out.setdefault("sl_distance", None)
        out.setdefault("sl_distance_pct", None)

    atr = _float(out.get("atr14"))
    if atr is None:
        atr = _float(notes.get("atr_14h") or notes.get("atr14"))
    out["atr14"] = atr
    if out.get("sl_distance") is not None and atr and atr != 0:
        out["sl_atr_ratio"] = float(out["sl_distance"]) / atr
    else:
        out.setdefault("sl_atr_ratio", None)

    tid = str(out.get("trade_id") or "")
    journal_entries = journal_entries or {}
    journal = journal_entries.get(tid)
    if journal:
        out["mae_pct"] = journal.mae_pct
        out["mfe_pct"] = journal.mfe_pct
        out["journal_present"] = True
    else:
        out.setdefault("mae_pct", None)
        out.setdefault("mfe_pct", None)
        out.setdefault("journal_present", False)

    out["audit_present"] = any(out.get(k) is not None for k in ("entry_score", "sl_score", "rr_score", "overall_score"))
    out["trace_id_used"] = bool(notes.get("trace_id_used")) if "trace_id_used" in notes else ""
    out["pnl"] = out.get("pnl", out.get("pnl_usdt"))
    return out


def _stable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (str(r.get("closed_at") or ""), str(r.get("trade_id") or "")))


def write_csv(rows: list[dict[str, Any]], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    enriched = [enrich_row(r) for r in rows]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in _stable_rows(enriched):
            writer.writerow({col: _fmt(row.get(col)) for col in CSV_COLUMNS})
    assert_no_secrets(path.read_text(encoding="utf-8"))


def _sum(values: list[Any]) -> float:
    return sum(float(v) for v in values if _float(v) is not None)


def render_summary(rows: list[dict[str, Any]], warnings: list[str]) -> str:
    enriched = [enrich_row(r) for r in rows]
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        by_symbol[str(row.get("symbol") or "UNKNOWN")].append(row)

    lines: list[str] = [
        "# Phase 0 SL Evidence Summary",
        "",
        "Verdict owner: Utku. This report intentionally does not decide H1/H2/H3/H4 dominance.",
        "",
        "## Warnings",
    ]
    if warnings:
        lines.extend(f"- {w}" for w in sorted(set(warnings)))
    else:
        lines.append("- None")

    total = len(enriched)
    audit_count = sum(1 for r in enriched if r.get("audit_present"))
    journal_count = sum(1 for r in enriched if r.get("journal_present"))
    lines += [
        "",
        "## Overall",
        f"- Closed trades: {total}",
        f"- Audit coverage: {audit_count}/{total}",
        f"- Journal coverage: {journal_count}/{total}",
        f"- Net PnL: {_sum([r.get('pnl') for r in enriched]):.4f}",
        "",
        "## Per-symbol aggregates",
        "| Symbol | Trades | Net PnL | Wins | Losses | Audit coverage | Journal coverage |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for sym in sorted(by_symbol):
        rs = by_symbol[sym]
        wins = sum(1 for r in rs if (_float(r.get("pnl")) or 0) > 0)
        losses = sum(1 for r in rs if (_float(r.get("pnl")) or 0) < 0)
        audits = sum(1 for r in rs if r.get("audit_present"))
        journals = sum(1 for r in rs if r.get("journal_present"))
        lines.append(f"| {sym} | {len(rs)} | {_sum([r.get('pnl') for r in rs]):.4f} | {wins} | {losses} | {audits}/{len(rs)} | {journals}/{len(rs)} |")

    reconciled = sum(1 for r in enriched if str(r.get("reason") or "").upper() in {"RECONCILED", "MANUAL_RECONCILE"})
    null_sl = sum(1 for r in enriched if _float(r.get("sl")) in (None, 0.0))
    op_fil = [r for r in enriched if str(r.get("symbol")) in {"OP/USDT", "FIL/USDT"}]
    lines += [
        "",
        "## H1 indicator — protection failure",
        f"- Reconciled/manual close count: {reconciled}",
        f"- NULL/zero SL count: {null_sl}",
        "",
        "## H2 indicator — SL price logic",
        f"- Rows with SL/ATR ratio: {sum(1 for r in enriched if r.get('sl_atr_ratio') not in (None, ''))}",
        f"- OP+FIL rows: {len(op_fil)}; OP+FIL net PnL: {_sum([r.get('pnl') for r in op_fil]):.4f}",
        "",
        "## H3 indicator — strategy expectancy",
        "- Use per-symbol aggregates above to compare OP/FIL expectancy against the rest.",
        "",
        "## H4 indicator — reconcile mismatch",
        "- Compare bot PnL columns against external Binance/accounting data outside this read-only script.",
        "",
        "## Decision matrix",
        "| Hypothesis | Evidence | Utku verdict |",
        "|---|---|---|",
        "| H1 | See H1 indicator section | TBD by Utku |",
        "| H2 | See H2 indicator section | TBD by Utku |",
        "| H3 | See H3 indicator section | TBD by Utku |",
        "| H4 | See H4 indicator section | TBD by Utku |",
        "",
    ]
    text = "\n".join(lines)
    assert_no_secrets(text)
    return text


def write_summary(rows: list[dict[str, Any]], path: str | Path, warnings: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_summary(rows, warnings), encoding="utf-8")
