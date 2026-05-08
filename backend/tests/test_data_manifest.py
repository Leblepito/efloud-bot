"""Cache manifest — JSON registry of (symbol, tf) → metadata."""
import json
import pytest

from data.manifest import CacheManifest


def test_manifest_creates_empty_on_missing(tmp_path):
    m = CacheManifest(tmp_path / "manifest.json")
    assert m.entries() == {}


def test_manifest_records_entry(tmp_path):
    m = CacheManifest(tmp_path / "manifest.json")
    m.put("BTC/USDT", "15m", min_ts=1000, max_ts=2000, sha256="abc123")
    m.save()

    # Reload from disk
    m2 = CacheManifest(tmp_path / "manifest.json")
    entry = m2.get("BTC/USDT", "15m")
    assert entry == {"min_ts": 1000, "max_ts": 2000, "sha256": "abc123"}


def test_manifest_get_unknown_returns_none(tmp_path):
    m = CacheManifest(tmp_path / "manifest.json")
    assert m.get("ETH/USDT", "1h") is None
