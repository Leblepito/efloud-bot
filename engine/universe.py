"""
Symbol Universe Resolver
━━━━━━━━━━━━━━━━━━━━━━━━
Sabit + dinamik top-volume coin listesi.

Modlar:
  fixed    → sadece fixed_core listesi
  dynamic  → Binance'den top-N by 24h volume
  hybrid   → fixed_core + dynamic top-N (dedup edilir)

Cache: dinamik listeyi config.symbols.refresh_dynamic_hours saatte bir yeniler.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta, timezone

log = logging.getLogger("efloud.universe")


class SymbolUniverse:
    """Watchlist resolver with caching."""

    def __init__(self, cfg: dict, client=None):
        """
        cfg: top-level bot config
        client: BinanceClient (dynamic mode için gerekli)
        """
        self.cfg = cfg
        self.client = client
        syms_cfg = cfg.get("symbols", {})

        # Backward compat: symbols: [list] direkt verilmişse fixed mode
        if isinstance(syms_cfg, list):
            self.mode = "fixed"
            self.fixed_core = list(syms_cfg)
            self.dynamic_top_n = 0
            self.exclude = []
            self.refresh_hours = 24
        else:
            self.mode = syms_cfg.get("mode", "fixed")
            self.fixed_core = list(syms_cfg.get("fixed_core", []))
            self.dynamic_top_n = int(syms_cfg.get("dynamic_top_n", 0))
            self.exclude = list(syms_cfg.get("dynamic_exclude", []))
            self.refresh_hours = float(syms_cfg.get("refresh_dynamic_hours", 24))

        self._cached_dynamic: List[str] = []
        self._cached_at: Optional[datetime] = None

    def resolve(self, force_refresh: bool = False) -> List[str]:
        """Aktif sembol listesi — cache'li."""
        if self.mode == "fixed":
            return list(self.fixed_core)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        needs_refresh = force_refresh or self._cached_at is None or \
                         (now - self._cached_at) > timedelta(hours=self.refresh_hours)

        if needs_refresh:
            self._refresh_dynamic()

        dyn = list(self._cached_dynamic)

        if self.mode == "dynamic":
            return dyn[:self.dynamic_top_n] if self.dynamic_top_n else dyn

        # hybrid
        combined = list(self.fixed_core)
        for s in dyn:
            if s in combined:
                continue
            if len(combined) >= len(self.fixed_core) + self.dynamic_top_n:
                break
            combined.append(s)
        return combined

    def _refresh_dynamic(self):
        """Binance'den top-volume çek. fixed_core ve stablecoin'leri hariç tut.

        Not: CCXT'de `fetch_tickers()` Binance futures'ta desteklenmiyor.
        Fallback stratejisi:
          1. Futures market ise direkt fapi_public_get_ticker_24hr çağır
          2. Başarısız olursa geçici spot client ile fetch_tickers dene
        """
        if self.client is None:
            log.warning("No exchange client — skipping dynamic refresh")
            return

        exclude_set = set(self.exclude) | set(self.fixed_core)
        usdt_pairs = []

        try:
            tickers_data = self._fetch_tickers_safe()
            for entry in tickers_data:
                sym = entry["symbol"]
                if not sym.endswith("/USDT"):
                    continue
                if sym in exclude_set:
                    continue
                if entry["volume"] <= 0:
                    continue
                usdt_pairs.append((sym, entry["volume"]))

            usdt_pairs.sort(key=lambda x: x[1], reverse=True)
            top = [s for s, v in usdt_pairs[:self.dynamic_top_n + 2]]

            self._cached_dynamic = top
            self._cached_at = datetime.now(timezone.utc).replace(tzinfo=None)

            log.info(f"🌐 Dynamic universe refreshed: top {len(top)} by 24h volume "
                     f"(excluded: {len(exclude_set)} symbols)")
            for i, (sym, vol) in enumerate(usdt_pairs[:self.dynamic_top_n], 1):
                log.info(f"   #{i:>2} {sym:<15} ${vol:>14,.0f}")

        except Exception as e:
            log.error(f"Dynamic symbol fetch failed: {e}")

    def _fetch_tickers_safe(self) -> list:
        """Futures + spot fallback. Returns list of {symbol, volume} dicts.

        Symbol format: 'BTC/USDT' (CCXT unified format)
        volume: 24h quoteVolume (USDT denominated)
        """
        import ccxt

        ex = self.client.exchange
        market_type = self.client.market_type

        # ── Attempt 1: futures endpoint (direct fapi call) ──
        if market_type == "futures":
            try:
                raw = ex.fapi_public_get_ticker_24hr()
                # raw format: [{symbol: 'BTCUSDT', quoteVolume: '...', ...}, ...]
                result = []
                for t in raw:
                    raw_sym = t.get("symbol", "")
                    # BTCUSDT → BTC/USDT (sadece /USDT ile bitenler)
                    if not raw_sym.endswith("USDT"):
                        continue
                    base = raw_sym[:-4]
                    unified = f"{base}/USDT"
                    result.append({
                        "symbol": unified,
                        "volume": float(t.get("quoteVolume") or 0),
                    })
                if result:
                    log.debug(f"Fetched {len(result)} futures tickers via fapi")
                    return result
            except Exception as e:
                log.debug(f"fapi ticker fetch failed: {e}, trying spot fallback")

        # ── Attempt 2: spot client (top volume coinler genelde aynı) ──
        try:
            spot_client = ccxt.binance({
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            })
            if self.client.testnet:
                spot_client.set_sandbox_mode(True)

            tickers = spot_client.fetch_tickers()
            result = []
            for sym, t in tickers.items():
                result.append({
                    "symbol": sym,
                    "volume": float(t.get("quoteVolume") or 0),
                })
            log.debug(f"Fetched {len(result)} spot tickers (futures fallback)")
            return result
        except Exception as e:
            log.error(f"Spot fallback also failed: {e}")
            return []
