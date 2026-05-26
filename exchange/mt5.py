"""MetaTrader 5 (MT5) Forex Exchange Client — Phase 3.5.

Implements the ExchangeAdapter protocol for Forex trading via the MT5 terminal.
Includes lazy import protections to allow running on non-Windows/no-MT5 systems.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

log = logging.getLogger("efloud.exchange.mt5")

class MT5Client:
    """Forex exchange adapter for MetaTrader 5 terminal.

    Maintains full compatibility with ExchangeAdapter and efloud trading engine.
    """

    def __init__(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        testnet: bool = True,
    ) -> None:
        self._login = login or int(os.environ.get("EFLOUD_MT5_LOGIN", 0))
        self._password = password or os.environ.get("EFLOUD_MT5_PASSWORD", "")
        self._server = server or os.environ.get("EFLOUD_MT5_SERVER", "")
        self._testnet = testnet
        self._market_type = "forex"
        self._mt5 = self._import_mt5()

        if self._mt5 is not None:
            self._initialize()
        else:
            log.warning("MetaTrader5 package not available or failed to import — running in mock/idle mode")

    @property
    def exchange(self) -> Any:
        """Returns the raw MT5 library wrapper."""
        return self._mt5

    @property
    def market_type(self) -> str:
        return self._market_type

    @property
    def testnet(self) -> bool:
        return self._testnet

    def _import_mt5(self) -> Any:
        """Lazily imports the MetaTrader5 library."""
        try:
            import MetaTrader5 as mt5  # type: ignore[import]
            return mt5
        except ImportError:
            return None

    def _initialize(self) -> None:
        """Establishes connection to the MT5 terminal."""
        if not self._mt5.initialize(login=self._login, password=self._password, server=self._server):
            err = self._mt5.last_error()
            log.error(f"MT5 terminal initialization failed: {err}")
            raise RuntimeError(f"MT5 init failed: {err}")
        log.info(f"✅ Connected to MT5 Server: {self._server} (Login: {self._login})")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Queries historical bars from the MT5 terminal."""
        if self._mt5 is None:
            # Mock return for testing
            idx = pd.date_range(end=datetime.now(timezone.utc), periods=limit, freq="15min")
            return pd.DataFrame(1.0, index=idx, columns=["open", "high", "low", "close", "volume"])

        mt5_tf = self._map_timeframe(timeframe)
        rates = self._mt5.copy_rates_from_pos(symbol, mt5_tf, 0, limit)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"Failed to copy rates for {symbol}: {self._mt5.last_error()}")

        df = pd.DataFrame(rates)
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("timestamp", inplace=True)
        # Rename to unified efloud columns
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    def to_ccxt_symbol(self, symbol: str) -> str:
        """MT5 formats Forex symbols as simple text (e.g. 'EURUSD' or 'EURUSD.pro')."""
        return symbol.replace("/", "").replace(":", "")

    def get_balance(self) -> float:
        """Returns MT5 account equity (Cash Balance + Floating PnL)."""
        if self._mt5 is None:
            return 10000.0
        acc = self._mt5.account_info()
        if acc is None:
            log.warning(f"Could not retrieve MT5 account info: {self._mt5.last_error()}")
            return 0.0
        return float(acc.equity)

    def get_available_margin(self) -> float:
        """Returns free margin available for sizing new positions."""
        if self._mt5 is None:
            return 10000.0
        acc = self._mt5.account_info()
        if acc is None:
            return 0.0
        return float(acc.margin_free)

    def get_price(self, symbol: str) -> float:
        """Returns the current Ask/Bid midpoint price of the Forex pair."""
        if self._mt5 is None:
            return 1.1000
        symbol = self.to_ccxt_symbol(symbol)
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"Symbol {symbol} ticker not found: {self._mt5.last_error()}")
        return float((tick.ask + tick.bid) / 2.0)

    def set_leverage(self, symbol: str, leverage: int) -> None:
        """MT5 leverage is set at the account level; symbol-level leverage is a no-op."""
        log.info(f"MT5 set_leverage called for {symbol} to {leverage}x (account-level configuration)")

    def set_margin_mode(self, symbol: str, mode: str = "ISOLATED") -> bool:
        """Forex accounts always use crossed portfolio margin (crossed leverage). Isolated is no-op."""
        log.debug("MT5 uses crossed account margin model (default isolated set is no-op)")
        return True

    def set_position_mode(self, dual_side: bool = True) -> bool:
        """MT5 account hedging configuration is locked by the broker (hedging vs netting)."""
        log.debug("MT5 position mode is dictated by account type (Hedging vs Netting)")
        return True

    def get_open_positions(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Queries MT5 open orders/positions and maps them to standard format."""
        if self._mt5 is None:
            return []

        symbol = self.to_ccxt_symbol(symbol) if symbol else None
        positions = self._mt5.positions_get(symbol=symbol) if symbol else self._mt5.positions_get()
        if positions is None:
            return []

        mapped = []
        for p in positions:
            mapped.append({
                "symbol": p.symbol,
                "contracts": float(p.volume),
                "side": "buy" if p.type == self._mt5.POSITION_TYPE_BUY else "sell",
                "entryPrice": float(p.price_open),
                "unrealizedPnl": float(p.profit),
            })
        return mapped

    def _map_timeframe(self, timeframe: str) -> Any:
        """Maps unified efloud timeframes to MT5 timeframe constants."""
        if self._mt5 is None:
            return 15
        mapping = {
            "1m": self._mt5.TIMEFRAME_M1,
            "5m": self._mt5.TIMEFRAME_M5,
            "15m": self._mt5.TIMEFRAME_M15,
            "30m": self._mt5.TIMEFRAME_M30,
            "1h": self._mt5.TIMEFRAME_H1,
            "4h": self._mt5.TIMEFRAME_H4,
            "1d": self._mt5.TIMEFRAME_D1,
        }
        return mapping.get(timeframe, self._mt5.TIMEFRAME_M15)
