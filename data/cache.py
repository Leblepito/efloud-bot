"""Parquet OHLCV cache with atomic writes + sha256 verification."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd

from data.manifest import CacheManifest


def hash_dataframe(df: pd.DataFrame) -> str:
    """Stable sha256 of a DataFrame (sorted index, sorted columns)."""
    df_sorted = df.sort_index().reindex(sorted(df.columns), axis=1)
    return hashlib.sha256(pd.util.hash_pandas_object(df_sorted, index=True).values.tobytes()).hexdigest()


class OHLCVCache:
    """Parquet cache: cache_dir/{symbol_normalized}/{tf}.parquet"""

    def __init__(self, cache_dir: Path | str, verify_sha: bool = True):
        """verify_sha: when False, skip sha256 check on read (fast path for trusted cache)."""
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = CacheManifest(self.dir / "manifest.json")
        self.verify_sha = verify_sha

    def _path(self, symbol: str, tf: str) -> Path:
        return self.dir / symbol.replace("/", "_") / f"{tf}.parquet"

    def get(self, symbol: str, tf: str) -> Optional[pd.DataFrame]:
        """Returns DataFrame on cache hit + sha256 match, else None."""
        manifest_entry = self.manifest.get(symbol, tf)
        path = self._path(symbol, tf)
        if not manifest_entry or not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
        except Exception:
            return None
        if self.verify_sha:
            actual_sha = hash_dataframe(df)
            if actual_sha != manifest_entry["sha256"]:
                return None
        return df

    def put(self, symbol: str, tf: str, df: pd.DataFrame) -> None:
        """Atomic write + manifest update."""
        path = self._path(symbol, tf)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        df.to_parquet(tmp)
        tmp.replace(path)

        sha = hash_dataframe(df)
        # Convert datetime index → ms for manifest
        idx_ms = (df.index.astype("int64") // 1_000_000).tolist()
        self.manifest.put(symbol, tf, min_ts=idx_ms[0], max_ts=idx_ms[-1], sha256=sha)
        self.manifest.save()
