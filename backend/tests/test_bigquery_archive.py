"""Unit tests for Supabase to GCP BigQuery trade log archiver script.

Covers all core functionality (Postgres fetches, BigQuery Client building,
idempotent syncing, duplicate filtering, formatting) without requiring a real
database or GCP connection.
"""
import sys
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Mock libraries not installed in the local environment
mock_google = MagicMock()
mock_google_cloud = MagicMock()
mock_bigquery = MagicMock()
mock_oauth2 = MagicMock()
mock_sa = MagicMock()

sys.modules["google"] = mock_google
sys.modules["google.cloud"] = mock_google_cloud
sys.modules["google.cloud.bigquery"] = mock_bigquery
sys.modules["google.oauth2"] = mock_oauth2
sys.modules["google.oauth2.service_account"] = mock_sa

# Unify attributes for from-imports
mock_google.cloud = mock_google_cloud
mock_google_cloud.bigquery = mock_bigquery
mock_google.oauth2 = mock_oauth2
mock_oauth2.service_account = mock_sa

class MockNotFound(Exception):
    pass

mock_exceptions = MagicMock()
mock_exceptions.NotFound = MockNotFound
sys.modules["google.api_core"] = mock_exceptions
sys.modules["google.api_core.exceptions"] = mock_exceptions

import pytest

from scripts.bigquery_archive import (
    fetch_postgres_closed_trades,
    get_bigquery_client,
    sync_trades_to_bigquery,
)


# ─────────────────────────────────────────────────────────────────────────────
# DB/Postgres Fetch Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("asyncpg.connect")
async def test_fetch_postgres_closed_trades(mock_connect):
    """Verifies that postgres rows are fetched and confluence_details are serialized."""
    mock_conn = AsyncMock()
    mock_connect.return_value = mock_conn

    # Mock DB row
    mock_row = {
        "id": "abc-123-uuid",
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "entry": 60000.0,
        "exit": 61000.0,
        "sl": 59000.0,
        "tp1": 62000.0,
        "tp2": None,
        "size": 0.1,
        "pnl_usdt": 100.0,
        "pnl_pct": 1.67,
        "reason": "TP1",
        "confluence": 80,
        "binance_order_id": "112233",
        "opened_at": datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 5, 26, 13, 0, 0, tzinfo=timezone.utc),
        "trace_id": "trace-99",
        "bar_ts_ms": 1779998888000,
        "entry_setup_source": "OTE_RETRACE",
        "tp1_target_type": "MTF_ZONE",
        "tp2_target_type": None,
        "bars_to_pullback": 4,
        "mae_pct": 0.1,
        "mfe_pct": 1.7,
        "initial_sl": 59000.0,
        "adx_value": 25.5,
        "atr_value": 450.0,
        "funding_rate": 0.0001,
        "confluence_details": {"reasons": ["BOS", "CHoCH"], "score": 8},
    }
    mock_conn.fetch.return_value = [mock_row]

    trades = await fetch_postgres_closed_trades("postgresql://localhost:5432/test")

    # Assert connection made
    mock_connect.assert_called_once_with(dsn="postgresql://localhost:5432/test")
    # Assert query execution
    mock_conn.fetch.assert_called_once()
    assert len(trades) == 1
    # Verify serialization of dict to JSON string for BQ
    assert isinstance(trades[0]["confluence_details"], str)
    details = json.loads(trades[0]["confluence_details"])
    assert details["score"] == 8


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery Client Initialization Tests
# ─────────────────────────────────────────────────────────────────────────────

@patch.dict("os.environ", {"EFLOUD_PUBSUB_SERVICE_ACCOUNT_JSON": ""})
def test_get_bigquery_client_default():
    """Should initialize standard BigQuery client when no service account is set."""
    mock_client_class = sys.modules["google.cloud.bigquery"].Client
    mock_client_class.reset_mock()
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance

    client = get_bigquery_client()
    assert client == mock_client_instance
    mock_client_class.assert_called_once()


