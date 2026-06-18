"""
M2 chart-export manifest consumer — hermetic unit tests.

Disk fixture'ları tmp_path ile oluşturulur (gerçek manifest dizinine dokunmaz).
JSON I/O ve path resolution mock'lanmaz, gerçek dosya sistemi kullanılır
(hızlı, hermetic).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.social import tv_manifest as m2
from backend.social.tv_manifest import (
    ChartSnapshot,
    ManifestError,
    ManifestIndex,
    ManifestNotFoundError,
    ManifestSchemaError,
    SnapshotNotFoundError,
    build_index,
    load_all,
    load_latest,
    resolve_chart_image,
    _validate_item,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sample data (operatörün deliverable kontratı)
# ─────────────────────────────────────────────────────────────────────────────


SAMPLE_BTC_15M = {
    "symbol": "BTCUSDT",
    "tf": "15m",
    "ts": "2026-06-18T18:00:00Z",
    "snapshot_id": "K2GRzo5K",
    "share_url": "https://www.tradingview.com/x/K2GRzo5K/",
    "image_url": "https://s3.tradingview.com/snapshots/k/2/K2GRzo5K.png",
}

SAMPLE_ETH_1H = {
    "symbol": "ETHUSDT",
    "tf": "1h",
    "ts": "2026-06-18T18:05:00Z",
    "snapshot_id": "7ZhYCXAH",
    "share_url": "https://www.tradingview.com/x/7ZhYCXAH/",
    "image_url": "https://s3.tradingview.com/snapshots/7/Z/7ZhYCXAH.png",
}


def _write_manifest(dir_path: Path, name: str, items: list[dict]) -> Path:
    p = dir_path / name
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_item_ok():
    snap = _validate_item(SAMPLE_BTC_15M, source_file="latest.json")
    assert snap.symbol == "BTCUSDT"
    assert snap.tf == "15m"
    assert snap.snapshot_id == "K2GRzo5K"
    assert snap.share_url.startswith("https://www.tradingview.com/x/")
    assert snap.image_url.startswith("https://")
    assert snap.source_file == "latest.json"


def test_validate_item_missing_field():
    bad = dict(SAMPLE_BTC_15M)
    del bad["image_url"]
    with pytest.raises(ManifestSchemaError, match="image_url"):
        _validate_item(bad, source_file="latest.json")


def test_validate_item_missing_multiple_fields():
    bad = {"symbol": "BTCUSDT", "tf": "15m"}
    with pytest.raises(ManifestSchemaError, match="snapshot_id"):
        _validate_item(bad, source_file="latest.json")


def test_validate_item_bad_ts():
    bad = dict(SAMPLE_BTC_15M, ts="not-iso")
    with pytest.raises(ManifestSchemaError, match="ISO 8601"):
        _validate_item(bad, source_file="latest.json")


# ─────────────────────────────────────────────────────────────────────────────
# Loader: latest.json
# ─────────────────────────────────────────────────────────────────────────────


def test_load_latest_two_items(tmp_path):
    _write_manifest(tmp_path, "latest.json", [SAMPLE_BTC_15M, SAMPLE_ETH_1H])
    snaps = load_latest(manifest_dir=tmp_path)
    assert len(snaps) == 2
    assert snaps[0].symbol == "BTCUSDT"
    assert snaps[1].symbol == "ETHUSDT"


def test_load_latest_empty(tmp_path):
    _write_manifest(tmp_path, "latest.json", [])
    snaps = load_latest(manifest_dir=tmp_path)
    assert snaps == []


def test_load_latest_missing_file(tmp_path):
    with pytest.raises(ManifestNotFoundError, match="latest.json bulunamadı"):
        load_latest(manifest_dir=tmp_path)


def test_load_latest_invalid_json(tmp_path):
    (tmp_path / "latest.json").write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ManifestError, match="parse hatası"):
        load_latest(manifest_dir=tmp_path)


def test_load_latest_not_array(tmp_path):
    (tmp_path / "latest.json").write_text('{"symbol": "BTCUSDT"}', encoding="utf-8")
    with pytest.raises(ManifestSchemaError, match="array olmalı"):
        load_latest(manifest_dir=tmp_path)


def test_load_latest_skips_invalid_items(tmp_path):
    bad = dict(SAMPLE_BTC_15M)
    del bad["image_url"]
    _write_manifest(tmp_path, "latest.json", [SAMPLE_BTC_15M, bad, SAMPLE_ETH_1H])
    snaps = load_latest(manifest_dir=tmp_path)
    assert len(snaps) == 2  # invalid skip


# ─────────────────────────────────────────────────────────────────────────────
# Loader: load_all
# ─────────────────────────────────────────────────────────────────────────────


def test_load_all_dedup(tmp_path):
    """Aynı snapshot iki dosyada → bir kez sayılır."""
    _write_manifest(tmp_path, "2026-06-18_run1.json", [SAMPLE_BTC_15M])
    _write_manifest(tmp_path, "2026-06-18_run2.json", [SAMPLE_BTC_15M, SAMPLE_ETH_1H])
    snaps = load_all(manifest_dir=tmp_path)
    assert len(snaps) == 2  # BTC dedupe, ETH yeni
    symbols = {s.symbol for s in snaps}
    assert symbols == {"BTCUSDT", "ETHUSDT"}


def test_load_all_empty_dir(tmp_path):
    assert load_all(manifest_dir=tmp_path) == []


def test_load_all_skips_invalid_manifest(tmp_path):
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    _write_manifest(tmp_path, "good.json", [SAMPLE_BTC_15M])
    snaps = load_all(manifest_dir=tmp_path)
    assert len(snaps) == 1


def test_load_all_skips_non_array_manifest(tmp_path):
    (tmp_path / "notarray.json").write_text('{"x": 1}', encoding="utf-8")
    _write_manifest(tmp_path, "good.json", [SAMPLE_BTC_15M])
    snaps = load_all(manifest_dir=tmp_path)
    assert len(snaps) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Index / resolver
# ─────────────────────────────────────────────────────────────────────────────


def test_index_add_and_resolve():
    idx = ManifestIndex()
    snap = ChartSnapshot(
        symbol=SAMPLE_BTC_15M["symbol"],
        tf=SAMPLE_BTC_15M["tf"],
        ts=SAMPLE_BTC_15M["ts"],
        snapshot_id=SAMPLE_BTC_15M["snapshot_id"],
        share_url=SAMPLE_BTC_15M["share_url"],
        image_url=SAMPLE_BTC_15M["image_url"],
    )
    idx.add(snap)
    resolved = idx.resolve("BTCUSDT", "15m")
    assert resolved.snapshot_id == "K2GRzo5K"
    assert resolved.image_url == SAMPLE_BTC_15M["image_url"]


def test_index_resolve_missing_raises():
    idx = ManifestIndex()
    with pytest.raises(SnapshotNotFoundError, match="BTCUSDT:15m"):
        idx.resolve("BTCUSDT", "15m")


def _snap_from(raw: dict) -> ChartSnapshot:
    """Helper: dict → ChartSnapshot (sample fixture'lar için)."""
    return ChartSnapshot(
        symbol=raw["symbol"],
        tf=raw["tf"],
        ts=raw["ts"],
        snapshot_id=raw["snapshot_id"],
        share_url=raw["share_url"],
        image_url=raw["image_url"],
    )


def test_index_latest_wins():
    """Aynı (symbol, tf) için eski+yeni → yenisi seçilir."""
    idx = ManifestIndex()
    old = _snap_from(dict(SAMPLE_BTC_15M, ts="2026-06-17T10:00:00Z",
                          snapshot_id="OLD00001"))
    new = _snap_from(SAMPLE_BTC_15M)
    idx.add(old)
    idx.add(new)
    resolved = idx.resolve("BTCUSDT", "15m")
    assert resolved.snapshot_id == "K2GRzo5K"  # yeni


def test_index_latest_wins_reverse_order():
    """Yeni önce eklenirse, eski eklenince değişmemeli."""
    idx = ManifestIndex()
    new = _snap_from(SAMPLE_BTC_15M)
    old = _snap_from(dict(SAMPLE_BTC_15M, ts="2026-06-17T10:00:00Z",
                          snapshot_id="OLD00001"))
    idx.add(new)
    idx.add(old)
    resolved = idx.resolve("BTCUSDT", "15m")
    assert resolved.snapshot_id == "K2GRzo5K"


def test_index_keys_sorted():
    idx = ManifestIndex([
        _snap_from(SAMPLE_ETH_1H),
        _snap_from(SAMPLE_BTC_15M),
    ])
    keys = idx.keys()
    assert keys == ["BTCUSDT:15m", "ETHUSDT:1h"]


def test_index_len():
    idx = ManifestIndex([_snap_from(SAMPLE_BTC_15M)])
    assert len(idx) == 1


def test_build_index_from_disk(tmp_path):
    _write_manifest(tmp_path, "latest.json", [SAMPLE_BTC_15M, SAMPLE_ETH_1H])
    idx = build_index(manifest_dir=tmp_path)
    assert len(idx) == 2
    assert idx.resolve("ETHUSDT", "1h").snapshot_id == "7ZhYCXAH"


def test_resolve_chart_image_helper(tmp_path):
    _write_manifest(tmp_path, "latest.json", [SAMPLE_BTC_15M])
    idx = build_index(manifest_dir=tmp_path)
    url = resolve_chart_image(idx, "BTCUSDT", "15m")
    assert url == SAMPLE_BTC_15M["image_url"]


def test_resolve_chart_image_missing_raises(tmp_path):
    _write_manifest(tmp_path, "latest.json", [SAMPLE_BTC_15M])
    idx = build_index(manifest_dir=tmp_path)
    with pytest.raises(SnapshotNotFoundError):
        resolve_chart_image(idx, "SOLUSDT", "1h")


# ─────────────────────────────────────────────────────────────────────────────
# ChartSnapshot dataclass
# ─────────────────────────────────────────────────────────────────────────────


def test_snapshot_key():
    snap = _snap_from(SAMPLE_BTC_15M)
    assert snap.key == "BTCUSDT:15m"


def test_snapshot_to_dict():
    snap = _snap_from(SAMPLE_BTC_15M)
    d = snap.to_dict()
    assert d["symbol"] == "BTCUSDT"
    assert d["snapshot_id"] == "K2GRzo5K"
    assert d["source_file"] is None  # default
    assert "loaded_at" in d


def test_snapshot_default_loaded_at():
    snap1 = _snap_from(SAMPLE_BTC_15M)
    snap2 = _snap_from(SAMPLE_BTC_15M)
    # loaded_at default factory her instance için fresh değer üretir
    assert snap1.loaded_at <= snap2.loaded_at
