"""Exchange Adapter Protocol — Phase 3.5.

Defines the pluggable structural Protocol (interface) for all exchange and broker
adapters (Crypto CCXT, Forex MT5, Forex OANDA), allowing the trading engine to be
completely broker-agnostic.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol
import pandas as pd


class ExchangeAdapter(Protocol):
    """Structural Protocol (PEP 544) for efloud exchange adapters.

    All concrete clients (BinanceClient, MT5Client, OandaClient) must implement
    these methods and attributes. SafeOrchestrator and OrderManager interact
    with exchanges exclusively through this interface.
    """

    @property
    def exchange(self) -> Any:
        """Returns the underlying exchange/broker raw API or CCXT instance."""
        ...

    @property
    def market_type(self) -> str:
        """Returns the market classification (e.g. 'futures', 'spot', 'forex')."""
        ...

    @property
    def testnet(self) -> bool:
        """True if connected to sandbox / demo environment."""
        ...

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Kline / historical candle data query → DataFrame with index 'timestamp'."""
        ...

    def to_ccxt_symbol(self, symbol: str) -> str:
        """Formats the trade symbol matching the underlying API structure."""
        ...

    def get_balance(self) -> float:
        """Returns total account equity (wallet cash + unrealized P&L)."""
        ...

    def get_available_margin(self) -> float:
        """Returns available free margin (cash not locked in active margin)."""
        ...

    def get_price(self, symbol: str) -> float:
        """Returns the latest ticker last price of the instrument."""
        ...

    def set_leverage(self, symbol: str, leverage: int) -> None:
        """Configures leverage / gearing multiplier for the instrument."""
        ...

    def set_margin_mode(self, symbol: str, mode: str = "ISOLATED") -> bool:
        """Sets margin collateral mode (isolated vs crossed margin)."""
        ...

    def set_position_mode(self, dual_side: bool = True) -> bool:
        """Enables Hedge Mode (true) or One-way position holding (false)."""
        ...

    def get_open_positions(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Returns a list of active open positions for a symbol (or all)."""
        ...