@patch.dict("os.environ", {
    "EFLOUD_PUBSUB_SERVICE_ACCOUNT_JSON": '{"type": "service_account", "project_id": "test-project"}'
})
def test_get_bigquery_client_with_service_account():
    """Should initialize BigQuery client using the service account credentials from env."""
    mock_from_info = sys.modules["google.oauth2.service_account"].Credentials.from_service_account_info
    mock_from_info.reset_mock()
    mock_bq_client = sys.modules["google.cloud.bigquery"].Client
    mock_bq_client.reset_mock()

    mock_creds = MagicMock()
    mock_from_info.return_value = mock_creds
    mock_client_instance = MagicMock()
    mock_bq_client.return_value = mock_client_instance

    client = get_bigquery_client()
    assert client == mock_client_instance
    mock_from_info.assert_called_once()
    # Check that credentials was passed
    mock_bq_client.assert_called_once_with(credentials=mock_creds)


# ─────────────────────────────────────────────────────────────────────────────
# Core Sync Logic Tests
# ─────────────────────────────────────────────────────────────────────────────

@patch("google.cloud.bigquery.Dataset")
@patch("google.cloud.bigquery.Table")
@patch("google.cloud.bigquery.SchemaField")
def test_sync_trades_to_bigquery_creates_dataset_and_table_if_missing(mock_schema, mock_table, mock_dataset):
    """Should fetch existing tables, create dataset/table if missing, and insert rows."""
    from google.api_core.exceptions import NotFound

    mock_bq = MagicMock()
    mock_bq.project = "test-project"

    # Mock get_dataset / get_table raising NotFound to trigger creation
    mock_bq.get_dataset.side_effect = NotFound("Dataset not found")
    mock_bq.get_table.side_effect = NotFound("Table not found")

    # Mock query job
    mock_query_job = MagicMock()
    mock_bq.query.return_value = mock_query_job
    mock_query_job.result.return_value = [] # no existing rows in BigQuery

    # Mock insert returning empty list (success)
    mock_bq.insert_rows_json.return_value = []

    # Prepare mock input trades
    trades = [
        {
            "id": "new-uuid-1",
            "symbol": "ETH/USDT",
            "direction": "SHORT",
            "entry": 3000.0,
            "exit": 2900.0,
            "sl": 3100.0,
            "tp1": 2800.0,
            "tp2": None,
            "size": 1.0,
            "opened_at": datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 26, 13, 0, 0, tzinfo=timezone.utc),
            "mae_pct": 0.0,
            "mfe_pct": 3.33,
        }
    ]

    synced_count = sync_trades_to_bigquery(trades, mock_bq)

    assert synced_count == 1
    # Check dataset was created
    mock_bq.create_dataset.assert_called_once()
    # Check table was created
    mock_bq.create_table.assert_called_once()
    # Check insert was called
    mock_bq.insert_rows_json.assert_called_once()
    
    # Verify ISO timestamp string formatting
    inserted_rows = mock_bq.insert_rows_json.call_args[0][1]
    assert inserted_rows[0]["opened_at"] == "2026-05-26T12:00:00+00:00"
    assert inserted_rows[0]["closed_at"] == "2026-05-26T13:00:00+00:00"


def test_sync_trades_to_bigquery_skips_duplicates():
    """Should query existing BQ records and filter out already archived IDs."""
    mock_bq = MagicMock()
    mock_bq.project = "test-project"

    # Dataset/table exist
    mock_bq.get_dataset.return_value = MagicMock()
    mock_bq.get_table.return_value = MagicMock()

    # BQ already has "uuid-existing"
    mock_row = MagicMock()
    mock_row.id = "uuid-existing"
    mock_query_job = MagicMock()
    mock_bq.query.return_value = mock_query_job
    mock_query_job.result.return_value = [mock_row]

    # Mock insert success
    mock_bq.insert_rows_json.return_value = []

    # One existing trade, one new trade
    trades = [
        {"id": "uuid-existing", "symbol": "BTC/USDT", "opened_at": datetime.now(), "closed_at": datetime.now()},
        {"id": "uuid-new", "symbol": "ETH/USDT", "opened_at": datetime.now(), "closed_at": datetime.now()}
    ]

    synced_count = sync_trades_to_bigquery(trades, mock_bq)

    # Only new one should be synced
    assert synced_count == 1
    # Ensure insert called with only new trade
    mock_bq.insert_rows_json.assert_called_once()
    inserted_rows = mock_bq.insert_rows_json.call_args[0][1]
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["id"] == "uuid-new"
