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
        # Suppress CCXT's "warning" about fetching open orders without a symbol
        # (we intentionally fetch all open orders for reconcile; CCXT raises this
        # as an exception which would otherwise break the reconcile loop).
        self.exchange.options["warnOnFetchOpenOrdersWithoutSymbol"] = False
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

    def to_ccxt_symbol(self, symbol: str) -> str:
        """CCXT exchange'e gönderilecek symbol formatı.

        Spot:    'BTC/USDT' → 'BTC/USDT'
        Futures: 'BTC/USDT' → 'BTC/USDT:USDT' (linear/USDM, collateral notation)

        defaultType=future ayarına rağmen CCXT'nin create_order'ı symbol'i
        spot olarak yorumluyor → /api/v3/order'a gidiyor (spot endpoint).
        ':USDT' suffix'i futures route'unu zorlar → /fapi/v1/order.
        """
        if self.market_type != "futures":
            return symbol
        if ":" in symbol:
            return symbol  # zaten formatted
        return f"{symbol}:USDT"

    def get_balance(self) -> float:
        """USDT free balance.

        Futures için: /fapi/v2/account 'availableBalance' field'ı
        (fetch_balance bazen futures USDT'yi top-level key olarak döndürmez,
        defaultType=future olsa bile sıfır gelebilir).
        """
        if self.market_type == "futures":
            try:
                info = self.exchange.fapiPrivateV2GetAccount()
                return float(info.get("availableBalance", 0))
            except Exception as e:
                log.warning(f"futures balance fetch failed: {e} — falling back to fetch_balance")
        b = self.exchange.fetch_balance()
        return float(b.get("USDT", {}).get("free", 0))

    def get_price(self, symbol: str) -> float:
        """Anlık fiyat."""
        t = self.exchange.fetch_ticker(symbol)
        return float(t["last"])

    def set_leverage(self, symbol: str, leverage: int):
        """Futures leverage ayarla — direct fapi endpoint kullanır.

        ccxt.set_leverage symbol parse'ında hata veriyor ('linear/inverse only').
        Bu yüzden direct /fapi/v1/leverage çağrısı yapıyoruz.
        """
        if self.market_type != "futures":
            return
        binance_sym = symbol.replace("/", "")
        try:
            self.exchange.fapiPrivatePostLeverage({
                "symbol": binance_sym,
                "leverage": int(leverage),
            })
            log.info(f"Leverage set: {symbol} → {leverage}x")
        except Exception as e:
            log.warning(f"Leverage set failed for {symbol}: {e}")

    def set_margin_mode(self, symbol: str, mode: str = "ISOLATED") -> bool:
        """Futures margin mode — direct /fapi/v1/marginType.

        ISOLATED: her pozisyon kendi margin'i ile, biri diğerini etkilemez.
        CROSSED: tüm bakiye paylaşılır.

        Bot için ISOLATED zorunlu — risk izolasyonu kritik.
        """
        if self.market_type != "futures":
            return False
        binance_sym = symbol.replace("/", "")
        try:
            self.exchange.fapiPrivatePostMarginType({
                "symbol": binance_sym,
                "marginType": mode.upper(),
            })
            log.info(f"✅ Margin mode set: {symbol} → {mode}")
            return True
        except Exception as e:
            err_str = str(e).lower()
            # -4046 = "No need to change margin type" (zaten istenen modda)
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
    size: float             # Kontrat sayısı (toplam — TP1 hit'ten sonra yarısı remaining)
    order_id: str = ""
    sl_order_id: str = ""
    tp1_order_id: str = ""
    tp2_order_id: str = ""
    tp1_hit: bool = False   # TP1 fill oldu mu (server-side detect via reconcile)
    opened_at: str = ""
    closed_at: str = ""
    exit_reason: str = ""   # "TP1" | "TP2" | "SL" | "MANUAL" | "RECONCILED"
    exit_price: float = 0.0
    pnl_usdt: float = 0.0


