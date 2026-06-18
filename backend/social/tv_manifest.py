r"""
M2 chart-export manifest consumer.

Operatörün LOKAL makinesi (TV Desktop + CDP) M2 üretim yapar:
  generate(local) → C:\tmp\m2-tv-export\manifests\<date>_<runid>.json

Schema (tek manifest item):
  {
    "symbol": "BTCUSDT",
    "tf": "15m",
    "ts": "2026-06-18T18:00:00Z",
    "snapshot_id": "K2GRzo5K",
    "share_url": "https://www.tradingview.com/x/K2GRzo5K/",
    "image_url": "https://s3.tradingview.com/snapshots/.../K2GRzo5K.png"
  }

VPS consumer (this module) üretmez — sadece okur, validate eder, index'ler.

Bu modül:
  1. Manifest dosyalarını diskten okur (idempotent)
  2. Schema validate eder (snapshot_id + image_url her zaman)
  3. Symbol + TF bazlı lookup index'i kurar (chart_img placeholder resolve için)
  4. Tier-2 renderer'a resolve fonksiyonu sağlar

Üretim (generate) operatörün lokalinde kalır; VPS'te browser yok.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Default manifest dizini (VPS tarafı — operatör scp/sync ile buraya düşürür).
# Operatör-lokal path: C:\tmp\m2-tv-export\manifests\
# VPS'te bu path mount/sync edilir; default fallback /opt/efloud-bot/state/m2_manifests
_DEFAULT_MANIFEST_DIR = (
    Path(__file__).resolve().parents[2] / "state" / "m2_manifests"
)
MANIFEST_DIR_ENV = "EFLOUD_M2_MANIFEST_DIR"  # override

# latest.json = en yeni manifest'i gösteren alias
LATEST_FILENAME = "latest.json"


class ManifestError(Exception):
    """Base error for M2 manifest consumer."""


class ManifestSchemaError(ManifestError):
    """Item eksik alan içeriyor."""


class ManifestNotFoundError(ManifestError):
    """Manifest dizini boş veya latest.json yok."""


class SnapshotNotFoundError(ManifestError):
    """Symbol+TF için manifest'te kayıt yok."""


# ─────────────────────────────────────────────────────────────────────────────
# Item model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ChartSnapshot:
    """Tek bir TV chart-export snapshot'ı."""

    symbol: str                      # "BTCUSDT"
    tf: str                          # "15m" | "1h" | "4h"
    ts: str                          # ISO 8601 UTC, "2026-06-18T18:00:00Z"
    snapshot_id: str                 # "K2GRzo5K" (TV public id)
    share_url: str                   # "https://www.tradingview.com/x/K2GRzo5K/"
    image_url: str                   # "https://s3.tradingview.com/.../K2GRzo5K.png"
    source_file: str | None = None   # Hangi manifest'ten geldi (audit)
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def key(self) -> str:
        """Lookup key: (symbol, tf). Tier-2 renderer bununla resolve eder."""
        return f"{self.symbol}:{self.tf}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "ts": self.ts,
            "snapshot_id": self.snapshot_id,
            "share_url": self.share_url,
            "image_url": self.image_url,
            "source_file": self.source_file,
            "loaded_at": self.loaded_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────────────────


_REQUIRED_FIELDS = ("symbol", "tf", "ts", "snapshot_id", "share_url", "image_url")


