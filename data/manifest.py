"""Parquet cache manifest — JSON registry of (symbol, tf) → range/sha256."""
from __future__ import annotations
import json
from pathlib import Path


def _key(symbol: str, tf: str) -> str:
    """Manifest key: BTC/USDT_15m → 'BTC_USDT_15m'."""
    return f"{symbol.replace('/', '_')}_{tf}"


class CacheManifest:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.exists():
            self._data = json.loads(self.path.read_text())
        else:
            self._data = {}

    def put(self, symbol: str, tf: str, *, min_ts: int, max_ts: int, sha256: str) -> None:
        self._data[_key(symbol, tf)] = {
            "min_ts": int(min_ts),
            "max_ts": int(max_ts),
            "sha256": sha256,
        }

    def get(self, symbol: str, tf: str) -> dict | None:
        return self._data.get(_key(symbol, tf))

    def entries(self) -> dict:
        return dict(self._data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
        tmp.replace(self.path)
