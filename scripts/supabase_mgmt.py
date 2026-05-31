#!/usr/bin/env python3
"""Supabase Management API helper.

Reads SUPABASE_ACCESS_TOKEN and SUPABASE_PROJECT_REF from the environment.
Usage:
    python scripts/supabase_mgmt.py sql "select 1;"
    python scripts/supabase_mgmt.py sqlfile path/to/file.sql
    python scripts/supabase_mgmt.py tables
"""
import json
import os
import sys
import urllib.request
import urllib.error

def _load_env_file(path: str):
    """Load KEY=VALUE lines from a dotenv-style file into os.environ if not already set."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_load_env_file(os.path.join(_HERE, ".env.supabase"))

TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN")
REF = os.environ.get("SUPABASE_PROJECT_REF")


def run_sql(sql: str):
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
        return {"ok": False, "status": e.code, "body": e.read().decode()[:1000]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def main():
    if not TOKEN or not REF:
        print("ERROR: set SUPABASE_ACCESS_TOKEN and SUPABASE_PROJECT_REF", file=sys.stderr)
        sys.exit(2)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tables"
    if cmd == "sql":
        res = run_sql(sys.argv[2])
    elif cmd == "sqlfile":
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            res = run_sql(f.read())
    elif cmd == "tables":
        res = run_sql(
            "select table_name from information_schema.tables "
            "where table_schema='public' order by table_name;"
        )
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(res, indent=2, default=str))
    if not res.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
