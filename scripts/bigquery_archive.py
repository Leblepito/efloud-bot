"""Supabase to Google Cloud BigQuery Trade Log Warehouse Archiver — Phase 3.2.

Synchronizes closed trades from Supabase (PostgreSQL) to GCP BigQuery.
Runs as a daily cron script/batch sync.

Features:
  - Graceful degradation if libraries are missing.
  - Idempotent: checks for already archived trades in BigQuery to prevent duplicates.
  - Automatic BigQuery dataset and table creation.
  - Complete schema mapping matching all 20+ telemetry, excursion, and risk columns.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import asyncpg

# Add parent directory to path so backend module is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("efloud.bigquery_archive")


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery Schema definition
# ─────────────────────────────────────────────────────────────────────────────

def get_bigquery_schema(bq: Any) -> list[Any]:
    """Returns BigQuery TableSchema fields matching all trades columns."""
    return [
        bq.SchemaField("id", "STRING", mode="REQUIRED"),
        bq.SchemaField("symbol", "STRING", mode="REQUIRED"),
        bq.SchemaField("direction", "STRING", mode="REQUIRED"),
        bq.SchemaField("entry", "FLOAT", mode="REQUIRED"),
        bq.SchemaField("exit", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("sl", "FLOAT", mode="REQUIRED"),
        bq.SchemaField("tp1", "FLOAT", mode="REQUIRED"),
        bq.SchemaField("tp2", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("size", "FLOAT", mode="REQUIRED"),
        bq.SchemaField("pnl_usdt", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("pnl_pct", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("reason", "STRING", mode="NULLABLE"),
        bq.SchemaField("confluence", "INTEGER", mode="NULLABLE"),
        bq.SchemaField("binance_order_id", "STRING", mode="NULLABLE"),
        bq.SchemaField("opened_at", "TIMESTAMP", mode="REQUIRED"),
        bq.SchemaField("closed_at", "TIMESTAMP", mode="REQUIRED"),
        # PR #57 / tracking
        bq.SchemaField("trace_id", "STRING", mode="NULLABLE"),
        bq.SchemaField("bar_ts_ms", "INTEGER", mode="NULLABLE"),
        # SMC v2 telemetry & Excursions (Phase 3.2)
        bq.SchemaField("entry_setup_source", "STRING", mode="NULLABLE"),
        bq.SchemaField("tp1_target_type", "STRING", mode="NULLABLE"),
        bq.SchemaField("tp2_target_type", "STRING", mode="NULLABLE"),
        bq.SchemaField("bars_to_pullback", "INTEGER", mode="NULLABLE"),
        bq.SchemaField("mae_pct", "FLOAT", mode="REQUIRED"),
        bq.SchemaField("mfe_pct", "FLOAT", mode="REQUIRED"),
        bq.SchemaField("initial_sl", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("adx_value", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("atr_value", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("funding_rate", "FLOAT", mode="NULLABLE"),
        bq.SchemaField("confluence_details", "STRING", mode="NULLABLE"),  # JSON string
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Core Sync Logic
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_postgres_closed_trades(db_url: str) -> list[dict[str, Any]]:
    """Fetches all closed trades from Postgres/Supabase."""
    log.info("Fetching closed trades from Supabase Postgres...")
    conn = await asyncpg.connect(dsn=db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT id::text, symbol, direction,
                   entry::double precision, exit::double precision,
                   sl::double precision, tp1::double precision, tp2::double precision,
                   size::double precision, pnl_usdt::double precision, pnl_pct::double precision,
                   reason, confluence, binance_order_id, opened_at, closed_at,
                   trace_id, bar_ts_ms,
                   entry_setup_source, tp1_target_type, tp2_target_type, bars_to_pullback,
                   mae_pct::double precision, mfe_pct::double precision,
                   initial_sl::double precision, adx_value::double precision,
                   atr_value::double precision, funding_rate::double precision,
                   confluence_details
            FROM trades
            WHERE closed_at IS NOT NULL
            ORDER BY closed_at ASC
            """
        )
        trades = []
        for r in rows:
            d = dict(r)
            # Serialize confluence_details to a JSON string if present
            if d.get("confluence_details") is not None:
                d["confluence_details"] = json.dumps(d["confluence_details"], default=str)
            trades.append(d)
        log.info(f"Fetched {len(trades)} closed trades from Postgres.")
        return trades
    finally:
        await conn.close()


