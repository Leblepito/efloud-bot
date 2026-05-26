"""OANDA Forex Exchange Client — Phase 3.5.

Implements the ExchangeAdapter protocol for Forex trading via the OANDA v20 REST API.
Includes lazy import protections to allow running on systems without oandapyV20 installed.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

log = logging.getLogger("efloud.exchange.oanda")

class OandaClient:
    """Forex exchange adapter for OANDA Broker REST API.

    Maintains full compatibility with ExchangeAdapter and efloud trading engine.
    """

    def __init__(
        self,
        account_id: str = "",
        api_token: str = "",
        testnet: bool = True,
    ) -> None:
        self._account_id = account_id or os.environ.get("EFLOUD_OANDA_ACCOUNT_ID", "")
        self._api_token = api_token or os.environ.get("EFLOUD_OANDA_API_TOKEN", "")
        self._testnet = testnet
        self._market_type = "forex"
        self._client = self._import_oanda_client()

        if self._client is not None and self._account_id and self._api_token:
            log.info(f"✅ OANDA Client initialized for account: {self._account_id} (testnet={testnet})")
        else:
            log.warning("oandapyV20 package not available or credentials missing — running in mock/idle mode")

    @property
    def exchange(self) -> Any:
        """Returns the OANDA API client instance."""
        return self._client

    @property
    def market_type(self) -> str:
        return self._market_type

    @property
    def testnet(self) -> bool:
        return self._testnet

    def _import_oanda_client(self) -> Any:
        """Lazily imports the oandapyV20 client library."""
        try:
            import oandapyV20  # type: ignore[import]
            env = "practice" if self._testnet else "live"
            return oandapyV20.API(access_token=self._api_token, environment=env)
        except ImportError:
            return None

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Queries historical candles from OANDA v20 API."""
        if self._client is None or not self._api_token:
            # Mock return for testing
            idx = pd.date_range(end=datetime.now(timezone.utc), periods=limit, freq="15min")
            return pd.DataFrame(1.0, index=idx, columns=["open", "high", "low", "close", "volume"])

        from oandapyV20.endpoints import instruments  # type: ignore[import]

        symbol = self.to_ccxt_symbol(symbol)
        oanda_tf = self._map_timeframe(timeframe)
        params = {
            "count": limit,
            "granularity": oanda_tf,
            "price": "M",  # Midpoint pricing
        }

        r = instruments.InstrumentsCandles(instrument=symbol, params=params)
        try:
            self._client.request(r)
            candles = r.response.get("candles", [])
        except Exception as e:
            raise RuntimeError(f"OANDA candles fetch failed for {symbol}: {e}")

        cdata = []
        for c in candles:
            if not c.get("complete"):
                continue
            cdata.append({
                "timestamp": pd.to_datetime(c["time"]),
                "open": float(c["mid"]["o"]),
                "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]),
                "close": float(c["mid"]["c"]),
                "volume": float(c["volume"]),
            })

        df = pd.DataFrame(cdata)
        if len(df) > 0:
            df.set_index("timestamp", inplace=True)
        return df

    def to_ccxt_symbol(self, symbol: str) -> str:
        """OANDA formats Forex symbols with underscores (e.g. 'EUR_USD')."""
        return symbol.replace("/", "_").replace(":", "_")

    def get_balance(self) -> float:
        """Returns OANDA account Net Asset Value (NAV)."""
        if self._client is None or not self._api_token:
            return 10000.0

        from oandapyV20.endpoints import accounts  # type: ignore[import]
        r = accounts.AccountSummary(self._account_id)
        try:
            self._client.request(r)
            summary = r.response.get("account", {})
            return float(summary.get("NAV", 0.0))
        except Exception as e:
            log.warning(f"OANDA NAV fetch failed: {e}")
            return 0.0

    def get_available_margin(self) -> float:
        """Returns free margin available in the OANDA account."""
        if self._client is None or not self._api_token:
            return 10000.0

        from oandapyV20.endpoints import accounts  # type: ignore[import]
        r = accounts.AccountSummary(self._account_id)
        try:
            self._client.request(r)
            summary = r.response.get("account", {})
            return float(summary.get("marginAvailable", 0.0))
        except Exception as e:
            return 0.0

    def get_price(self, symbol: str) -> float:
        """Returns current midpoint price of the Forex pair."""
        if self._client is None or not self._api_token:
            return 1.1000

        from oandapyV20.endpoints import pricing  # type: ignore[import]
        symbol = self.to_ccxt_symbol(symbol)
        r = pricing.PricingInfo(accountID=self._account_id, params={"instruments": symbol})
        try:
            self._client.request(r)
            prices = r.response.get("prices", [])
            if prices:
                bids = prices[0].get("bids", [])
                asks = prices[0].get("asks", [])
                if bids and asks:
                    return (float(bids[0]["price"]) + float(asks[0]["price"])) / 2.0
            raise ValueError("No price prices in response")
        except Exception as e:
            raise RuntimeError(f"OANDA ticker pricing failed for {symbol}: {e}")

    def set_leverage(self, symbol: str, leverage: int) -> None:
        """OANDA leverage is configured globally at account registration and cannot be changed dynamically."""
        log.info(f"OANDA leverage set called for {symbol} to {leverage}x (account preset value used)")

    def set_margin_mode(self, symbol: str, mode: str = "ISOLATED") -> bool:
        """OANDA always uses crossed account margins (crossed leverage). Isolated is a no-op."""
        log.debug("OANDA uses account margin sharing (isolated mode set is no-op)")
        return True

    def set_position_mode(self, dual_side: bool = True) -> bool:
        """OANDA position holding constraints (hedging vs netting) are account-bound settings."""
        log.debug("OANDA position mode is predetermined by account type settings")
        return True

    def get_open_positions(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Queries OANDA open positions."""
        if self._client is None or not self._api_token:
            return []

        from oandapyV20.endpoints import positions  # type: ignore[import]
        r = positions.PositionList(self._account_id)
        try:
            self._client.request(r)
            pos_list = r.response.get("positions", [])
        except Exception as e:
            log.warning(f"OANDA get_open_positions failed: {e}")
            return []

        mapped = []
        for p in pos_list:
            # Check long side
            long_units = float(p.get("long", {}).get("units", 0.0))
            if long_units > 0:
                mapped.append({
                    "symbol": p["instrument"],
                    "contracts": long_units,
                    "side": "buy",
                    "entryPrice": float(p["long"].get("averagePrice", 0.0)),
                    "unrealizedPnl": float(p["long"].get("unrealizedPL", 0.0)),
                })
            # Check short side
            short_units = float(p.get("short", {}).get("units", 0.0))
            if short_units < 0:
                mapped.append({
                    "symbol": p["instrument"],
                    "contracts": abs(short_units),
                    "side": "sell",
                    "entryPrice": float(p["short"].get("averagePrice", 0.0)),
                    "unrealizedPnl": float(p["short"].get("unrealizedPL", 0.0)),
                })
        
        if symbol:
            symbol = self.to_ccxt_symbol(symbol)
            mapped = [m for m in mapped if m["symbol"] == symbol]
        return mapped

    def _map_timeframe(self, timeframe: str) -> str:
        """Maps unified efloud timeframes to OANDA granularity codes."""
        mapping = {
            "1m": "M1",
            "5m": "M5",
            "15m": "M15",
            "30m": "M30",
            "1h": "H1",
            "4h": "H4",
            "1d": "D",
        }
        return mapping.get(timeframe, "M15")