class OrderManager:
    """Pozisyon açma + server-side TP/SL + reconciliation.

    v2.2 refactor:
    - TP1/TP2 server-side TAKE_PROFIT_MARKET orders (0ms execution)
    - reconcile() her cycle başı Binance ↔ local sync
    - check_positions() → backup polling fallback (network kopukluğu vs.)
    """

    def __init__(self, client: BinanceClient, dry_run: bool = True,
                 on_position_change=None):
        self.client = client
        self.dry_run = dry_run
        self.positions: List[Position] = []
        self.closed_positions: List[Position] = []  # son kapanan pozisyon history (DB'ye yazılır)
        self.on_position_change = on_position_change  # callback (event_type, position) — WS push için

    # ─────────────────────────────────────────────────────────────
    # Open / Close
    # ─────────────────────────────────────────────────────────────

    def open_position(self, symbol: str, direction: str, size: float,
                      entry: float, sl: float, tp1: float, tp2: float) -> Optional[Position]:
        """Yeni pozisyon aç + server-side SL + TP1 (yarı) + TP2 (yarı) yerleştir."""
        side = "buy" if direction == "LONG" else "sell"
        reverse_side = "sell" if direction == "LONG" else "buy"
        half_size = size / 2

        if self.dry_run:
            log.info(f"[DRY] {direction} {symbol} size={size:.4f} @ {entry:.2f} | "
                     f"SL={sl:.2f} TP1={tp1:.2f} TP2={tp2:.2f}")
            pos = Position(symbol, direction, entry, sl, tp1, tp2, size,
                           opened_at=pd.Timestamp.now().isoformat())
            self.positions.append(pos)
            self._emit("position_opened", pos)
            return pos

        # CCXT'nin futures route'una gitmesi için symbol'i collateral notation ile sar
        ccxt_sym = self.client.to_ccxt_symbol(symbol)

        try:
            # 1) Market entry order
            entry_order = self.client.exchange.create_order(ccxt_sym, "market", side, size)
            oid = entry_order.get("id", "")
            log.info(f"MARKET {direction} {symbol} size={size} | order_id={oid}")

            # 2) Server-side SL — STOP_MARKET reduceOnly
            sl_order = self.client.exchange.create_order(
                ccxt_sym, "STOP_MARKET", reverse_side, size,
                params={"stopPrice": sl, "reduceOnly": True}
            )
            sl_oid = sl_order.get("id", "")
            log.info(f"  ↳ SL @ {sl:.4f} | order_id={sl_oid}")

            # 3) Server-side TP1 — TAKE_PROFIT_MARKET, yarı boyut, reduceOnly
            tp1_order = self.client.exchange.create_order(
                ccxt_sym, "TAKE_PROFIT_MARKET", reverse_side, half_size,
                params={"stopPrice": tp1, "reduceOnly": True}
            )
            tp1_oid = tp1_order.get("id", "")
            log.info(f"  ↳ TP1 @ {tp1:.4f} (size={half_size:.4f}) | order_id={tp1_oid}")

            # 4) Server-side TP2 — kalan yarı
            tp2_order = self.client.exchange.create_order(
                ccxt_sym, "TAKE_PROFIT_MARKET", reverse_side, size - half_size,
                params={"stopPrice": tp2, "reduceOnly": True}
            )
            tp2_oid = tp2_order.get("id", "")
            log.info(f"  ↳ TP2 @ {tp2:.4f} (size={size - half_size:.4f}) | order_id={tp2_oid}")

            pos = Position(
                symbol=symbol, direction=direction, entry=entry,
                sl=sl, tp1=tp1, tp2=tp2, size=size,
                order_id=oid, sl_order_id=sl_oid,
                tp1_order_id=tp1_oid, tp2_order_id=tp2_oid,
                opened_at=pd.Timestamp.now().isoformat(),
            )
            self.positions.append(pos)
            self._emit("position_opened", pos)
            return pos

        except Exception as e:
            log.error(f"Order failed for {symbol}: {e}", exc_info=True)
            # Best-effort cleanup: market order başarılı olduysa pozisyon açılmış demektir,
            # ama SL/TP order'ları başarısız olduysa bot pozisyonu izlemez. Manual kapatma gerekir.
            return None

    # ─────────────────────────────────────────────────────────────
    # Reconciliation — primary source of truth for closes
    # ─────────────────────────────────────────────────────────────

    def reconcile(self) -> List[Position]:
        """Her cycle başı: Binance ↔ local pozisyon karşılaştır.

        Returns: Bu cycle'da kapanmış pozisyonlar.

        Algorithm:
        - Binance positions fetch → "contracts" sayısı 0 olan = kapalı
        - Binance open orders fetch → TP1 order'ı listede yoksa = filled (TP1 hit)
        - Filled TP1 → SL'i break-even'a kaydır (eski SL cancel + yeni SL @ entry)
        """
        if self.dry_run:
            return []

        try:
            bn_positions = self.client.get_open_positions()
        except Exception as e:
            log.warning(f"Reconcile: positions fetch failed: {e}")
            return []

        bn_orders_raw: list = []
        bn_order_ids: set = set()
        try:
            bn_orders_raw = self.client.exchange.fetch_open_orders()
            bn_order_ids = {str(o.get("id", "")) for o in bn_orders_raw}
        except Exception as e:
            log.warning(f"Reconcile: open orders fetch failed: {e}")
            # bn_orders_raw stays []; bn_order_ids stays empty set

        # Binance'deki açık pozisyon symbol'leri
        bn_open_symbols = {p["symbol"] for p in bn_positions if float(p.get("contracts", 0)) > 0}

        closed_now: List[Position] = []

        for pos in self.positions[:]:
            if pos.symbol not in bn_open_symbols:
                # Pozisyon Binance'de kapanmış — TP2 / SL / manual close
                exit_price = self._estimate_exit_price(pos, bn_orders_raw)
                self._record_close(pos, exit_price, reason="RECONCILED")
                closed_now.append(pos)
                self.positions.remove(pos)
                continue

            # Pozisyon hâlâ açık — TP1 fill kontrolü
            if pos.tp1_order_id and not pos.tp1_hit:
                if pos.tp1_order_id not in bn_order_ids:
                    # TP1 order'ı kaybolmuş = filled
                    pos.tp1_hit = True
                    log.info(f"RECONCILE: TP1 hit {pos.symbol} → SL → break-even @ {pos.entry}")
                    self._move_sl_to_breakeven(pos)
                    self._emit("tp1_hit", pos)

        return closed_now

    def _move_sl_to_breakeven(self, pos: Position) -> None:
        """TP1 hit sonrası SL'i entry'ye kaydır (server-side cancel + new order)."""
        if self.dry_run:
            pos.sl = pos.entry
            return

        ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
        try:
            if pos.sl_order_id:
                try:
                    self.client.exchange.cancel_order(pos.sl_order_id, ccxt_sym)
                except Exception as e:
                    log.warning(f"SL cancel failed for {pos.symbol}: {e} (continuing)")

            reverse_side = "sell" if pos.direction == "LONG" else "buy"
            remaining_size = pos.size / 2  # TP1 yarısı kapandı, kalan yarısı için SL
            new_sl = self.client.exchange.create_order(
                ccxt_sym, "STOP_MARKET", reverse_side, remaining_size,
                params={"stopPrice": pos.entry, "reduceOnly": True}
            )
            pos.sl = pos.entry
            pos.sl_order_id = new_sl.get("id", "")
            log.info(f"  ↳ New SL @ break-even {pos.entry:.4f} | order_id={pos.sl_order_id}")
        except Exception as e:
            log.error(f"Move-SL-to-breakeven failed for {pos.symbol}: {e}")

    def _estimate_exit_price(self, pos: Position, bn_orders: list) -> float:
        """Reconcile sırasında exit price tahmin et.

        Hangi order tetiklendi? — bn_orders listesinde olmayan TP/SL order'ı = filled.
        """
        # TP2 / TP1 / SL'den hangisi yoksa o tetiklenmiş demektir
        order_ids = {str(o.get("id", "")) for o in bn_orders}

        if pos.tp2_order_id and pos.tp2_order_id not in order_ids:
            return pos.tp2  # TP2 hit
        if pos.sl_order_id and pos.sl_order_id not in order_ids:
            return pos.sl   # SL hit
        if pos.tp1_order_id and pos.tp1_order_id not in order_ids and not pos.tp1_hit:
            return pos.tp1
        # Fallback: current market price
        try:
            return self.client.get_price(pos.symbol)
        except Exception:
            return pos.entry

    def _record_close(self, pos: Position, exit_price: float, reason: str) -> None:
        """Pozisyon kapanış metadata'sını doldur ve event emit et."""
        is_long = pos.direction == "LONG"
        pnl_pct = ((exit_price - pos.entry) / pos.entry * 100) if is_long else \
                  ((pos.entry - exit_price) / pos.entry * 100)
        pnl_usdt = (exit_price - pos.entry) * pos.size if is_long else \
                   (pos.entry - exit_price) * pos.size

        pos.closed_at = pd.Timestamp.now().isoformat()
        pos.exit_reason = reason
        pos.exit_price = exit_price
        pos.pnl_usdt = pnl_usdt

        log.info(
            f"{reason}: {pos.symbol} {pos.direction} | "
            f"Entry={pos.entry:.4f} Exit={exit_price:.4f} | "
            f"PnL={pnl_pct:+.2f}% (${pnl_usdt:+.2f})"
        )

        self.closed_positions.append(pos)
        self._emit("position_closed", pos)

    # ─────────────────────────────────────────────────────────────
    # Backup polling (network/order issues fallback)
    # ─────────────────────────────────────────────────────────────

    def check_positions(self):
        """Backup polling — sadece network/Binance kopukluğunda devreye girer.

        Server-side TP/SL primary path. Bu fonksiyon defensive fallback:
        eğer reconcile() çalışmadıysa veya order'lar yerleşmediyse polling ile
        yedek koruma. Production'da nadiren tetiklenir.
        """
        for pos in self.positions[:]:
            try:
                price = self.client.get_price(pos.symbol)
            except Exception:
                continue

            is_long = pos.direction == "LONG"

            # SL fallback
            if (is_long and price <= pos.sl) or (not is_long and price >= pos.sl):
                log.warning(f"Polling SL hit detected for {pos.symbol} (server-side missed?)")
                self._fallback_close(pos, price, "SL_POLL")
                continue

            # TP2 fallback
            if (is_long and price >= pos.tp2) or (not is_long and price <= pos.tp2):
                log.warning(f"Polling TP2 hit detected for {pos.symbol} (server-side missed?)")
                self._fallback_close(pos, price, "TP2_POLL")

    def _fallback_close(self, pos: Position, price: float, reason: str):
        """Polling fallback: market close + cancel pending TP/SL orders."""
        if not self.dry_run:
            close_side = "sell" if pos.direction == "LONG" else "buy"
            ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
            try:
                self.client.exchange.create_order(
                    ccxt_sym, "market", close_side, pos.size,
                    params={"reduceOnly": True})
            except Exception as e:
                log.error(f"Fallback close failed: {e}")

            # Pending order cleanup
            for oid in [pos.sl_order_id, pos.tp1_order_id, pos.tp2_order_id]:
                if oid:
                    try:
                        self.client.exchange.cancel_order(oid, ccxt_sym)
                    except Exception:
                        pass

        self._record_close(pos, price, reason)
        self.positions.remove(pos)

    def kill_switch(self) -> int:
        """Tüm açık pozisyonları piyasa fiyatından kapat + tüm pending order'ları iptal et.

        Frontend kill switch butonunun çağıracağı endpoint. Returns: kapatılan pozisyon sayısı.
        """
        count = 0
        for pos in self.positions[:]:
            try:
                price = self.client.get_price(pos.symbol)
            except Exception:
                price = pos.entry  # fallback
            self._fallback_close(pos, price, "KILL_SWITCH")
            count += 1
        log.error(f"⛔ KILL SWITCH activated: closed {count} positions")
        return count

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _emit(self, event: str, position: Position) -> None:
        """Event callback (WebSocket push için)."""
        if self.on_position_change:
            try:
                self.on_position_change(event, position)
            except Exception as e:
                log.warning(f"Event callback failed: {e}")

    @property
    def open_count(self) -> int:
        return len(self.positions)
