#!/usr/bin/env python3
"""Read-only, aggregate-only trade journal analysis.

Window: closed snapshots with exit_timestamp in [now - 7 days, now], UTC.
Naive timestamps are UTC: TradeJournal.record_exit writes UTC without tzinfo.
Journal rows are snapshots, not events. Duplicate trade IDs are excluded rather
than arbitrarily selecting one. Malformed/undated rows can affect the window.

PnL is the journal's realized_pnl, not independently verified exchange PnL;
its source label may be stale (record_entry does not refresh pnl_source on an
existing snapshot). sl_initial may also be refreshed from a mutable position SL
at close. Thus neither its initial nature nor net PnL should be assumed.

Examples:
  python scripts/analyze_trade_journal.py --journal state_1k/trade_journal.jsonl
  some_read_only_source | python scripts/analyze_trade_journal.py --journal -
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException, localcontext
import json
from pathlib import Path
import sys

UTC = timezone.utc
STOPS = {"SL", "SL_POLL"}
NON_STOPS = {"TP1", "TP2", "TP2_POLL", "MANUAL", "REVERSE", "WEAKNESS", "HEDGE_CLOSE", "KILL_SWITCH"}


def timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=UTC)
        return result.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        # Bound exponents to make calculations robust even for hostile input.
        if not result.is_finite() or (result and abs(result.adjusted()) > 100):
            return None
        return result
    except (DecimalException, ValueError):
        return None


def reject_constant(_):
    raise ValueError("non-standard JSON number")


def amount(value):
    return str(value) if value is not None else None


def metric(value):
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 12
        return str(+value)


def mean(values):
    return metric(sum(values, Decimal(0)) / len(values)) if values else None


def analyze(lines, now):
    if now.tzinfo is None:
        raise ValueError("now must have a timezone")
    now = now.astimezone(UTC)
    start = now - timedelta(days=7)
    quality = Counter()
    rows = []
    for line in lines:
        if not line.strip():
            quality["empty_lines"] += 1
            continue
        try:
            if "\ufffd" in line:
                raise ValueError("invalid UTF-8")
            row = json.loads(line, parse_float=Decimal, parse_int=Decimal, parse_constant=reject_constant)
            if not isinstance(row, dict):
                raise ValueError("not an object")
        except (ValueError, UnicodeError, RecursionError):
            quality["malformed_lines"] += 1
            continue
        rows.append(row)
    ids = Counter(row.get("trade_id") for row in rows if isinstance(row.get("trade_id"), str) and row["trade_id"].strip())
    duplicate_ids = {key for key, count in ids.items() if count > 1}
    quality["duplicate_ids"] = len(duplicate_ids)
    quality["duplicate_rows_all_time"] = sum(count for key, count in ids.items() if key in duplicate_ids)

    selected = []
    for row in rows:
        raw_exit = row.get("exit_timestamp")
        if raw_exit is None or raw_exit == "":
            if row.get("exit_reason") or row.get("exit_price") is not None:
                quality["undated_apparently_closed"] += 1
            else:
                quality["open_or_undated"] += 1
            continue
        exit_time = timestamp(raw_exit)
        if exit_time is None:
            quality["invalid_exit_timestamp"] += 1
            continue
        if exit_time > now:
            quality["future_exit_timestamp"] += 1
            continue
        if exit_time < start:
            continue
        trade_id = row.get("trade_id")
        if isinstance(trade_id, str) and trade_id in duplicate_ids:
            quality["duplicate_rows_in_window_excluded"] += 1
            continue
        if not isinstance(trade_id, str) or not trade_id.strip():
            quality["window_missing_trade_id"] += 1
        selected.append((exit_time, row))

    pnls, sl_pcts, durations = [], [], []
    pnl_sources, reasons = Counter(), Counter()
    groups = defaultdict(list)
    for exit_time, row in selected:
        pnl = number(row.get("realized_pnl"))
        if pnl is None:
            quality["window_missing_or_invalid_pnl"] += 1
        else:
            pnls.append(pnl)
            source = row.get("pnl_source")
            pnl_sources[source if source in ("exchange", "estimated") else "unknown"] += 1
        reason = row.get("exit_reason")
        reason = reason.strip().upper() if isinstance(reason, str) else ""
        if reason in STOPS:
            kind = "stop"
        elif reason in NON_STOPS:
            kind = "known_non_stop"
        elif reason == "RECONCILED":
            kind = "reconciled_unknown"
        else:
            kind = "other_or_missing_unknown"
        reasons[kind] += 1
        groups[exit_time].append(kind)
        entry, sl = number(row.get("entry_price")), number(row.get("sl_initial"))
        if entry is None or sl is None or entry <= 0 or sl <= 0:
            quality["window_missing_or_invalid_sl_distance"] += 1
        else:
            sl_pcts.append(abs(entry - sl) / entry * 100)
        entered = timestamp(row.get("entry_timestamp"))
        if entered is None or entered > exit_time:
            quality["window_missing_or_invalid_duration"] += 1
        else:
            delta = exit_time - entered
            seconds = Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000
            durations.append(seconds / 3600)

    # Mixed simultaneous timestamps have no known order; do not invent one.
    longest = current = 0
    for at in sorted(groups):
        kinds = groups[at]
        if len(kinds) > 1 and "stop" in kinds and any(k != "stop" for k in kinds):
            quality["mixed_timestamp_groups"] += 1
            longest = max(longest, 1)
            current = 0
        elif all(k == "stop" for k in kinds):
            current += len(kinds)
            longest = max(longest, current)
        else:
            current = 0

    fields = ("empty_lines", "malformed_lines", "duplicate_ids", "duplicate_rows_all_time",
              "duplicate_rows_in_window_excluded", "open_or_undated", "undated_apparently_closed",
              "invalid_exit_timestamp", "future_exit_timestamp", "window_missing_trade_id",
              "window_missing_or_invalid_pnl", "window_missing_or_invalid_sl_distance",
              "window_missing_or_invalid_duration", "mixed_timestamp_groups")
    return {
        "window_utc": {"from_inclusive": start.isoformat(), "to_inclusive": now.isoformat()},
        "closed_rows_included": len(selected),
        "pnl_usdt": {"sum_of_available": amount(sum(pnls, Decimal(0))) if pnls else None,
                     "values": len(pnls), "source_labels": {k: pnl_sources[k] for k in ("exchange", "estimated", "unknown")}},
        "exit_reason_categories": {k: reasons[k] for k in ("stop", "known_non_stop", "reconciled_unknown", "other_or_missing_unknown")},
        "stop_streak": {"max_confirmed_in_observed_window": longest, "ending_confirmed_in_observed_window": current},
        "sl_distance_pct": {"values": len(sl_pcts), "mean": mean(sl_pcts),
                            "min": metric(min(sl_pcts)) if sl_pcts else None, "max": metric(max(sl_pcts)) if sl_pcts else None},
        "holding_hours": {"values": len(durations), "mean": mean(durations),
                          "min": metric(min(durations)) if durations else None, "max": metric(max(durations)) if durations else None},
        "quality": {key: quality[key] for key in fields},
        "notes": [
            "Naive timestamps are treated as UTC, as in the journal writer; offsets are converted to UTC.",
            "PnL is the sum of available realized_pnl values, not necessarily complete or exchange-verified; source labels may be stale.",
            "SL/SL_POLL alone are classified as stop; RECONCILED and other unknown reasons do not imply stop or non-stop.",
            "Streaks use exit-time order within the window; unknown reasons and mixed ties are barriers, and malformed/undated/excluded rows may change the true sequence. Earlier history is not included.",
            "SL distance is abs(entry_price - sl_initial) / entry_price * 100; sl_initial may have been overwritten with a later SL, so original risk is not guaranteed.",
            "Durations use exit_timestamp - entry_timestamp, not bars_held. Missing/invalid values are excluded rather than zero-filled; statistics are rounded to 12 significant digits.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--journal", default="state_1k/trade_journal.jsonl", help="journal path, or - for stdin")
    parser.add_argument("--now", help="optional ISO-8601 reference time with timezone (for reproducible analyses)")
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.now:
        try:
            parsed = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            now = parsed.astimezone(UTC)
        except (ValueError, OverflowError):
            parser.error("--now must be an ISO-8601 timestamp with timezone")
    try:
        with localcontext() as ctx:
            ctx.prec = 240
            if args.journal == "-":
                if hasattr(sys.stdin, "reconfigure"):
                    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
                result = analyze(sys.stdin, now)
            else:
                with Path(args.journal).open(encoding="utf-8", errors="replace") as stream:
                    result = analyze(stream, now)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, DecimalException) as exc:
        print(f"Journal read/analysis failed ({type(exc).__name__}); no report produced.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
