"""Binance exchange client + order manager — CCXT tabanlı."""

import ccxt
import json
import os
import pandas as pd
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict

log = logging.getLogger("efloud.exchange")


def _strip_contract_suffix(symbol: str) -> str:
    """Normalize CCXT futures contract notation: 'FIL/USDT:USDT' → 'FIL/USDT'.

    CCXT returns linear futures symbols with a `:USDT` (or `:USDC`) suffix from
    `fetch_positions` and similar endpoints, but local Position objects are
    tracked in slash-only form. This helper bridges the two so symbol set
    comparisons (e.g. in reconcile) don't silently fail when both sides come
    from different CCXT call paths.
    """
    return symbol.split(":", 1)[0] if ":" in symbol else symbol


class BinanceClient:
    """CCXT ile Binance Futures/Spot bağlantısı."""

    def __init__(self, api_key: str = "", api_secret: str = "",
                 testnet: bool = True, market_type: str = "futures"):
        # CCXT 4.x binance only accepts 'spot|future|margin|delivery|option' for
        # options.defaultType. The bot uses 'futures' (plural) as its own internal
        # market_type label (40+ `== "futures"` comparisons across the codebase),
        # so we normalize here for CCXT and leave self.market_type unchanged.
        # Without this normalization, fetch_open_orders silently falls through
        # is_linear/is_inverse and routes to /api/v3/openOrders (spot) — see the
        # 2026-05-08 reconcile-blindspot incident.
        ccxt_default_type = "future" if market_type == "futures" else market_type
        opts = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": ccxt_default_type},
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
        """USDT total margin balance — mark-to-market equity (wallet + unrealized PnL).

        For futures: /fapi/v2/account 'totalMarginBalance' field. This is the right
        metric for risk breakers (emergency threshold, daily-loss, drawdown) because
        it captures both wallet cash AND unrealized PnL on open positions. Returning
        'availableBalance' here would falsely halt the breaker whenever positions are
        open (margin locked → availableBalance < threshold even when wallet is fine).

        Spot fallback returns USDT 'total' (free + locked) for the same reason.
        """
        if self.market_type == "futures":
            try:
                info = self.exchange.fapiPrivateV2GetAccount()
                return float(info.get("totalMarginBalance", 0))
            except Exception as e:
                log.warning(f"futures balance fetch failed: {e} — falling back to fetch_balance")
        b = self.exchange.fetch_balance()
        return float(b.get("USDT", {}).get("total", 0))

    def get_available_margin(self) -> float:
        """USDT available margin — free balance not locked in open positions.

        For futures: /fapi/v2/account 'availableBalance' field. This is the right
        metric for *new-position sizing decisions* — it answers "how much margin
        do I have left to deploy?" rather than "what's my total equity?".

        Note: get_balance() returns totalMarginBalance (wallet + unrealized PnL),
        which is the right metric for risk breakers (drawdown, daily-loss). The
        two methods serve different purposes; both are valid and intentional.

        Spot fallback returns USDT 'free' (not 'total'), since locked balance is
        economically committed and shouldn't size new entries.
        """
        if self.market_type == "futures":
            try:
                info = self.exchange.fapiPrivateV2GetAccount()
                return float(info.get("availableBalance", 0))
            except Exception as e:
                log.warning(f"futures available margin fetch failed: {e} — falling back to fetch_balance")
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
        """Açık pozisyonları getir.

        Raises on transport/API failure — callers must distinguish 'no positions'
        from 'fetch failed'. Reconcile relies on this distinction: silently
        returning [] on exception caused the 2026-05-08 stacking bug where
        every API hiccup was interpreted as 'all positions closed', wiping
        local state and letting the next signal re-open + restack TP/SL trios.
        """
        if self.market_type != "futures":
            return []
        positions = self.exchange.fetch_positions([symbol] if symbol else None)
        return [p for p in positions if float(p.get("contracts", 0)) > 0]


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
    trace_id: Optional[str] = None       # log correlation across orchestrator → DB
    bar_ts_ms: Optional[int] = None      # bar-aligned timestamp (UTC ms epoch)