def _validate_item(raw: dict[str, Any], source_file: str) -> ChartSnapshot:
    """Raw dict → ChartSnapshot; eksik alan → ManifestSchemaError."""
    missing = [f for f in _REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ManifestSchemaError(
            f"manifest item eksik alanlar: {missing} (file={source_file})"
        )
    # ts basit doğrulama: ISO 8601 lookalike olmalı
    ts = raw["ts"]
    if not isinstance(ts, str) or "T" not in ts:
        raise ManifestSchemaError(
            f"ts ISO 8601 olmalı (YYYY-MM-DDTHH:MM:SSZ): {ts!r} (file={source_file})"
        )
    return ChartSnapshot(
        symbol=str(raw["symbol"]),
        tf=str(raw["tf"]),
        ts=ts,
        snapshot_id=str(raw["snapshot_id"]),
        share_url=str(raw["share_url"]),
        image_url=str(raw["image_url"]),
        source_file=source_file,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_manifest_dir(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get(MANIFEST_DIR_ENV)
    if env:
        return Path(env)
    return _DEFAULT_MANIFEST_DIR


def load_latest(
    manifest_dir: str | Path | None = None,
) -> list[ChartSnapshot]:
    """latest.json → list[ChartSnapshot].

    latest.json bir array (operatör deliverable kontratı).
    Boş dizi → ManifestNotFoundError.
    Invalid item → log warning + skip (load_all ile tutarlı).
    """
    d = _resolve_manifest_dir(manifest_dir)
    latest = d / LATEST_FILENAME
    if not latest.exists():
        raise ManifestNotFoundError(f"latest.json bulunamadı: {latest}")
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestError(f"latest.json parse hatası: {e}") from e

    if not isinstance(data, list):
        raise ManifestSchemaError(
            f"latest.json array olmalı, bulundu: {type(data).__name__}"
        )

    items: list[ChartSnapshot] = []
    for raw in data:
        try:
            items.append(_validate_item(raw, source_file=str(latest)))
        except ManifestSchemaError as e:
            logger.warning("latest.json item skip: %s", e)
            continue
    return items


def load_all(manifest_dir: str | Path | None = None) -> list[ChartSnapshot]:
    """manifest_dir altındaki TÜM .json dosyalarını yükle (latest.json dahil).

    Use case: bootstrap'ta tüm history yükle.
    Duplicate (symbol, tf, snapshot_id) → ilk görülen kalır.
    """
    d = _resolve_manifest_dir(manifest_dir)
    if not d.exists():
        return []

    items: list[ChartSnapshot] = []
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(d.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning("manifest parse hatası: %s — %s", path, e)
            continue
        if not isinstance(data, list):
            logger.warning("manifest array değil: %s", path)
            continue
        for raw in data:
            try:
                snap = _validate_item(raw, source_file=str(path))
            except ManifestSchemaError as e:
                logger.warning("manifest item skip: %s", e)
                continue
            dedup_key = (snap.symbol, snap.tf, snap.snapshot_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            items.append(snap)
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Index / resolver (Tier-2 renderer entegrasyonu)
# ─────────────────────────────────────────────────────────────────────────────


class ManifestIndex:
    """In-memory (symbol, tf) → ChartSnapshot lookup.

    Latest-wins semantics: aynı (symbol, tf) için birden fazla snapshot varsa
    en yenisi (ts DESC) seçilir.
    """

    def __init__(self, snapshots: Iterable[ChartSnapshot] | None = None) -> None:
        self._by_key: dict[str, ChartSnapshot] = {}
        if snapshots:
            for s in snapshots:
                self.add(s)

    def add(self, snap: ChartSnapshot) -> None:
        existing = self._by_key.get(snap.key)
        if existing is None or snap.ts > existing.ts:
            self._by_key[snap.key] = snap

    def resolve(self, symbol: str, tf: str) -> ChartSnapshot:
        """Symbol + TF → ChartSnapshot (latest)."""
        key = f"{symbol}:{tf}"
        snap = self._by_key.get(key)
        if snap is None:
            raise SnapshotNotFoundError(
                f"snapshot bulunamadı: {key} "
                f"(mevcut: {sorted(self._by_key.keys())})"
            )
        return snap

    def __len__(self) -> int:
        return len(self._by_key)

    def keys(self) -> list[str]:
        return sorted(self._by_key.keys())


def build_index(manifest_dir: str | Path | None = None) -> ManifestIndex:
    """latest.json → ManifestIndex. Convenience."""
    return ManifestIndex(load_latest(manifest_dir))


# ─────────────────────────────────────────────────────────────────────────────
# Renderer helper — {chart_img} placeholder resolve
# ─────────────────────────────────────────────────────────────────────────────


def resolve_chart_image(
    index: ManifestIndex,
    symbol: str,
    tf: str,
) -> str:
    """Tier-2 renderer için convenience: ManifestIndex + (symbol, tf) → image_url.

    Kullanım (tier2_renderers entegrasyonunda):
        rc = render("signal_idea", "en", {
            "symbol": "BTCUSDT", "tf": "15m", ...,
            "chart_img": resolve_chart_image(idx, "BTCUSDT", "15m"),
        })
    """
    return index.resolve(symbol, tf).image_url
