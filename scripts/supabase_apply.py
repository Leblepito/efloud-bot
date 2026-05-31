#!/usr/bin/env python3
"""Apply efloud-bot migrations + u2algo waitlist to Supabase via the Management API.

Mirrors backend/migrate.py semantics:
  - schema_migrations(version TEXT PK, applied_at TIMESTAMPTZ DEFAULT NOW())
  - version == migration file stem (e.g. "001_init")
  - applies only pending versions, in alphabetical order
  - records each applied version so a later `python -m backend.migrate up`
    against this same DB sees them as already applied and skips them.

Reads SUPABASE_ACCESS_TOKEN + SUPABASE_PROJECT_REF (auto-loaded from .env.supabase).

Usage:
    python scripts/supabase_apply.py            # apply bot migrations + waitlist
    python scripts/supabase_apply.py --dry-run  # show plan only
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = HERE / "backend" / "migrations"
WAITLIST_SQL = HERE / "u2algo-site" / "supabase" / "waitlist_leads.sql"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env_file(HERE / ".env.supabase")
TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN")
REF = os.environ.get("SUPABASE_PROJECT_REF")


def run_sql(sql: str) -> dict:
    url = f"https://api.supabase.com/v1/projects/{REF}/database/query"
    req = urllib.request.Request(
        url,
        data=json.dumps({"query": sql}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return {"ok": True, "data": json.loads(r.read().decode())}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": e.read().decode()[:1500]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def fail(msg: str, res: dict | None = None) -> None:
    print(f"FATAL: {msg}")
    if res is not None:
        print(json.dumps(res, indent=2, default=str))
    sys.exit(1)


def main() -> None:
    if not TOKEN or not REF:
        fail("SUPABASE_ACCESS_TOKEN / SUPABASE_PROJECT_REF not set (check .env.supabase)")
    dry = "--dry-run" in sys.argv

    # 1. Ensure tracking table (same DDL as backend/migrate.py)
    print("== ensure schema_migrations ==")
    res = run_sql(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, "
        "applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW());"
    )
    if not res["ok"]:
        fail("could not create schema_migrations", res)

    # 2. Applied set
    res = run_sql("SELECT version FROM schema_migrations;")
    if not res["ok"]:
        fail("could not read schema_migrations", res)
    applied = {row["version"] for row in res["data"]}
    print(f"already applied: {sorted(applied) or '(none)'}")

    # 3. Discover migrations (stem-sorted, like the runner)
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    pending = [p for p in migrations if p.stem not in applied]
    print(f"pending migrations: {[p.stem for p in pending] or '(none)'}")

    if dry:
        print("\n-- DRY RUN: nothing applied --")
        print(f"waitlist file present: {WAITLIST_SQL.exists()}")
        return

    # 4. Apply each pending migration, then record version.
    #    The Management API runs each query in its own implicit transaction.
    for p in pending:
        sql = p.read_text(encoding="utf-8")
        print(f"\n== applying {p.stem} ==")
        res = run_sql(sql)
        if not res["ok"]:
            fail(f"migration {p.stem} failed", res)
        rec = run_sql(
            f"INSERT INTO schema_migrations (version) VALUES ('{p.stem}') "
            "ON CONFLICT (version) DO NOTHING;"
        )
        if not rec["ok"]:
            fail(f"could not record {p.stem}", rec)
        print(f"  ok {p.stem}")

    # 5. u2algo waitlist_leads (separate site schema; not part of bot runner)
    if WAITLIST_SQL.exists():
        print("\n== applying u2algo waitlist_leads ==")
        res = run_sql(WAITLIST_SQL.read_text(encoding="utf-8"))
        if not res["ok"]:
            fail("waitlist_leads failed", res)
        print("  ok waitlist_leads")
    else:
        print("waitlist_leads.sql not found, skipping")

    print("\nALL DONE")


if __name__ == "__main__":
    main()
