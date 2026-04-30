"""Binance exchange client + order manager — CCXT tabanlı."""

import ccxt
import pandas as pd
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass, field

log = logging.getLogger("efloud.exchange")


class BinanceClient:
    """CCXT ile Binance Futures/Spot bağlantısı."""

    def __init__(self, api_key: str = "", api_secret: str = "",
                 testnet: bool = True, market_type: str = "futures"):
        opts = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": market_type},
        }
        if testnet:
            opts["sandbox"] = True

        self.exchange = ccxt.binance(opts)
        self.market_type = market_type
        self.testnet = testnet
        log.info(f"Binance {'testnet' if testnet else 'MAINNET'} | {market_type}")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Kline data çek → DataFrame."""
        raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        return df

    def get_balance(self) -> float:
        """USDT bakiye."""
        b = self.exchange.fetch_balance()
        return float(b.get("USDT", {}).get("free", 0))

    def get_price(self, symbol: str) -> float:
        """Anlık fiyat."""
        t = self.exchange.fetch_ticker(symbol)
        return float(t["last"])

    def set_leverage(self, symbol: str, leverage: int):
        """Futures leverage ayarla."""
        if self.market_type == "futures":
            try:
                self.exchange.set_leverage(leverage, symbol)
                log.info(f"Leverage set: {symbol} → {leverage}x")
            except Exception as e:
                log.warning(f"Leverage set failed: {e}")

    def set_margin_mode(self, symbol: str, mode: str = "ISOLATED") -> bool:
        """
        Futures margin mode ayarla: ISOLATED veya CROSSED.
        ISOLATED: her pozisyon kendi margin'i ile, biri diğerini etkilemez.
        CROSSED: tüm bakiye paylaşılır, biri likidasyona giderse diğerleri de etkilenir.

        Bot için ISOLATED zorunlu — risk izolasyonu kritik.
        """
        if self.market_type != "futures":
            return False
        try:
            self.exchange.set_margin_mode(mode, symbol)
            log.info(f"✅ Margin mode set: {symbol} → {mode}")
            return True
        except Exception as e:
            err_str = str(e).lower()
            # "no need to change" benzeri mesajlar zaten istenen durumda olduğunu gösterir
            if "no need" in err_str or "already" in err_str or "-4046" in err_str:
                log.debug(f"Margin mode already {mode} for {symbol}")
                return True
            log.warning(f"Margin mode set failed for {symbol}: {e}")
            return False

    def get_open_positions(self, symbol: str = None) -> list:
        """Açık pozisyonları getir."""
        if self.market_type != "futures":
            return []
        try:
            positions = self.exchange.fetch_positions([symbol] if symbol else None)
            return [p for p in positions if float(p.get("contracts", 0)) > 0]
        except Exception as e:
            log.error(f"Fetch positions error: {e}")
            return []


@dataclass
class Position:
    symbol: str
    direction: str          # "LONG" | "SHORT"
    entry: float
    sl: float
    tp1: float
    tp2: float
    size: float             # Kontrat sayısı
    order_id: str = ""
    sl_order_id: str = ""
    tp1_order_id: str = ""
    tp1_hit: bool = False   # TP1'e ulaştı mı (yarı kapat + SL trail)
    opened_at: str = ""


class OrderManager:
    """Pozisyon açma, kapatma, SL/TP yönetimi."""

    def __init__(self, client: BinanceClient, dry_run: bool = True):
        self.client = client
        self.dry_run = dry_run
        self.positions: List[Position] = []

    def open_position(self, symbol: str, direction: str, size: float,
                      entry: float, sl: float, tp1: float, tp2: float) -> Optional[Position]:
        """Yeni pozisyon aç."""
        side = "buy" if direction == "LONG" else "sell"

        if self.dry_run:
            log.info(f"[DRY] {direction} {symbol} size={size:.4f} @ {entry:.2f} | SL={sl:.2f} TP1={tp1:.2f} TP2={tp2:.2f}")
            pos = Position(symbol, direction, entry, sl, tp1, tp2, size,
                           opened_at=pd.Timestamp.now().isoformat())
            self.positions.append(pos)
            return pos

        try:
            # Market order
            order = self.client.exchange.create_order(symbol, "market", side, size)
            oid = order.get("id", "")
            log.info(f"MARKET {direction} {symbol} size={size} | order_id={oid}")

            # SL order
            sl_side = "sell" if direction == "LONG" else "buy"
            sl_params = {"stopPrice": sl, "reduceOnly": True}
            sl_order = self.client.exchange.create_order(
                symbol, "STOP", sl_side, size, sl, params=sl_params)

            pos = Position(symbol, direction, entry, sl, tp1, tp2, size,
                           oid, sl_order.get("id", ""),
                           opened_at=pd.Timestamp.now().isoformat())
            self.positions.append(pos)
            return pos

        except Exception as e:
            log.error(f"Order failed: {e}")
            return None

    def check_positions(self):
        """Açık pozisyonları kontrol — TP1/TP2/SL takibi."""
        for pos in self.positions[:]:
            try:
                price = self.client.get_price(pos.symbol)
            except Exception:
                continue

            is_long = pos.direction == "LONG"

            # SL kontrolü
            if (is_long and price <= pos.sl) or (not is_long and price >= pos.sl):
                self._close(pos, price, "SL HIT")
                continue

            # TP2 kontrolü (tam kapat)
            if (is_long and price >= pos.tp2) or (not is_long and price <= pos.tp2):
                self._close(pos, price, "TP2 HIT")
                continue

            # TP1 kontrolü (yarı kapat + SL → entry)
            if not pos.tp1_hit:
                if (is_long and price >= pos.tp1) or (not is_long and price <= pos.tp1):
                    pos.tp1_hit = True
                    pos.sl = pos.entry  # SL'yi break-even'a çek
                    log.info(f"TP1 HIT: {pos.symbol} | SL → break-even @ {pos.entry}")

                    if not self.dry_run:
                        # Yarısını kapat
                        half = pos.size / 2
                        close_side = "sell" if is_long else "buy"
                        try:
                            self.client.exchange.create_order(
                                pos.symbol, "market", close_side, half,
                                params={"reduceOnly": True})
                            pos.size = pos.size - half
                        except Exception as e:
                            log.error(f"TP1 partial close failed: {e}")

    def _close(self, pos: Position, price: float, reason: str):
        """Pozisyonu kapat."""
        pnl_pct = ((price - pos.entry) / pos.entry * 100) if pos.direction == "LONG" else \
                  ((pos.entry - price) / pos.entry * 100)

        log.info(f"{reason}: {pos.symbol} {pos.direction} | Entry={pos.entry:.2f} Exit={price:.2f} | PnL={pnl_pct:+.2f}%")

        if not self.dry_run:
            close_side = "sell" if pos.direction == "LONG" else "buy"
            try:
                self.client.exchange.create_order(
                    pos.symbol, "market", close_side, pos.size,
                    params={"reduceOnly": True})
            except Exception as e:
                log.error(f"Close failed: {e}")

        self.positions.remove(pos)

    @property
    def open_count(self) -> int:
        return len(self.positions)