class OrderManager:
    """Pozisyon açma + server-side TP/SL + reconciliation.

    v2.2 refactor:
    - TP1/TP2 server-side TAKE_PROFIT_MARKET orders (0ms execution)
    - reconcile() her cycle başı Binance ↔ local sync
    - check_positions() → backup polling fallback (network kopukluğu vs.)
    """

    def __init__(self, client: BinanceClient, dry_run: bool = True,
                 on_position_change=None, state_dir: Optional[str] = None,
                 orphan_protector=None):
        self.client = client
        self.dry_run = dry_run
        self.positions: List[Position] = []
        self.closed_positions: List[Position] = []  # son kapanan pozisyon history (DB'ye yazılır)
        self.on_position_change = on_position_change  # callback (event_type, position) — WS push için
        self.orphan_protector = orphan_protector

        # Persistence — state_dir=None disables it (keeps old test fixtures working).
        # When set, self.positions is mirrored to a JSON file after every state
        # change so a restart picks up the same open positions and PositionGuard's
        # duplicate-direction check stays effective. See 2026-05-08 stacking bug
        # for why this matters in production.
        self._state_dir: Optional[Path] = Path(state_dir) if state_dir else None
        self._state_file: Optional[Path] = (
            self._state_dir / "order_manager_positions.json" if self._state_dir else None
        )
        if self._state_dir is not None:
            self._restore()

    # ─────────────────────────────────────────────────────────────
    # Open / Close
    # ─────────────────────────────────────────────────────────────

    def open_position(self, symbol: str, direction: str, size: float,
                      entry: float, sl: float, tp1: float, tp2: float,
                      trace_id: Optional[str] = None,
                      bar_ts_ms: Optional[int] = None) -> Optional[Position]:
        """Yeni pozisyon aç + server-side SL + TP1 (yarı) + TP2 (yarı) yerleştir.

        trace_id / bar_ts_ms: optional log-correlation + bar-alignment metadata
        forwarded into the Position dataclass; bot_runner persists them through
        the cross-thread DB callback. Both default to None for backwards compat
        (orchestrator paths that don't yet thread them through).
        """
        side = "buy" if direction == "LONG" else "sell"
        reverse_side = "sell" if direction == "LONG" else "buy"
        half_size = size / 2

        if self.dry_run:
            log.info(f"[DRY] {direction} {symbol} size={size:.4f} @ {entry:.2f} | "
                     f"SL={sl:.2f} TP1={tp1:.2f} TP2={tp2:.2f}")
            pos = Position(symbol, direction, entry, sl, tp1, tp2, size,
                           opened_at=pd.Timestamp.now(tz="UTC").isoformat(),
                           trace_id=trace_id, bar_ts_ms=bar_ts_ms)
            self.positions.append(pos)
            self._persist()
            self._emit("position_opened", pos)
            return pos

        # CCXT'nin futures route'una gitmesi için symbol'i collateral notation ile sar
        ccxt_sym = self.client.to_ccxt_symbol(symbol)

        try:
            # 1) Market entry order
            entry_order = self.client.exchange.create_order(ccxt_sym, "market", side, size)
            oid = entry_order.get("id", "")
            # Capture actual fill price (slippage tracking).
            # CCXT market orders return `average` (preferred) or `price` after fill.
            actual_entry = entry
            raw_avg = entry_order.get("average") or entry_order.get("price") or 0
            try:
                fill_price = float(raw_avg) if raw_avg else 0.0
            except (TypeError, ValueError):
                fill_price = 0.0
            if fill_price > 0:
                actual_entry = fill_price
                slip_pct = ((actual_entry - entry) / entry * 100) if entry else 0.0
                log.info(
                    f"MARKET {direction} {symbol} size={size} fill={actual_entry:.4f} "
                    f"(signal={entry:.4f}, slip={slip_pct:+.3f}%) | order_id={oid}"
                )
            else:
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
                symbol=symbol, direction=direction, entry=actual_entry,
                sl=sl, tp1=tp1, tp2=tp2, size=size,
                order_id=oid, sl_order_id=sl_oid,
                tp1_order_id=tp1_oid, tp2_order_id=tp2_oid,
                opened_at=pd.Timestamp.now(tz="UTC").isoformat(),
                trace_id=trace_id, bar_ts_ms=bar_ts_ms,
            )
            self.positions.append(pos)
            self._persist()
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
        orders_fetch_ok = True
        try:
            bn_orders_raw = self.client.exchange.fetch_open_orders()
            bn_order_ids = {str(o.get("id", "")) for o in bn_orders_raw}
            # Also fetch algo orders (server-side TP/SL via /fapi/v1/algo/open-orders).
            # CCXT fetch_open_orders does NOT include algo orders — without this,
            # every reconcile cycle falsely declares TP1 filled because the algo
            # TP1 order is "missing" from the regular orders list. See 2026-05-09
            # LTC/ADA reconcile incident: bot moved SL to break-even on phantom TP1.
            try:
                algo_orders = self.client.exchange.fapiPrivateGetOpenAlgoOrders({})
                bn_order_ids.update(str(a.get("algoId", "")) for a in algo_orders)
            except Exception as e:
                log.warning(f"Reconcile: algo orders fetch failed: {e} — TP1-hit detection may misfire")
        except Exception as e:
            log.warning(f"Reconcile: open orders fetch failed: {e}")
            orders_fetch_ok = False
            # bn_orders_raw stays []; bn_order_ids stays empty set
            # CRITICAL: do NOT use missing-order = filled logic when fetch failed —
            # that's how the 2026-05-08 stacking bug fired (every transient API
            # error tripped TP1-hit on every open position).

        # Binance'deki açık pozisyon symbol'leri.
        # CCXT futures returns 'FIL/USDT:USDT'; bot tracks 'FIL/USDT'. Strip the
        # contract suffix so set membership matches local Position.symbol form.
        bn_open_symbols = {
            _strip_contract_suffix(p["symbol"])
            for p in bn_positions
            if float(p.get("contracts", 0)) > 0
        }

        # Orphan detection: positions on exchange but not tracked locally.
        # These typically arise from one of three scenarios:
        #   1. Manual position opened outside the bot (dashboard, mobile, API).
        #   2. Bot crashed after market entry but before persisting Position.
        #   3. State file corruption / loss / manual edit gone wrong.
        # We DO NOT auto-import: bot has no SL/TP/entry context for the orphan,
        # and may not own the trade decision. Instead emit a structured warning
        # event so an operator (or Hermes-style ops agent) can investigate and
        # either close the orphan manually, run a reconcile script with explicit
        # parameters, or accept it. See 2026-05-09 LTC/ADA orphan incident: bot
        # had only 3 of 5 exchange positions in state; manual `state_aggressive/
        # order_manager_positions.json` injection was needed.
        local_symbols = {p.symbol for p in self.positions}
        orphan_symbols = bn_open_symbols - local_symbols
        detected_orphans: list = []
        if orphan_symbols:
            for orphan in sorted(orphan_symbols):
                # Find the matching exchange position payload to enrich the warning.
                ex_pos = next(
                    (p for p in bn_positions
                     if _strip_contract_suffix(p["symbol"]) == orphan
                     and float(p.get("contracts", 0)) > 0),
                    None,
                )
                if ex_pos:
                    detected_orphans.append(ex_pos)
                    side = ex_pos.get("side", "?")
                    qty = ex_pos.get("contracts", 0)
                    entry_p = ex_pos.get("entryPrice", 0)
                    upnl = ex_pos.get("unrealizedPnl", 0)
                    log.warning(
                        f"⚠️  ORPHAN POSITION DETECTED: {orphan} {side} qty={qty} "
                        f"entry={entry_p} upnl={upnl} — NOT in local state. "
                        f"Bot will NOT manage SL/TP for this position. "
                        f"Manual reconcile required if this was a bot-opened trade."
                    )
                else:
                    log.warning(f"⚠️  ORPHAN POSITION DETECTED: {orphan} — details unavailable")

        if self.orphan_protector is not None and detected_orphans:
            try:
                actions = self.orphan_protector.protect_cycle(detected_orphans, algo_orders if 'algo_orders' in locals() else [])
                for act in actions:
                    log.info(
                        f"orphan_protect[{act.symbol}]: {act.action}"
                        + (f" sl={act.sl_price}" if act.sl_price else "")
                        + (f" error={act.error}" if act.error else "")
                    )
            except Exception as e:
                log.warning(f"orphan_protector failed during reconcile: {e}", exc_info=True)

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
            # Only run when the open-orders fetch succeeded; otherwise an empty
            # bn_order_ids (from a failed fetch) would falsely declare TP1 filled.
            if orders_fetch_ok and pos.tp1_order_id and not pos.tp1_hit:
                if pos.tp1_order_id not in bn_order_ids:
                    # TP1 order'ı kaybolmuş = filled
                    pos.tp1_hit = True
                    log.info(f"RECONCILE: TP1 hit {pos.symbol} → SL → break-even @ {pos.entry}")
                    self._move_sl_to_breakeven(pos)
                    self._emit("tp1_hit", pos)

        # Always persist after a reconcile pass so disk reflects latest exchange-derived
        # state (closes removed from list, tp1_hit flags flipped, sl_order_id updated).
        self._persist()
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

        pos.closed_at = pd.Timestamp.now(tz="UTC").isoformat()
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
        self._persist()

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

    # ─────────────────────────────────────────────────────────────
    # Persistence — opt-in via state_dir
    # ─────────────────────────────────────────────────────────────

    def _persist(self) -> None:
        """Atomically write self.positions to disk (no-op if state_dir not set)."""
        if self._state_file is None:
            return
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._state_file.with_suffix(".json.tmp")
            payload = {"positions": [asdict(p) for p in self.positions]}
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._state_file)
        except Exception as e:
            log.error(f"OrderManager state persist failed: {e}")

    def _restore(self) -> None:
        """Load self.positions from state file. Corrupt files are quarantined."""
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
            raw = payload.get("positions", [])
            restored: List[Position] = []
            for d in raw:
                # Tolerate unknown fields from older formats.
                fields = {f.name for f in Position.__dataclass_fields__.values()}
                clean = {k: v for k, v in d.items() if k in fields}
                restored.append(Position(**clean))
            self.positions = restored
            if restored:
                log.info(
                    f"♻️  OrderManager restored {len(restored)} position(s) from "
                    f"{self._state_file}: "
                    f"{[(p.symbol, p.direction, p.size) for p in restored]}"
                )
        except Exception as e:
            log.error(f"OrderManager restore failed: {e} — quarantining state file")
            try:
                bad = self._state_file.with_suffix(
                    f".corrupt.{int(pd.Timestamp.now().timestamp())}.json"
                )
                self._state_file.rename(bad)
            except Exception:
                pass
            self.positions = []
