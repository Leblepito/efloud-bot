#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure repo root imports work when invoked as `python scripts/extract_sl_evidence.py`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._sl_evidence.db import fetch_rows
from scripts._sl_evidence.journal import load_journal
from scripts._sl_evidence.render import enrich_row, write_csv, write_summary
from scripts._sl_evidence.secrets import assert_no_secrets


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract read-only Phase 0 SL evidence for PR-B. Produces CSV + markdown summary; does not decide H1-H4 verdicts.",
    )
    parser.add_argument("--since", required=True, help="UTC lower bound for closed_at, e.g. 2026-05-01T00:00:00Z")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. OP/USDT,FIL/USDT")
    parser.add_argument("--out", required=True, help="CSV output path")
    parser.add_argument("--summary", required=True, help="Markdown summary output path")
    parser.add_argument("--journal", default="state_aggressive/trade_journal.jsonl", help="Trade journal JSONL path")
    parser.add_argument("--database-url-env", default="DATABASE_URL", help="Environment variable containing DB URL")
    parser.add_argument("--dry-run", action="store_true", help="Validate args and print plan without reading DB or writing files")
    return parser.parse_args(argv)


def _symbols(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


async def _run(args: argparse.Namespace) -> int:
    symbols = _symbols(args.symbols)
    if not symbols:
        print("ERROR: --symbols resolved to an empty list", file=sys.stderr)
        return 2

    if args.dry_run:
        msg = f"DRY RUN: would query {len(symbols)} symbols since {args.since}; CSV={args.out}; summary={args.summary}; journal={args.journal}"
        assert_no_secrets(msg)
        print(msg)
        return 0

    database_url = os.getenv(args.database_url_env)
    if not database_url:
        print(f"ERROR: required DB URL env var is not set: {args.database_url_env}", file=sys.stderr)
        return 1

    try:
        raw_rows = await fetch_rows(database_url, args.since, symbols)
    except Exception as exc:
        print(f"ERROR: DB evidence query failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    journal_entries, warnings = load_journal(args.journal)
    rows = [enrich_row(r, journal_entries) for r in raw_rows]
    try:
        write_csv(rows, args.out)
        write_summary(rows, args.summary, warnings)
    except Exception as exc:
        print(f"ERROR: failed to write evidence outputs: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    audit_count = sum(1 for r in rows if r.get("audit_present"))
    stdout = (
        f"Phase 0 evidence extracted: rows={len(rows)} audit_rows={audit_count} "
        f"journal_rows={sum(1 for r in rows if r.get('journal_present'))} csv={args.out} summary={args.summary}"
    )
    assert_no_secrets(stdout)
    print(stdout)
    if len(rows) > 0 and audit_count / len(rows) < 0.10:
        print("WARNING: trade_audits coverage below 10%; surface to Utku before analysis", file=sys.stderr)
    for warning in warnings[:3]:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