def get_bigquery_client() -> Any:
    """Builds and returns BigQuery client with optional credentials."""
    try:
        from google.cloud import bigquery  # type: ignore[import]
    except ImportError:
        log.error("google-cloud-bigquery library is not installed.")
        return None

    # Service-account JSON from environment
    sa_json = os.environ.get("EFLOUD_PUBSUB_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            import google.oauth2.service_account as _sa  # type: ignore[import]
            creds = _sa.Credentials.from_service_account_info(
                json.loads(sa_json),
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            return bigquery.Client(credentials=creds)
        except Exception as e:
            log.warning(f"Failed to use service account JSON for BigQuery: {e} — falling back to ADC")
    
    return bigquery.Client()


def sync_trades_to_bigquery(trades: list[dict[str, Any]], bq_client: Any) -> int:
    """Syncs new trades to BigQuery, skipping existing ones. Returns archived count."""
    from google.cloud import bigquery
    from google.api_core.exceptions import NotFound

    project = os.environ.get("EFLOUD_BQ_PROJECT_ID") or bq_client.project
    dataset_id = os.environ.get("EFLOUD_BQ_DATASET_ID", "efloud_warehouse")
    table_id = os.environ.get("EFLOUD_BQ_TABLE_ID", "trades")

    dataset_ref = bq_client.dataset(dataset_id, project=project)
    table_ref = dataset_ref.table(table_id)

    # 1. Ensure Dataset exists
    try:
        bq_client.get_dataset(dataset_ref)
        log.info(f"BigQuery dataset {project}.{dataset_id} exists.")
    except NotFound:
        log.info(f"Creating BigQuery dataset {project}.{dataset_id}...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = os.environ.get("EFLOUD_BQ_LOCATION", "US")
        bq_client.create_dataset(dataset)
        log.info(f"Dataset {project}.{dataset_id} created.")

    # 2. Ensure Table exists
    try:
        table = bq_client.get_table(table_ref)
        log.info(f"BigQuery table {project}.{dataset_id}.{table_id} exists.")
    except NotFound:
        log.info(f"Creating BigQuery table {project}.{dataset_id}.{table_id}...")
        table = bigquery.Table(table_ref, schema=get_bigquery_schema(bigquery))
        bq_client.create_table(table)
        log.info(f"Table {project}.{dataset_id}.{table_id} created.")

    # 3. Query existing trade IDs from BigQuery to deduplicate
    log.info("Fetching existing trade IDs from BigQuery...")
    query = f"SELECT id FROM `{project}.{dataset_id}.{table_id}`"
    try:
        query_job = bq_client.query(query)
        results = query_job.result()
        existing_ids = {row.id for row in results}
        log.info(f"Found {len(existing_ids)} trades already in BigQuery.")
    except Exception as e:
        log.warning(f"Could not fetch existing IDs from BigQuery: {e} — proceeding with full load")
        existing_ids = set()

    # 4. Filter out already archived trades
    new_trades = [t for t in trades if t["id"] not in existing_ids]
    if not new_trades:
        log.info("No new closed trades to archive. BigQuery is up-to-date!")
        return 0

    log.info(f"Archiving {len(new_trades)} new trades to BigQuery...")

    # Format timestamp fields for BigQuery JSON load (ISO 8601 strings)
    rows_to_insert = []
    for t in new_trades:
        row = t.copy()
        if isinstance(row.get("opened_at"), datetime):
            row["opened_at"] = row["opened_at"].isoformat()
        if isinstance(row.get("closed_at"), datetime):
            row["closed_at"] = row["closed_at"].isoformat()
        rows_to_insert.append(row)

    # 5. Insert rows into BigQuery
    errors = bq_client.insert_rows_json(table_ref, rows_to_insert)
    if errors:
        log.error(f"Failed to insert rows to BigQuery: {errors}")
        raise RuntimeError(f"BigQuery insert failed: {errors}")

    log.info(f"✅ Successfully archived {len(new_trades)} trades to BigQuery!")
    return len(new_trades)


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL environment variable is not set. Cannot sync.")
        sys.exit(1)

    bq_client = get_bigquery_client()
    if bq_client is None:
        log.error("BigQuery client initialization failed. Make sure google-cloud-bigquery is installed.")
        sys.exit(1)

    try:
        trades = await fetch_postgres_closed_trades(db_url)
        if not trades:
            log.info("No closed trades in Postgres.")
            return

        archived = sync_trades_to_bigquery(trades, bq_client)
        log.info(f"BigQuery Warehouse Sync complete. Total synced in this run: {archived}")
    except Exception as e:
        log.error(f"Archiving failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
