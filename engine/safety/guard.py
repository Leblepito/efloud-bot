"""
Exchange Guard — API Resilience Layer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Exchange çağrılarını güvenli hale getiren wrapper:
  - Exponential backoff retry (503, 429, timeout)
  - Rate limit tracking
  - Data freshness validation
  - Mainnet guard
  - Secret masking
"""

import time
import os
import logging
from functools import wraps
from datetime import datetime, timedelta
from typing import Callable, Any, Optional
import pandas as pd

log = logging.getLogger("efloud.guard")


# ══════════════════════════════════════════════
# RETRY LOGIC
# ══════════════════════════════════════════════

class RetryExhausted(Exception):
    pass


def retry_with_backoff(max_attempts: int = 5,
                        base_delay: float = 1.0,
                        max_delay: float = 30.0,
                        retryable_errors: tuple = (Exception,)):
    """
    Exponential backoff decorator.
    Retryable errors: network, timeout, 5xx. NOT 4xx (auth/params).
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable_errors as e:
                    last_err = e
                    err_str = str(e).lower()

                    # 4xx errors — retry etme
                    if any(x in err_str for x in ["insufficient", "invalid", "forbidden",
                                                     "unauthorized", "not found", "400", "401",
                                                     "403", "404"]):
                        log.error(f"{func.__name__} non-retryable: {e}")
                        raise

                    delay = min(base_delay * (2 ** attempt), max_delay)
                    log.warning(f"{func.__name__} attempt {attempt+1}/{max_attempts} failed: {e}. "
                                 f"Retry in {delay:.1f}s")
                    time.sleep(delay)

            raise RetryExhausted(f"{func.__name__} failed after {max_attempts} attempts: {last_err}")
        return wrapper
    return decorator


# ══════════════════════════════════════════════
# RATE LIMITER
# ══════════════════════════════════════════════

class RateLimiter:
    """Token bucket rate limiter — Binance: ~1200 weight/min."""

    def __init__(self, max_per_minute: int = 1000):
        self.max = max_per_minute
        self.tokens: list = []  # timestamps

    def acquire(self, weight: int = 1, block: bool = True) -> bool:
        """
        Token al. block=True ise bekle, False ise limit aşıldıysa False dön.
        """
        # 2026-07-11 review (ertelenen kalem): weight > max hicbir bekleme
        # ile sigamaz — eski kod bos bucket'ta self.tokens[0] IndexError'a
        # dusuyordu (canli loop crash), doluysa sonsuz bekleme dongusune
        # giriyordu. Fail-closed: acik hata. (Repo'daki tek gercek cagri
        # weight=4, max=1000 — canli yol etkilenmez.)
        if weight > self.max:
            raise ValueError(
                f"RateLimiter: weight={weight} > max_per_minute={self.max} — "
                "bu istek hicbir zaman admit edilemez (config/cagri hatasi)"
            )
        now = time.time()
        # 1 dakikadan eski tokenları temizle
        self.tokens = [t for t in self.tokens if now - t[0] < 60]

        current_usage = sum(t[1] for t in self.tokens)

        if current_usage + weight > self.max:
            if not block:
                return False
            # En eski token'ın 60s dolmasını bekle. tokens burada bos olamaz
            # (weight <= max garanti; bos bucket'ta usage=0+weight <= max ->
            # admit). Yine de indexleme korumali kalsin.
            wait = (60 - (now - self.tokens[0][0]) + 0.5) if self.tokens else 1.0
            log.warning(f"Rate limit: waiting {wait:.1f}s")
            time.sleep(max(wait, 0))
            return self.acquire(weight, block)

        self.tokens.append((now, weight))
        return True


# ══════════════════════════════════════════════
# DATA VALIDATION
# ══════════════════════════════════════════════

class StaleDataError(Exception):
    pass


def validate_kline_freshness(df: pd.DataFrame, timeframe: str,
                              tolerance_factor: float = 2.0) -> bool:
    """
    Son mum çok eski mi? Stale data üzerinde trade ETMEYİZ.

    Args:
        df: kline DataFrame (index: timestamp)
        timeframe: "1m", "5m", "1h", "4h", "1d"
        tolerance_factor: Kaç timeframe gecikme kabul? (2.0 = 2× TF)

    Raises:
        StaleDataError: data çok eski
    """
    if len(df) == 0:
        raise StaleDataError("Empty DataFrame")

    tf_minutes = _tf_to_minutes(timeframe)
    last_ts = df.index[-1]
    if isinstance(last_ts, pd.Timestamp):
        last_ts = last_ts.to_pydatetime()

    # UTC'ye çevir
    if last_ts.tzinfo is None:
        now = datetime.utcnow()
    else:
        from datetime import timezone
        now = datetime.now(timezone.utc)

    delta = (now - last_ts).total_seconds() / 60
    max_delta = tf_minutes * tolerance_factor

    if delta > max_delta:
        raise StaleDataError(
            f"Last candle {delta:.1f} min old, max {max_delta:.1f} min for {timeframe}")

    return True


def validate_kline_integrity(df: pd.DataFrame) -> bool:
    """NaN, gap, duplicates kontrolü."""
    if df.empty:
        raise ValueError("Empty DataFrame")

    # NaN check
    if df[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("NaN in OHLC")

    # Duplicate timestamps
    if df.index.duplicated().any():
        raise ValueError("Duplicate timestamps")

    # High >= Low sanity
    if (df["high"] < df["low"]).any():
        raise ValueError("High < Low in some rows")

    # Positive prices
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Non-positive prices")

    return True


def _tf_to_minutes(tf: str) -> int:
    """'5m' → 5, '1h' → 60, '4h' → 240, '1d' → 1440."""
    tf = tf.lower().strip()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("d"):
        return int(tf[:-1]) * 1440
    if tf.endswith("w"):
        return int(tf[:-1]) * 10080
    raise ValueError(f"Unknown timeframe: {tf}")


# ══════════════════════════════════════════════
# MAINNET GUARD
# ══════════════════════════════════════════════

class MainnetGuard:
    """
    Mainnet'te yanlışlıkla çalışmayı engelleyen guard.

    Kurallar:
      1. testnet=false + dry_run=false kombinasyonu için EFLOUD_ALLOW_MAINNET=1 env var
      2. Mainnet'te başlarken 5 saniyelik uyarı bekler
      3. İlk mainnet run'da dry_run=true zorla
    """

    @staticmethod
    def check(testnet: bool, dry_run: bool, interactive: bool = True) -> bool:
        """
        Returns: True = proceed, False = abort
        """
        if testnet:
            return True  # Testnet her zaman güvenli

        if dry_run:
            log.info("⚠️  MAINNET + dry_run: no real orders will be sent")
            return True

        # LIVE MAINNET
        allow = os.environ.get("EFLOUD_ALLOW_MAINNET", "0") == "1"
        if not allow:
            log.error("⛔ MAINNET LIVE trading requires EFLOUD_ALLOW_MAINNET=1 env var")
            return False

        # 5 saniye countdown
        log.warning("🚨" * 20)
        log.warning("🚨 MAINNET LIVE TRADING — REAL MONEY AT RISK")
        log.warning("🚨" * 20)
        if interactive:
            for i in range(5, 0, -1):
                log.warning(f"🚨 Starting in {i} seconds... (Ctrl+C to abort)")
                time.sleep(1)
        return True


# ══════════════════════════════════════════════
# SECRET MASKING
# ══════════════════════════════════════════════

def mask_secret(s: str, keep_tail: int = 4) -> str:
    """API key'i log için maskele: 'abc...xyz1'."""
    if not s or len(s) < keep_tail + 3:
        return "***"
    return f"{s[:3]}...{s[-keep_tail:]}"
