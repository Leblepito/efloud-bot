#!/usr/bin/env python3
"""List pending entitlements (T-017 kuyruk görünümü).

Kullanım:
    python3 scripts/list_pending_entitlements.py
    python3 scripts/list_pending_entitlements.py --status granted --limit 20
    python3 scripts/list_pending_entitlements.py --status all --limit 100

Env: scripts/supabase_mgmt.py ile aynı (.env.supabase →
SUPABASE_ACCESS_TOKEN + SUPABASE_PROJECT_REF, dosya yoksa env'den okur)
"""
import argparse
import json
import sys

sys.path.insert(0, 'scripts')
import supabase_mgmt as sm  # type: ignore


def main():
    parser = argparse.ArgumentParser(
        description="List u2algo entitlements (T-017 kuyruk görünümü)"
    )
    parser.add_argument(
        '--status',
        default='pending',
        choices=['pending', 'granted', 'revoked', 'expired', 'all'],
        help='Status filtresi (default: pending)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Maks satır sayısı (default: 50)'
    )
    args = parser.parse_args()

    if args.status == 'all':
        where = ''
    else:
        where = f"where status = '{args.status}'"

    sql = (
        "select email, product, status, source, order_ref, "
        "granted_at, expires_at, created_at "
        f"from public.entitlements {where} "
        f"order by created_at desc limit {args.limit};"
    )

    try:
        result = sm.run_sql(sql)
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "error": "query_failed",
            "detail": str(e),
            "hint": "set SUPABASE_ACCESS_TOKEN and SUPABASE_PROJECT_REF (in .env.supabase or env)"
        }, indent=2), file=sys.stderr)
        sys.exit(1)

    # Supabase Management API response shape: [{"query_result": [...rows...]}]
    # Normalize to a friendly output
    if isinstance(result, list) and len(result) > 0 and 'query_result' in result[0]:
        rows = result[0]['query_result']
    elif isinstance(result, list):
        rows = result
    else:
        rows = []

    print(json.dumps({
        "ok": True,
        "status_filter": args.status,
        "limit": args.limit,
        "count": len(rows),
        "rows": rows
    }, indent=2, default=str))


if __name__ == '__main__':
    main()
