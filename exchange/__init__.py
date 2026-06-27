"""Binance exchange client + order manager — CCXT tabanlı."""

import ccxt
import json
import os
import time as _time
import pandas as pd
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict

# TradeJournal imported lazily inside OrderManager to avoid a hard import
# cycle (engine.journal stays optional for unit tests that don't need it).
# A TYPE_CHECKING-only import keeps the type hint readable.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from engine.journal import TradeJournal

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


# Sentinel value set by _retry_tp_order when a TP order cannot be placed because
# the price has already passed the stop price (Binance -2021 'Order would
# immediately trigger'). This is a truthy string so that:
#   1. Sentinel check in downstream logic must be explicit via _is_real_oid().
#   2. Naive `if tp_order_id:` checks still treat it as "set, not empty".
#   3. String persists cleanly through JSON state serialization on Position fields.
_TP_UNREACHABLE_SENTINEL = "UNREACHABLE"


def _timeframe_ms(timeframe: str) -> int:
    """Timeframe string → milliseconds. '1m'→60_000, '4h'→14_400_000, '1d'→…."""
    tf = timeframe.lower().strip()
    unit_ms = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
    return int(tf[:-1]) * unit_ms[tf[-1]]


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
        """Kline data çek → DataFrame (yalnız KAPANMIŞ barlar)."""
        raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        # C1: drop the still-forming (unclosed) last candle. CCXT returns the
        # current in-progress bar as the final row; the SMC engine reads
        # ``.iloc[-1]`` for CHoCH/BOS close crossings, entry price, SL local-low
        # and ATR, so acting on it repaints intra-bar — and that is invisible in
        # backtest, which feeds only closed bars. A bar is still forming when its
        # close time (open + tf) is in the future. Operate on the raw ms
        # timestamps to avoid naive-vs-tz epoch ambiguity. Single exchange choke
        # point → live + CLI both inherit closed-bar-only analysis. Backtest does
        # NOT use this path (it loads cached parquet of already-closed bars).
        if raw and len(raw) >= 2:
            tf_ms = _timeframe_ms(timeframe)
            now_ms = int(_time.time() * 1000)
            if raw[-1][0] + tf_ms > now_ms:
                raw = raw[:-1]
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
        target = mode.upper()  # CROSSED | ISOLATED

        # GET-first (like set_position_mode): skip the POST when the symbol is
        # already in the target margin mode. A redundant POST on a symbol that
        # has open positions/orders returns -4047 "Margin type cannot be changed
        # if there exists open orders" instead of the benign -4046 — which would
        # falsely look like a real failure. Checking first avoids that entirely
        # (and only the genuine flat-book change actually POSTs).
        try:
            risk = self.exchange.fapiPrivateV2GetPositionRisk({"symbol": binance_sym})
            cur = ""
            if isinstance(risk, list) and risk:
                cur = str(risk[0].get("marginType", "")).upper()  # CROSS | ISOLATED
            if cur == "CROSS":
                cur = "CROSSED"
            if cur and cur == target:
                log.debug(f"Margin mode already {target} for {symbol} (GET-first)")
                return True
        except Exception as e:
            log.debug(f"Margin GET-first check failed for {symbol}: {e} — will POST")

        try:
            self.exchange.fapiPrivatePostMarginType({
                "symbol": binance_sym,
                "marginType": target,
            })
            log.info(f"✅ Margin mode set: {symbol} → {mode}")
            return True
        except Exception as e:
            err_str = str(e).lower()
            # -4046 = "No need to change margin type" (zaten istenen modda)
            if "no need" in err_str or "already" in err_str or "-4046" in err_str:
                log.debug(f"Margin mode already {mode} for {symbol}")
                return True
            # -4047 = can't change with open orders. If we reach here the GET-first
            # check did not confirm a match (genuine mismatch on a non-flat book),
            # so this IS a real failure — keep it fatal so a true ISOLATED flip on
            # a non-flat book aborts startup rather than running half-applied.
            log.warning(f"Margin mode set failed for {symbol}: {e}")
            return False

    def set_position_mode(self, dual_side: bool = True) -> bool:
        """Set position mode: dualSidePosition (Hedge Mode) to True, or False for One-way."""
        if self.market_type != "futures":
            return False
        
        # First, query the current position side configuration to avoid POSTing when already set.
        # This prevents Binance from rejecting the request with -4067 (not allowed with open positions/orders)
        # even when the position mode already matches what we want.
        try:
            current_config = self.exchange.fapiPrivateGetPositionSideDual()
            if isinstance(current_config, dict):
                current_dual = current_config.get("dualSidePosition")
                # CCXT response value can be boolean True/False or string "true"/"false"
                is_currently_dual = str(current_dual).lower() == "true"
                if is_currently_dual == dual_side:
                    log.info(f"✅ Position mode is already verified as {'HEDGE' if dual_side else 'ONE_WAY'} via GET")
                    return True
        except Exception as q_err:
            log.warning(f"Failed to query current position mode: {q_err} (will attempt to set anyway)")

        try:
            self.exchange.fapiPrivatePostPositionSideDual({
                "dualSidePosition": "true" if dual_side else "false"
            })
            log.info(f"✅ Position mode set to {'HEDGE' if dual_side else 'ONE_WAY'}")
            return True
        except Exception as e:
            err_str = str(e).lower()
            # -4059 = "No need to change position side" (zaten istenen modda)
            if "no need" in err_str or "already" in err_str or "-4059" in err_str:
                log.debug(f"Position mode already {'HEDGE' if dual_side else 'ONE_WAY'}")
                return True
            log.warning(f"Position mode set failed: {e}")
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

    def fetch_realized_pnl(self, symbol: str, since_ms: int,
                           until_ms: Optional[int] = None) -> dict:
        """Sum REALIZED_PNL / COMMISSION / FUNDING_FEE for a symbol+window.

        Reads the USD-M income endpoint (fapiPrivateGetIncome). Soft-fails:
        any transport/API error returns ok=False with zeroed sums so the
        caller can fall back to its estimate — never raises into reconcile.
        """
        if self.market_type != "futures":
            return {"realized_pnl": 0.0, "commission": 0.0, "funding": 0.0,
                    "net": 0.0, "ok": False}
        try:
            bn_sym = self.exchange.market(self.to_ccxt_symbol(symbol))["id"]
        except Exception:
            bn_sym = symbol.replace("/", "")

        totals = {"REALIZED_PNL": 0.0, "COMMISSION": 0.0, "FUNDING_FEE": 0.0}
        for income_type in totals:
            params = {"symbol": bn_sym, "incomeType": income_type,
                      "startTime": int(since_ms), "limit": 1000}
            if until_ms is not None:
                params["endTime"] = int(until_ms)
            try:
                rows = self.exchange.fapiPrivateGetIncome(params)
            except Exception as e:
                log.warning(f"fetch_realized_pnl({symbol},{income_type}) failed: {e}")
                return {"realized_pnl": 0.0, "commission": 0.0, "funding": 0.0,
                        "net": 0.0, "ok": False}
            for r in (rows or []):
                try:
                    totals[income_type] += float(r.get("income", 0) or 0)
                except (TypeError, ValueError):
                    continue

        net = totals["REALIZED_PNL"] + totals["COMMISSION"] + totals["FUNDING_FEE"]
        return {"realized_pnl": totals["REALIZED_PNL"],
                "commission": totals["COMMISSION"],
                "funding": totals["FUNDING_FEE"],
                "net": net, "ok": True}


@dataclass
class Position:
    symbol: str
    direction: str          # "LONG" | "SHORT"
    entry: float
    sl: float
    tp1: float
    # tp2 = None signals single-target mode (SMC v2, PR #S5.5). v1 always sets
    # a numeric tp2; v2 single-target setups set None so lifecycle.partial_close
    # TP1 branch full-closes and orchestrator cancels orphan SL.
    tp2: Optional[float]
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
    # PR C — exchange-truth PnL reconciliation. Defaults keep _restore() of
    # pre-PR-C order_manager_positions.json backward-compatible.
    realized_pnl_exchange: float = 0.0   # net realizedPnl pulled from Binance income endpoint
    commission_paid: float = 0.0         # summed COMMISSION income for this position's fills
    funding_paid: float = 0.0            # summed FUNDING_FEE income over the position lifetime
    pnl_source: str = "estimated"        # "estimated" until reconciled, then "exchange"
    trace_id: Optional[str] = None       # log correlation across orchestrator → DB
    bar_ts_ms: Optional[int] = None      # bar-aligned timestamp (UTC ms epoch)

    # Per-bar excursion tracking — mirrors engine.lifecycle.Position contract:
    # positive monotonic-max %, never decreasing. Surfaced to TradeJournal at
    # close so Phase 0 evidence can separate H2 (SL too tight) from H3 (price ran far).
    mae_pct: float = 0.0
    mfe_pct: float = 0.0

    # SMC v2 telemetry (PR #S5) — mirrors engine.lifecycle.Position. v1 callers
    # leave these None; v2 entry path (PR #71 _place_v2_entry_order) populates them.
    # Surfaced to DB trades table via bot_runner.position_opened wiring.
    entry_setup_source: Optional[str] = None   # "FVG_PULLBACK" | "OTE_RETRACE" | "V1_LEGACY" | None
    tp1_target_type:    Optional[str] = None   # "LIQUIDITY"    | "FVG_NEAR"    | "RR_PROJECTION" | None
    tp2_target_type:    Optional[str] = None   # "FVG_FAR"      | "FIB_EXT"     | "NONE"          | None
    bars_to_pullback:   Optional[int] = None   # bars elapsed AWAITING_PULLBACK → IN_ZONE

    # Warehouse telemetry (Phase 3.2) — market-state snapshot at entry time.
    # Persisted to DB for post-mortem analysis via bot_runner.position_opened.
    # All default None so existing callers remain unaffected.
    adx_value:          Optional[float] = None  # ADX indicator value at entry
    atr_value:          Optional[float] = None  # ATR indicator value at entry
    funding_rate:       Optional[float] = None  # Funding rate at entry (from exchange)
    confluence_details: Optional[dict]  = None  # Sub-scores, reasons, HTF/MTF biases

    def update_excursion(self, high: float, low: float) -> None:
        """Update mae_pct/mfe_pct from this bar's price extremes.

        Same contract as engine.lifecycle.Position.update_excursion:
        LONG: adverse = bar low below entry; favorable = bar high above entry.
        SHORT: adverse = bar high above entry; favorable = bar low below entry.
        Monotonic max — values only grow. Zero or negative inputs ignored.
        """
        if self.entry <= 0 or high <= 0 or low <= 0:
            return
        if self.direction == "LONG":
            adverse = max(0.0, (self.entry - low) / self.entry * 100.0)
            favorable = max(0.0, (high - self.entry) / self.entry * 100.0)
        else:  # SHORT
            adverse = max(0.0, (high - self.entry) / self.entry * 100.0)
            favorable = max(0.0, (self.entry - low) / self.entry * 100.0)
        if adverse > self.mae_pct:
            self.mae_pct = adverse
        if favorable > self.mfe_pct:
            self.mfe_pct = favorable


class OrderManager:
    """Pozisyon açma + server-side TP/SL + reconciliation.

    v2.2 refactor:
    - TP1/TP2 server-side TAKE_PROFIT_MARKET orders (0ms execution)
    - reconcile() her cycle başı Binance ↔ local sync
    - check_positions() → backup polling fallback (network kopukluğu vs.)
    """

    def __init__(self, client: BinanceClient, dry_run: bool = True,
                 on_position_change=None, state_dir: Optional[str] = None,
                 orphan_protector=None,
                 trade_journal: "Optional[TradeJournal]" = None,
                 hedge_mode: bool = False,
                 max_entry_drift_pct: float = 0.0):
        self.client = client
        self.hedge_mode = hedge_mode
        self.dry_run = dry_run
        # Entry-drift guard: reject a market entry when the LIVE price has run
        # more than this % from the signal entry (or already past TP1), which
        # would leave the position SL-only with a TP that Binance rejects as
        # -2021 'would immediately trigger'. 0.0 = disabled (backward-compat).
        # See test_entry_drift_guard.py for the 2026-05-31 live incident.
        self.max_entry_drift_pct = max_entry_drift_pct
        # PR C — periodic PnL audit sweep (overridden by bot_runner wiring).
        self.enable_pnl_audit = True
        self.pnl_audit_every_cycles = 20
        self._pnl_audit_cycle = 0
        # PR B — post-placement protection verification. Default OFF in code
        # (like max_entry_drift_pct); bot_runner enables it from config (default
        # true) so unit tests that don't wire config keep the old behavior and
        # take no 2.5s verify sleeps.
        self.enable_post_placement_verify = False
        self.verify_delay_sec = 2.5
        self.verify_max_attempts = 3
        self.rollback_on_sl_failure = True
        self.positions: List[Position] = []
        self.closed_positions: List[Position] = []  # son kapanan pozisyon history (DB'ye yazılır)
        # M4: per-sweep (trade_id, old_pnl, new_pnl) tuples produced by
        # audit_realized_pnl; drained by SafeOrchestrator STEP5 to back-correct
        # the breaker's consecutive-loss counter (default-OFF).
        self._last_pnl_corrections: list = []
        self.on_position_change = on_position_change  # callback (event_type, position) — WS push için
        self.orphan_protector = orphan_protector
        # Trade journal — writes a full TradeSnapshot (entry+exit atomically)
        # per closed trade in _record_close. None = no-op (backwards-compat for
        # backtest / unit-test paths). See PR fix/production-trade-journal +
        # feat/journal-order-manager-hook stack: this hook captures the bulk
        # of real production closes (TP1/TP2/SL/RECONCILED) that go through
        # OrderManager.reconcile() rather than SafeOrchestrator.
        self.trade_journal = trade_journal

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
    # TP/SL Retry & Repair Helpers
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """Return True if the exchange error is likely transient and retryable.

        Retryable: network timeout, rate limit, server overload, disconnected.
        Non-retryable: insufficient balance, invalid symbol, bad params, etc.
        """
        err = str(exc).lower()
        transient_markers = (
            "timeout", "timed out", "rate limit", "ratelimit",
            "-1001", "disconnected", "-1003", "too many",
            "-1015", "too many orders", "service unavailable",
            "503", "502", "504", "internal error", "network",
            "econnreset", "econnrefused", "epipe",
        )
        return any(m in err for m in transient_markers)

    @staticmethod
    def _is_unreachable_error(exc: Exception) -> bool:
        """Return True if the TP order is unreachable due to price already passed.

        Binance -2021 'Order would immediately trigger' means stop price is
        already past current market price. Repairing such TP is pointless —
        position is in profit zone. Sentinel handling prevents infinite retry
        loops (see PR #102a — LINK/USDT SHORT incident 2026-05-28 14:41 UTC).

        Markers:
          - binance code -2021
          - 'would immediately trigger' text (non-code variant)
        """
        err = str(exc).lower()
        unreachable_markers = (
            "-2021",
            "would immediately trigger",
        )
        return any(m in err for m in unreachable_markers)

    @staticmethod
    def _entry_drift_rejection(direction: str, live_price: float, entry: float,
                              tp1: float, max_drift_pct: float) -> Optional[str]:
        """Return a rejection reason if the live price has drifted too far from
        the signal entry to safely open, else None (allow).

        Two independent conditions, either of which rejects:
          1. |live - entry| / entry exceeds max_drift_pct — the market ran away
             from the signal; entering now chases a degraded reward.
          2. The live price has already reached/passed TP1 in the profit
             direction (LONG: live >= tp1, SHORT: live <= tp1) — the take-profit
             is unplaceable (Binance -2021) and the position would be SL-only.

        Fail-open: a non-positive entry/live or max_drift_pct <= 0 (disabled)
        returns None. NOTE (H4): the OrderManager.open_position CALL SITE owns
        price-fetch-failure semantics and fails CLOSED (rejects the entry) on a
        fetch exception or non-positive live price; this pure helper keeps its
        fail-open contract for callers that pass an already-validated price.
        """
        if max_drift_pct <= 0 or entry <= 0 or live_price <= 0:
            return None
        drift_pct = abs(live_price - entry) / entry * 100.0
        if drift_pct > max_drift_pct:
            return (f"entry drift {drift_pct:.2f}% > max {max_drift_pct:.2f}% "
                    f"(signal={entry:.6g}, live={live_price:.6g})")
        if tp1 and tp1 > 0:
            past_tp1 = ((direction == "LONG" and live_price >= tp1)
                        or (direction == "SHORT" and live_price <= tp1))
            if past_tp1:
                return (f"live {live_price:.6g} already past TP1 {tp1:.6g} "
                        f"({direction}) — TP unplaceable")
        return None

    @staticmethod
    def _is_real_oid(oid) -> bool:
        """Return True iff `oid` is a real Binance order id (not empty, not sentinel).

        Guards call-sites that interpret a truthy `position.order_id / .tp1_order_id
        / .sl_order_id` as a pending live order on Binance. Sentinel value
        `_TP_UNREACHABLE_SENTINEL` is truthy but represents "we tried, failed
        permanently, do not retry and do not interpret as live order".

        Use cases where this check is mandatory:
          - reconcile's TP1 fill detection (prevents false "TP1 hit" when
            sentinel set)
          - _estimate_exit_price's phantom TP2 hit detection
          - _cancel_position_siblings to avoid wasteful cancel_order() calls
            on a sentinel id
        """
        return bool(oid) and oid != _TP_UNREACHABLE_SENTINEL

    def _cancel_algo_order(self, algo_id: str) -> str:
        """Cancel a single server-side algo order (SL/TP) by its algoId.

        The bot places SL/TP via create_order(STOP_MARKET/TAKE_PROFIT_MARKET),
        which Binance routes to the conditional/algo system; create_order returns
        the *algoId* as `id`, so `pos.sl_order_id`/`tp1_order_id`/`tp2_order_id`
        ARE algoIds. The regular cancel_order(orderId) endpoint returns Binance
        -2011 'Unknown order sent' for an algoId — so algo orders MUST be
        cancelled via DELETE /fapi/v1/algo/futures/order (algoId). This is the
        root-cause fix for orphan SL/TP that survived position closes and for
        break-even moves that left a duplicate (un-cancelled) SL.

        Returns 'cancelled' | 'missing' | 'failed'.
        """
        try:
            self.client.exchange.fapiPrivateDeleteAlgoOrder({"algoId": algo_id})
            return "cancelled"
        except ccxt.OrderNotFound:
            return "missing"
        except Exception as e:  # noqa: BLE001 — best-effort cleanup, never propagate
            log.warning(f"[cleanup] algo-cancel failed for algoId={algo_id}: {e}")
            return "failed"

    def _cancel_order_any(self, oid: str, ccxt_sym: str) -> str:
        """Cancel an order by id, transparently handling BOTH regular orders
        and server-side algo orders (the SL/TP legs the bot places).

        Tries the regular cancel_order first; on OrderNotFound — which Binance
        also returns as -2011 'Unknown order sent' when an algoId is sent to the
        regular cancel endpoint — falls back to the algo-cancel endpoint.

        Returns 'cancelled' | 'missing' | 'failed'.
        """
        try:
            self.client.exchange.cancel_order(oid, ccxt_sym)
            return "cancelled"
        except ccxt.OrderNotFound:
            # Either genuinely gone, OR an algo order that hit the wrong endpoint
            # (-2011). Disambiguate by trying the algo-cancel endpoint.
            return self._cancel_algo_order(oid)
        except Exception:  # noqa: BLE001 — caller logs with label context
            return "failed"

    def _retry_tp_order(
        self,
        *,
        ccxt_sym: str,
        order_type: str,
        side: str,
        amount: float,
        params: dict,
        label: str,
        symbol: str,
        direction: str,
        entry_order_id: str,
        sl_order_id: str,
        price_display: float,
        tp1_order_id: str = "",
        max_attempts: int = 3,
        base_delay: float = 1.0,
    ) -> str:
        """Place a TP (or SL repair) order with retry on transient errors.

        Returns:
          - order_id (truthy string) on success
          - "" on exhausted retries (non-unreachable non-transient errors)
          - "UNREACHABLE" sentinel when Binance -2021 'would immediately
            trigger' — price already past TP target. Sentinel stops infinite
            repair loops (PR #102a).

        TP orders are reduceOnly — idempotent and safe to retry. If a previous
        attempt actually went through but we didn't see the response (timeout),
        placing a duplicate reduceOnly is harmless: Binance will either accept
        it (creating a second order that both reduce) or reject it if the
        position is already fully covered.

        Non-transient errors (insufficient balance, bad symbol) fail immediately
        without retry to avoid wasting attempts.
        """
        # Round stopPrice inside params using the exchange's price precision as a safety net
        if not self.dry_run and "stopPrice" in params:
            try:
                raw_price = params["stopPrice"]
                res = self.client.exchange.price_to_precision(ccxt_sym, raw_price)
                if isinstance(res, str):
                    params["stopPrice"] = float(res)
                    price_display = float(res)
            except Exception as e:
                log.warning(f"Failed to format stopPrice using exchange precision for {symbol} in _retry_tp_order: {e}")

        stop_price = params.get("stopPrice", price_display)
        for attempt in range(1, max_attempts + 1):
            try:
                order = self.client.exchange.create_order(
                    ccxt_sym, order_type, side, amount, params=params,
                )
                oid = order.get("id", "") if isinstance(order, dict) else ""
                log.info(
                    f"  ↳ {label} @ {price_display:.4f} (size={amount:.4f}) | "
                    f"order_id={oid}"
                    + (f" (attempt {attempt})" if attempt > 1 else "")
                )
                return oid
            except Exception as e:
                # Unreachable errors (price already past TP target) are a
                # special category — return sentinel immediately, no retry.
                if self._is_unreachable_error(e):
                    log.critical(
                        "order_manager.tp_unreachable: %s %s tp_leg=%s "
                        "entry_order_id=%s sl_order_id=%s error=%s — "
                        "position likely in profit zone, repair skipping",
                        symbol, direction, label,
                        entry_order_id, sl_order_id,
                        e,
                        extra={
                            "event": "order_manager.tp_unreachable",
                            "symbol": symbol,
                            "direction": direction,
                            "tp_leg": label,
                            "entry_order_id": entry_order_id,
                            "sl_order_id": sl_order_id,
                            "error": str(e),
                        },
                    )
                    return _TP_UNREACHABLE_SENTINEL
                is_transient = self._is_transient_error(e)
                if not is_transient or attempt == max_attempts:
                    log.warning(
                        "order_manager.tp_placement_failed_after_sl: %s %s "
                        "tp_leg=%s entry_order_id=%s sl_order_id=%s "
                        "tp1_order_id=%s error=%s attempts=%d/%d",
                        symbol, direction, label,
                        entry_order_id, sl_order_id, tp1_order_id,
                        e, attempt, max_attempts,
                        exc_info=True,
                        extra={
                            "event": "order_manager.tp_placement_failed_after_sl",
                            "symbol": symbol,
                            "direction": direction,
                            "tp_leg": label,
                            "entry_order_id": entry_order_id,
                            "sl_order_id": sl_order_id,
                            "tp1_order_id": tp1_order_id,
                            "error": str(e),
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "retryable": is_transient,
                        },
                    )
                    return ""
                # Transient error, more attempts left — backoff and retry.
                delay = base_delay * (2 ** (attempt - 1))
                log.info(
                    f"  ↳ {label} attempt {attempt}/{max_attempts} failed "
                    f"(transient): {e} — retrying in {delay:.1f}s"
                )
                _time.sleep(delay)
        return ""  # unreachable but defensive

    def _repair_missing_protection_orders(
        self, bn_order_ids: set, algo_fetch_ok: bool = True
    ) -> None:
        """Re-send TP1/TP2 orders for positions that have empty order IDs.

        ``algo_fetch_ok`` reports whether this cycle's algo-order fetch
        succeeded. When it failed, ``bn_order_ids`` holds NO algoIds, so every
        live SL/TP (which ARE algoIds) would falsely look 'absent' — the
        set-but-absent SL repair is suppressed to avoid re-placing a still-live
        SL (duplicate-SL churn on a transient API hiccup).

        Called from reconcile() after the TP1-hit detection pass. This is the
        safety net that catches:
        - Historical positions opened before the TP retry fix
        - Positions where all 3 retry attempts were exhausted
        - Positions created during a crash/restart window

        Only attempts repair when:
        1. Position is open (still in self.positions)
        2. The position hasn't been TP1-hit (for TP1 repair)
        3. The order ID is empty (never successfully placed)
        4. tp2 is not None (for TP2 repair; single-target has no TP2)
        """
        for pos in self.positions:
            ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
            reverse_side = "sell" if pos.direction == "LONG" else "buy"
            is_single_target = pos.tp2 is None
            tp1_size = pos.size if is_single_target else pos.size / 2
            tp2_size = 0.0 if is_single_target else pos.size - tp1_size

            # Round sizes using the exchange's amount precision to avoid stepSize/lotSize errors on Binance
            if not self.dry_run:
                try:
                    res1 = self.client.exchange.amount_to_precision(ccxt_sym, tp1_size)
                    if isinstance(res1, str):
                        tp1_size = float(res1)
                    if not is_single_target:
                        res2 = self.client.exchange.amount_to_precision(ccxt_sym, tp2_size)
                        if isinstance(res2, str):
                            tp2_size = float(res2)
                except Exception as e:
                    log.warning(f"Failed to format TP sizes using exchange precision for {pos.symbol}: {e}")

            # ── Repair SL if missing (highest priority — unprotected position) ──
            # "Missing" = never placed (empty id) OR placed-then-vanished: the
            # tracked algoId is no longer in the live order set (bn_order_ids,
            # which includes algoIds). The latter catches an SL that was
            # cancelled/lost while the position stayed open (exchange-side
            # cancel, failed BE-move, a stray cancel-all). Closes are processed
            # BEFORE repair, so a still-open position whose SL is absent
            # genuinely lost it (an SL fill would have closed the position).
            # UNREACHABLE sentinel is excluded via _is_real_oid (do not churn).
            # Gated on algo_fetch_ok: if the algo fetch failed this cycle,
            # bn_order_ids has no algoIds and every live SL would look absent.
            sl_absent_on_exchange = (
                algo_fetch_ok
                and self._is_real_oid(pos.sl_order_id)
                and pos.sl_order_id not in bn_order_ids
            )
            if not pos.sl_order_id or sl_absent_on_exchange:
                if sl_absent_on_exchange:
                    # Stale id: clear it so _retry_tp_order treats this as a
                    # fresh placement and overwrites with the new algoId below.
                    pos.sl_order_id = ""
                log.critical(
                    "order_manager.repair_missing_sl: %s %s "
                    "— re-sending protection order",
                    pos.symbol, pos.direction,
                    extra={
                        "event": "order_manager.repair_missing_sl",
                        "symbol": pos.symbol,
                        "direction": pos.direction,
                    },
                )
                # SL repair TAM boyutu korur (emir tamamen kayıp dalı — yarı
                # boyut çıplak pozisyon riski yaratır). Sadece TP1/TP2 ile
                # simetrik precision rounding uygula (stepSize hatası önlenir).
                sl_amount = pos.size
                if not self.dry_run:
                    try:
                        res_sl = self.client.exchange.amount_to_precision(ccxt_sym, sl_amount)
                        if isinstance(res_sl, str):
                            sl_amount = float(res_sl)
                    except Exception as e:
                        log.warning(
                            f"Failed to format SL size using exchange precision "
                            f"for {pos.symbol}: {e}"
                        )
                sl_repair_params = {"stopPrice": pos.sl}
                if self.hedge_mode:
                    sl_repair_params["positionSide"] = pos.direction
                else:
                    sl_repair_params["reduceOnly"] = True
                new_sl_oid = self._retry_tp_order(
                    ccxt_sym=ccxt_sym,
                    order_type="STOP_MARKET",
                    side=reverse_side,
                    amount=sl_amount,
                    params=sl_repair_params,
                    label="SL_REPAIR",
                    symbol=pos.symbol,
                    direction=pos.direction,
                    entry_order_id=pos.order_id,
                    sl_order_id="",
                    price_display=pos.sl,
                    tp1_order_id=pos.tp1_order_id or "",
                )
                if new_sl_oid:
                    pos.sl_order_id = new_sl_oid

            # Repair TP1 if missing and not yet hit
            if not pos.tp1_order_id and not pos.tp1_hit:
                log.critical(
                    "order_manager.repair_missing_tp: %s %s tp_leg=TP1 "
                    "— re-sending protection order",
                    pos.symbol, pos.direction,
                    extra={
                        "event": "order_manager.repair_missing_tp",
                        "symbol": pos.symbol,
                        "direction": pos.direction,
                        "tp_leg": "TP1",
                    },
                )
                tp1_params = {"stopPrice": pos.tp1}
                if self.hedge_mode:
                    tp1_params["positionSide"] = pos.direction
                else:
                    tp1_params["reduceOnly"] = True
                new_tp1_oid = self._retry_tp_order(
                    ccxt_sym=ccxt_sym,
                    order_type="TAKE_PROFIT_MARKET",
                    side=reverse_side,
                    amount=tp1_size,
                    params=tp1_params,
                    label="TP1_REPAIR",
                    symbol=pos.symbol,
                    direction=pos.direction,
                    entry_order_id=pos.order_id,
                    sl_order_id=pos.sl_order_id,
                    price_display=pos.tp1,
                )
                if new_tp1_oid:
                    pos.tp1_order_id = new_tp1_oid

            # Repair TP2 if missing (only for dual-target)
            if not is_single_target and not pos.tp2_order_id and not pos.tp1_hit:
                log.critical(
                    "order_manager.repair_missing_tp: %s %s tp_leg=TP2 "
                    "— re-sending protection order",
                    pos.symbol, pos.direction,
                    extra={
                        "event": "order_manager.repair_missing_tp",
                        "symbol": pos.symbol,
                        "direction": pos.direction,
                        "tp_leg": "TP2",
                    },
                )
                tp2_params = {"stopPrice": pos.tp2}
                if self.hedge_mode:
                    tp2_params["positionSide"] = pos.direction
                else:
                    tp2_params["reduceOnly"] = True
                new_tp2_oid = self._retry_tp_order(
                    ccxt_sym=ccxt_sym,
                    order_type="TAKE_PROFIT_MARKET",
                    side=reverse_side,
                    amount=tp2_size,
                    params=tp2_params,
                    label="TP2_REPAIR",
                    symbol=pos.symbol,
                    direction=pos.direction,
                    entry_order_id=pos.order_id,
                    sl_order_id=pos.sl_order_id,
                    price_display=pos.tp2,
                    tp1_order_id=pos.tp1_order_id,
                )
                if new_tp2_oid:
                    pos.tp2_order_id = new_tp2_oid

    # ─────────────────────────────────────────────────────────────
    # Open / Close
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_filled_amount(entry_order: dict, fallback_size: float) -> float:
        """Return actual filled amount from an exchange order response.

        Binance/CCXT responses are not perfectly stable across endpoints and
        versions. Prefer fill fields when present; fall back to requested size
        so rollback still attempts to close the whole intended entry.
        """
        for key in ("filled", "executedQty", "amount", "origQty"):
            raw = entry_order.get(key) if isinstance(entry_order, dict) else None
            if raw in (None, ""):
                continue
            try:
                amount = float(raw)
            except (TypeError, ValueError):
                continue
            if amount > 0:
                return amount
        return fallback_size

    def _rollback_entry_after_protection_failure(
        self,
        ccxt_sym: str,
        rollback_side: str,
        rollback_size: float,
        symbol: str,
        direction: str,
        entry_order_id: str,
        original_error: Exception,
    ) -> bool:
        """Best-effort reduceOnly market close after SL placement failure.

        This is the critical orphan-prevention safety net: if the market entry
        filled but the protective SL could not be placed, immediately try to
        flatten the just-opened exchange position instead of leaving it live and
        untracked.
        """
        try:
            rollback_params = {}
            if self.hedge_mode:
                rollback_params["positionSide"] = direction
            else:
                rollback_params["reduceOnly"] = True
            rollback_order = self.client.exchange.create_order(
                ccxt_sym,
                "market",
                rollback_side,
                rollback_size,
                params=rollback_params,
            )
            log.critical(
                "order_manager.entry_rollback_after_sl_failure: %s %s entry_order_id=%s "
                "rollback_order_id=%s rollback_size=%s original_error=%s",
                symbol,
                direction,
                entry_order_id,
                rollback_order.get("id", "") if isinstance(rollback_order, dict) else "",
                rollback_size,
                original_error,
                extra={
                    "event": "order_manager.entry_rollback_after_sl_failure",
                    "symbol": symbol,
                    "direction": direction,
                    "entry_order_id": entry_order_id,
                    "rollback_size": rollback_size,
                    "rollback_order_id": rollback_order.get("id", "") if isinstance(rollback_order, dict) else "",
                    "original_error": str(original_error),
                },
            )
            return True
        except Exception as rollback_error:
            log.critical(
                "order_manager.entry_rollback_failed: %s %s entry_order_id=%s "
                "rollback_size=%s original_error=%s rollback_error=%s",
                symbol,
                direction,
                entry_order_id,
                rollback_size,
                original_error,
                rollback_error,
                exc_info=True,
                extra={
                    "event": "order_manager.entry_rollback_failed",
                    "symbol": symbol,
                    "direction": direction,
                    "entry_order_id": entry_order_id,
                    "rollback_size": rollback_size,
                    "original_error": str(original_error),
                    "rollback_error": str(rollback_error),
                },
            )
            return False

    def open_position(self, symbol: str, direction: str, size: float,
                      entry: float, sl: float, tp1: float,
                      tp2: Optional[float],
                      trace_id: Optional[str] = None,
                      bar_ts_ms: Optional[int] = None,
                      *,
                      entry_setup_source: Optional[str] = None,
                      tp1_target_type: Optional[str] = None,
                      tp2_target_type: Optional[str] = None,
                      bars_to_pullback: Optional[int] = None,
                      adx_value: Optional[float] = None,
                      atr_value: Optional[float] = None,
                      funding_rate: Optional[float] = None,
                      confluence_details: Optional[dict] = None) -> Optional[Position]:
        """Yeni pozisyon aç + server-side SL + TP1 (yarı) + TP2 (yarı) yerleştir.

        trace_id / bar_ts_ms: optional log-correlation + bar-alignment metadata
        forwarded into the Position dataclass; bot_runner persists them through
        the cross-thread DB callback. Both default to None for backwards compat
        (orchestrator paths that don't yet thread them through).

        SMC v2 telemetry kwargs (PR #S5, keyword-only): forwarded into the
        Position dataclass and persisted by bot_runner; default None preserves
        v1 callers.
        """
        side = "buy" if direction == "LONG" else "sell"
        reverse_side = "sell" if direction == "LONG" else "buy"
        # Single-target mode (tp2=None) gives TP1 the full size; no split.
        is_single_target = tp2 is None
        tp1_size = size if is_single_target else size / 2
        tp2_size = 0.0 if is_single_target else size - tp1_size

        if self.dry_run:
            tp2_str = "NONE(single-target)" if tp2 is None else f"{tp2:.2f}"
            log.info(f"[DRY] {direction} {symbol} size={size:.4f} @ {entry:.2f} | "
                     f"SL={sl:.2f} TP1={tp1:.2f} TP2={tp2_str}")
            pos = Position(symbol, direction, entry, sl, tp1, tp2, size,
                           opened_at=pd.Timestamp.now(tz="UTC").isoformat(),
                           trace_id=trace_id, bar_ts_ms=bar_ts_ms,
                           entry_setup_source=entry_setup_source,
                           tp1_target_type=tp1_target_type,
                           tp2_target_type=tp2_target_type,
                           bars_to_pullback=bars_to_pullback,
                           adx_value=adx_value,
                           atr_value=atr_value,
                           funding_rate=funding_rate,
                           confluence_details=confluence_details)
            self.positions.append(pos)
            self._persist()
            self._emit("position_opened", pos)
            return pos

        # Entry-drift guard — reject if the live price has run too far from the
        # signal before we market-enter (would otherwise open SL-only with a TP
        # Binance rejects as -2021). FAIL-CLOSED (H4): the same Binance flakiness
        # that causes drift also breaks the price fetch, so a missing/zero/NaN
        # price must BLOCK the entry rather than open blind. It retries next cycle
        # once price is readable. (Only active when max_entry_drift_pct > 0.)
        if self.max_entry_drift_pct > 0:
            try:
                live_price = float(self.client.get_price(symbol))
            except Exception as e:
                log.warning(f"🚫 [{symbol}] Entry rejected — drift-guard price fetch failed: {e} (fail-closed; retries next cycle)")
                return None
            if not (live_price > 0):
                log.warning(f"🚫 [{symbol}] Entry rejected — drift-guard live price unavailable ({live_price}); fail-closed")
                return None
            reject_reason = self._entry_drift_rejection(
                direction, live_price, entry, tp1, self.max_entry_drift_pct,
            )
            if reject_reason:
                log.warning(f"🚫 [{symbol}] Entry rejected — {reject_reason}")
                return None

        # CCXT'nin futures route'una gitmesi için symbol'i collateral notation ile sar
        ccxt_sym = self.client.to_ccxt_symbol(symbol)

        # Round sizes and prices using the exchange's precision to avoid filter/lotSize/PRICE_FILTER errors on Binance
        if not self.dry_run:
            try:
                # 1) Round prices
                entry = float(self.client.exchange.price_to_precision(ccxt_sym, entry))
                sl = float(self.client.exchange.price_to_precision(ccxt_sym, sl))
                tp1 = float(self.client.exchange.price_to_precision(ccxt_sym, tp1))
                if tp2 is not None:
                    tp2 = float(self.client.exchange.price_to_precision(ccxt_sym, tp2))
            except Exception as e:
                log.warning(f"Failed to format entry/SL/TP prices using exchange precision for {symbol}: {e}")

            try:
                # 2) Round sizes
                res1 = self.client.exchange.amount_to_precision(ccxt_sym, tp1_size)
                if isinstance(res1, str):
                    tp1_size = float(res1)
                if not is_single_target:
                    res2 = self.client.exchange.amount_to_precision(ccxt_sym, tp2_size)
                    if isinstance(res2, str):
                        tp2_size = float(res2)
            except Exception as e:
                log.warning(f"Failed to format TP sizes using exchange precision for {symbol}: {e}")

        # Build parameters for CCXT orders
        params = {}
        if self.hedge_mode:
            params["positionSide"] = direction  # "LONG" or "SHORT"

        # 1) Market entry order. If this fails, nothing was opened and no
        # rollback is required.
        try:
            entry_order = self.client.exchange.create_order(
                ccxt_sym, "market", side, size, params=params
            )
        except Exception as e:
            log.error(f"Order failed for {symbol}: {e}", exc_info=True)
            return None

        oid = entry_order.get("id", "") if isinstance(entry_order, dict) else ""
        rollback_size = self._extract_filled_amount(entry_order, size)

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

        # 2) Server-side SL — STOP_MARKET reduceOnly. Retry on transient errors
        # (same as TP). If exhausted, rollback the entry (flatten exchange position).
        sl_params = {"stopPrice": sl}
        if self.hedge_mode:
            sl_params["positionSide"] = direction
        else:
            sl_params["reduceOnly"] = True

        sl_oid = self._retry_tp_order(
            ccxt_sym=ccxt_sym,
            order_type="STOP_MARKET",
            side=reverse_side,
            amount=size,
            params=sl_params,
            label="SL",
            symbol=symbol,
            direction=direction,
            entry_order_id=oid,
            sl_order_id="",
            price_display=sl,
        )

        if not self._is_real_oid(sl_oid):
            # SL exhausted or unreachable (price already past SL level —
            # Binance -2021 'would immediately trigger') — both require
            # immediate rollback because the position is already at loss.
            self._rollback_entry_after_protection_failure(
                ccxt_sym=ccxt_sym,
                rollback_side=reverse_side,
                rollback_size=rollback_size,
                symbol=symbol,
                direction=direction,
                entry_order_id=oid,
                original_error=Exception(
                    f"SL placement {'unreachable (-2021)' if sl_oid == _TP_UNREACHABLE_SENTINEL else 'exhausted after retries'}"
                ),
            )
            return None

        log.info(f"  ↳ SL @ {sl:.4f} | order_id={sl_oid}")

        tp1_oid = ""
        tp2_oid = ""

        # 3) Server-side TP1 — TAKE_PROFIT_MARKET, half (or full for single-target),
        # reduceOnly. If TP placement fails after SL succeeds, keep local tracking
        # rather than orphaning a protected exchange position.
        # FIX: TP1 failure must NOT early-return — TP2 must still be attempted.
        # FIX: Retry with backoff for transient API errors (reduceOnly = idempotent).
        tp1_params = {"stopPrice": tp1}
        if self.hedge_mode:
            tp1_params["positionSide"] = direction
        else:
            tp1_params["reduceOnly"] = True
        tp1_oid = self._retry_tp_order(
            ccxt_sym=ccxt_sym,
            order_type="TAKE_PROFIT_MARKET",
            side=reverse_side,
            amount=tp1_size,
            params=tp1_params,
            label="TP1",
            symbol=symbol,
            direction=direction,
            entry_order_id=oid,
            sl_order_id=sl_oid,
            price_display=tp1,
        )

        # 4) Server-side TP2 — kalan yarı. Same policy as TP1: SL-protected
        # positions must remain tracked even when optional TP placement fails.
        # Single-target mode (tp2=None): skip TP2 placement entirely.
        # tp2_oid stays "" so reconcile / cleanup helper find no order to cancel.
        # FIX: TP2 is always attempted even when TP1 failed (early-return removed).
        if tp2 is None:
            log.info("  ↳ TP2 skipped (single-target setup)")
        else:
            tp2_params = {"stopPrice": tp2}
            if self.hedge_mode:
                tp2_params["positionSide"] = direction
            else:
                tp2_params["reduceOnly"] = True
            tp2_oid = self._retry_tp_order(
                ccxt_sym=ccxt_sym,
                order_type="TAKE_PROFIT_MARKET",
                side=reverse_side,
                amount=tp2_size,
                params=tp2_params,
                label="TP2",
                symbol=symbol,
                direction=direction,
                entry_order_id=oid,
                sl_order_id=sl_oid,
                price_display=tp2,
                tp1_order_id=tp1_oid,
            )

        pos = Position(
            symbol=symbol, direction=direction, entry=actual_entry,
            sl=sl, tp1=tp1, tp2=tp2, size=size,
            order_id=oid, sl_order_id=sl_oid,
            tp1_order_id=tp1_oid, tp2_order_id=tp2_oid,
            opened_at=pd.Timestamp.now(tz="UTC").isoformat(),
            trace_id=trace_id, bar_ts_ms=bar_ts_ms,
            entry_setup_source=entry_setup_source,
            tp1_target_type=tp1_target_type,
            tp2_target_type=tp2_target_type,
            bars_to_pullback=bars_to_pullback,
            adx_value=adx_value,
            atr_value=atr_value,
            funding_rate=funding_rate,
            confluence_details=confluence_details,
        )
        self.positions.append(pos)
        # PR B — confirm SL/TP actually landed on the exchange within seconds.
        # May market-close + remove pos from self.positions if SL can't be
        # confirmed (returns rolled_back); return None so callers treat the
        # entry as not-opened (same contract as the entry-drift reject).
        # C3: persist AFTER verify, not before. Persisting before verify meant a
        # crash in the verify window (~verify_delay×attempts) left the on-disk
        # state claiming a possibly-bare position is open+protected. Now only a
        # verified-protected position is written; the rollback path persists its
        # own flattened state inside _verify_and_repair_protection's finally.
        verify_result = self._verify_and_repair_protection(pos)
        if verify_result.get("rolled_back"):
            self._emit("position_rolled_back", pos)
            return None
        self._persist()
        self._emit("position_opened", pos)
        return pos

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
        algo_fetch_ok = True
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
                algo_fetch_ok = False
                log.warning(f"Reconcile: algo orders fetch failed: {e} — TP1-hit detection may misfire")
        except Exception as e:
            log.warning(f"Reconcile: open orders fetch failed: {e}")
            orders_fetch_ok = False
            # bn_orders_raw stays []; bn_order_ids stays empty set
            # CRITICAL: do NOT use missing-order = filled logic when fetch failed —
            # that's how the 2026-05-08 stacking bug fired (every transient API
            # error tripped TP1-hit on every open position).

        # Binance'deki açık pozisyon symbol'leri ve yönleri (Hedge Mode uyumlu).
        # CCXT futures returns 'FIL/USDT:USDT'; bot tracks 'FIL/USDT'. Strip the
        # contract suffix so set membership matches local Position.symbol form.
        bn_open_symbols = {
            _strip_contract_suffix(p["symbol"])
            for p in bn_positions
            if float(p.get("contracts", 0)) > 0
        }
        bn_open_positions = {
            (_strip_contract_suffix(p["symbol"]), str(p.get("side", "")).upper())
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

        if (self.orphan_protector is not None and detected_orphans
                and orders_fetch_ok and algo_fetch_ok):
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
        elif self.orphan_protector is not None and detected_orphans:
            # The regular or algo open-orders fetch failed this cycle, so the live
            # id set is incomplete and SL coverage is UNKNOWABLE. Skip orphan
            # protection rather than infer 'missing SL' from an empty set — that
            # would place a DUPLICATE close-position SL on a position that may
            # already have an algo-SL which merely failed to fetch. Mirrors the
            # _repair_missing_protection_orders algo_fetch_ok guard. The orphan is
            # still warned above for the operator.
            log.warning(
                f"orphan_protect skipped for {len(detected_orphans)} orphan(s): "
                f"order/algo fetch failed (orders_ok={orders_fetch_ok}, "
                f"algo_ok={algo_fetch_ok}) — cannot assess SL coverage this cycle"
            )

        closed_now: List[Position] = []

        for pos in self.positions[:]:
            # Normalization fallback for legacy/mock tests that don't pass 'side' parameter:
            if self.hedge_mode:
                is_open = (pos.symbol, pos.direction) in bn_open_positions or (pos.symbol, "") in bn_open_positions
            else:
                is_open = pos.symbol in bn_open_symbols

            if not is_open:
                # Pozisyon Binance'de kapanmış — TP2 / SL / manual close
                # Ordering note: _estimate_exit_price runs before
                # _cancel_position_siblings as defense-in-depth. Currently safe
                # either way because it reads `bn_order_ids` captured once at the
                # top of reconcile(), so cancellations don't mutate that local
                # set. But if _estimate_exit_price is ever changed to live-fetch
                # open orders, cancelling first would invalidate trigger
                # attribution (TP1/TP2/SL is inferred from which id is missing).
                # Keep this order.
                # Pass the ALGO-INCLUSIVE id set (bn_order_ids), not the
                # regular-only bn_orders_raw: SL/TP are algo orders, so a
                # regular-only set makes every leg look 'missing' → phantom TP2.
                # fetch_ok gates attribution off when either fetch failed.
                exit_price = self._estimate_exit_price(
                    pos, bn_order_ids, fetch_ok=(orders_fetch_ok and algo_fetch_ok)
                )
                # Cancel orphan sibling reduceOnly orders before dropping local state
                if not self.dry_run:
                    ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
                    self._cancel_position_siblings(pos, ccxt_sym, reason="RECONCILED")
                self._record_close(pos, exit_price, reason="RECONCILED")
                closed_now.append(pos)
                self.positions.remove(pos)
                continue

            # Pozisyon hâlâ açık — TP1 fill kontrolü
            # Only run when the open-orders fetch succeeded; otherwise an empty
            # bn_order_ids (from a failed fetch) would falsely declare TP1 filled.
            if orders_fetch_ok and self._is_real_oid(pos.tp1_order_id) and not pos.tp1_hit:
                if pos.tp1_order_id not in bn_order_ids:
                    # TP1 order'ı kaybolmuş = filled
                    pos.tp1_hit = True
                    log.info(f"RECONCILE: TP1 hit {pos.symbol} → SL → break-even @ {pos.entry}")
                    self._move_sl_to_breakeven(pos)
                    # The BE move placed a NEW SL this cycle; its algoId is not in
                    # the cycle-start bn_order_ids snapshot. Register it so the
                    # set-but-absent repair below does not double-place it.
                    if self._is_real_oid(pos.sl_order_id):
                        bn_order_ids.add(pos.sl_order_id)
                    self._emit("tp1_hit", pos)

        # 🔧 Repair missing protection orders:
        # If a position was opened but TP1/TP2 placement failed (transient API
        # error, early-return bug pre-fix, crash between entry and TP placement),
        # re-send the missing orders now. This is the safety net that ensures
        # every open position eventually gets full SL+TP protection.
        if orders_fetch_ok and not self.dry_run:
            self._repair_missing_protection_orders(bn_order_ids, algo_fetch_ok=algo_fetch_ok)

        # 🧹 Fail-safe leftover order sweeper:
        # If there are open orders on Binance for a symbol, but we have:
        # 1. No active position tracked locally for this symbol.
        # 2. AND no active open position on the exchange for this symbol.
        # Then cancel all open orders for this symbol to prevent orphan leftovers!
        if orders_fetch_ok and not self.dry_run:
            active_symbols = {pos.symbol for pos in self.positions} | bn_open_symbols
            # (1) Regular leftover orders. Algo-aware cancel: a leftover whose id
            # is actually an algoId would fail cancel_order(-2011) → _cancel_order_any
            # falls back to the algo endpoint.
            for order in bn_orders_raw:
                ccxt_sym = order.get("symbol")
                if not ccxt_sym:
                    continue
                order_sym = _strip_contract_suffix(ccxt_sym)
                if order_sym and order_sym not in active_symbols:
                    oid = order.get("id")
                    if oid:
                        log.warning(
                            f"🧹 [cleanup] Leftover orphan order detected on {order_sym} "
                            f"(no active position locally or on exchange). Cancelling order {oid}..."
                        )
                        if self._cancel_order_any(oid, ccxt_sym) == "failed":
                            log.warning(
                                f"⚠️ [cleanup] Failed to cancel leftover order {oid} on {order_sym}"
                            )
            # (2) Leftover ALGO orders (server-side SL/TP). These are invisible to
            # fetch_open_orders, so a closed position's SL/TP can linger forever
            # as an orphan (the DOGE incident: TP filled, 2 STOP_MARKET SLs left).
            # Cancel any algo order whose symbol has no active position via the
            # algo-cancel endpoint. Algo symbols are bare ("DOGEUSDT") — compare
            # against the bare form of the active set.
            active_bn = {s.replace("/", "") for s in active_symbols}
            algo_list = algo_orders if ("algo_orders" in locals() and isinstance(algo_orders, list)) else []
            for a in algo_list:
                if not isinstance(a, dict):
                    continue
                algo_sym = a.get("symbol")
                algo_id = a.get("algoId")
                if not algo_sym or not algo_id or algo_sym in active_bn:
                    continue
                log.warning(
                    f"🧹 [cleanup] Leftover orphan ALGO order on {algo_sym} "
                    f"(no active position). Cancelling algoId={algo_id}..."
                )
                self._cancel_algo_order(str(algo_id))

        # Always persist after a reconcile pass so disk reflects latest exchange-derived
        # state (closes removed from list, tp1_hit flags flipped, sl_order_id updated).
        self._maybe_run_pnl_audit()
        self._persist()
        return closed_now

    def _cancel_position_siblings(
        self,
        pos: "Position",
        ccxt_sym: str,
        reason: str,
    ) -> dict:
        """Best-effort cancel SL + TP1 + TP2 reduceOnly orders for a position.

        Called from every full-close path (reconcile, fallback, kill switch).
        Each cancel is independent: failure of one does not block the others.

        Args:
            pos: the Position whose sibling orders should be cancelled
            ccxt_sym: CCXT futures symbol form (e.g. 'BTC/USDT:USDT')
            reason: short tag for the log line (e.g. 'RECONCILED', 'FALLBACK_CLOSE')

        Returns:
            dict with keys 'cancelled', 'failed', 'missing' — each a list of
            labels ('SL', 'TP1', 'TP2'). Useful for assertions and telemetry.
        """
        # `ccxt` is already imported at module scope (exchange/__init__.py:3)
        result = {"cancelled": [], "failed": [], "missing": []}
        for label, oid in [
            ("SL", pos.sl_order_id),
            ("TP1", pos.tp1_order_id),
            ("TP2", pos.tp2_order_id),
        ]:
            if not self._is_real_oid(oid):
                result["missing"].append(label)
                continue
            # Use the algo-aware cancel: the bot's SL/TP are algo orders, so a
            # plain cancel_order(algoId) returns -2011 and leaves the order
            # resting. _cancel_order_any falls back to the algo-cancel endpoint.
            outcome = self._cancel_order_any(oid, ccxt_sym)
            if outcome == "failed":
                log.warning(
                    f"[cleanup] {pos.symbol}: failed to cancel {label} ({oid})"
                )
            result[outcome].append(label)
        cancelled_str = "+".join(result["cancelled"]) or "none"
        log.info(
            f"[cleanup] {pos.symbol}: cancelled {cancelled_str} (reason={reason})"
        )
        return result

    def _move_sl_to_breakeven(self, pos: Position) -> None:
        """TP1 hit sonrası SL'i entry'ye kaydır (server-side cancel + new order).

        Single-target branch (SMC v2, PR #S5.5): when pos.tp2 is None, the
        lifecycle has already done a full close on TP1 (no remaining size to
        protect). Skip the BE move entirely and instead cancel orphan SL/TP2
        reduceOnly orders on the exchange to prevent them lingering forever.
        Inert under v1 (v1 always sets numeric tp2).

        Retry: New SL at breakeven uses _retry_tp_order (3 attempts, backoff).
        On exhaustion, sl_order_id is set to '' so reconcile's
        _repair_missing_protection_orders catches it on the next cycle.
        """
        if self.dry_run:
            pos.sl = pos.entry
            return

        ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)

        if pos.tp2 is None:
            # Single-target mode: full close already done by lifecycle.
            # Cancel orphan SL (TP1 already filled; TP2 was never placed).
            self._cancel_position_siblings(pos, ccxt_sym, reason="TP1_FULL_CLOSE")
            return

        # Step 1: Cancel old SL (best-effort — failure means it may already
        # be filled/cancelled server-side; new SL is a separate order).
        # Algo-aware: the old SL is an algo order, so cancel_order(algoId) alone
        # returns -2011 and leaves it resting → a duplicate SL after the BE move
        # (the orphan-SL bug). _cancel_order_any falls back to the algo endpoint.
        if self._is_real_oid(pos.sl_order_id):
            if self._cancel_order_any(pos.sl_order_id, ccxt_sym) == "failed":
                log.warning(f"SL cancel failed for {pos.symbol} (continuing)")

        # Step 2: Place new SL at breakeven with retry
        reverse_side = "sell" if pos.direction == "LONG" else "buy"
        remaining_size = pos.size / 2  # TP1 yarısı kapandı, kalan yarısı için SL
        try:
            res = self.client.exchange.amount_to_precision(ccxt_sym, remaining_size)
            if isinstance(res, str):
                remaining_size = float(res)
        except Exception as e:
            log.warning(f"Failed to format remaining SL size using exchange precision for {pos.symbol}: {e}")

        sl_params = {"stopPrice": pos.entry}
        if self.hedge_mode:
            sl_params["positionSide"] = pos.direction
        else:
            sl_params["reduceOnly"] = True

        new_sl_oid = self._retry_tp_order(
            ccxt_sym=ccxt_sym,
            order_type="STOP_MARKET",
            side=reverse_side,
            amount=remaining_size,
            params=sl_params,
            label="SL_BE",
            symbol=pos.symbol,
            direction=pos.direction,
            entry_order_id=pos.order_id,
            sl_order_id=pos.sl_order_id or "",
            price_display=pos.entry,
        )

        # Always update logical SL (lifecycle state stays consistent)
        pos.sl = pos.entry

        if new_sl_oid:
            pos.sl_order_id = new_sl_oid
            log.info(f"  ↳ New SL @ break-even {pos.entry:.4f} | order_id={pos.sl_order_id}")
        else:
            # All retries exhausted — clear order_id so reconcile repairs
            pos.sl_order_id = ""
            log.warning(
                "order_manager.be_sl_placement_failed: %s %s — "
                "sl_order_id cleared, reconcile will repair on next cycle",
                pos.symbol, pos.direction,
                extra={
                    "event": "order_manager.be_sl_placement_failed",
                    "symbol": pos.symbol,
                    "direction": pos.direction,
                    "sl_price": pos.sl,
                },
            )

    def _estimate_exit_price(
        self, pos: Position, bn_order_ids: set, fetch_ok: bool = True
    ) -> float:
        """Reconcile sırasında exit price tahmin et.

        Hangi order tetiklendi? — canlı id set'inde olmayan TP/SL order'ı = filled.

        bn_order_ids MUST be the algo-inclusive id set (regular fetch_open_orders
        ids + fapiPrivateGetOpenAlgoOrders algoIds), because pos.sl/tp1/tp2_order_id
        are server-side ALGO ids. Passing a regular-orders-only set makes every algo
        leg look 'missing' and mis-attributes every close to TP2/SL — an SL-hit loss
        gets logged as a TP2 profit, feeding phantom PnL to the drawdown breaker.

        fetch_ok must be False when EITHER the regular or algo open-orders fetch
        failed this cycle: the set is then incomplete (a live leg can look missing),
        so we fall through to the current market price instead of a phantom TP2/SL
        attribution.
        """
        # Only attribute a triggered leg when the live id set is trustworthy.
        if fetch_ok:
            if self._is_real_oid(pos.tp2_order_id) and pos.tp2_order_id not in bn_order_ids:
                return pos.tp2  # TP2 hit
            if self._is_real_oid(pos.sl_order_id) and pos.sl_order_id not in bn_order_ids:
                return pos.sl   # SL hit
            if self._is_real_oid(pos.tp1_order_id) and pos.tp1_order_id not in bn_order_ids and not pos.tp1_hit:
                return pos.tp1
        # Fetch failed, or no leg identifiably missing → current market price.
        try:
            return self.client.get_price(pos.symbol)
        except Exception:
            return pos.entry

    def _record_close(self, pos: Position, exit_price: float, reason: str) -> None:
        """Pozisyon kapanış metadata'sını doldur ve event emit et.

        PR C: prefer Binance net realizedPnl (realizedPnl - commission - funding)
        over the gross estimate. Falls back to the estimate (and tags
        pnl_source="estimated") when the exchange read soft-fails.
        """
        is_long = pos.direction == "LONG"
        pnl_pct = ((exit_price - pos.entry) / pos.entry * 100) if is_long else \
                  ((pos.entry - exit_price) / pos.entry * 100)
        est_pnl_usdt = (exit_price - pos.entry) * pos.size if is_long else \
                       (pos.entry - exit_price) * pos.size

        # Exchange-truth PnL (soft-fail → keep estimate).
        pnl_usdt = est_pnl_usdt
        pos.pnl_source = "estimated"
        try:
            since_ms = int(pd.Timestamp(pos.opened_at).value // 1_000_000) if pos.opened_at else 0
        except Exception:
            since_ms = 0
        try:
            res = self.client.fetch_realized_pnl(pos.symbol, since_ms=since_ms)
        except Exception:
            res = {"ok": False}
        # isinstance guard: a real BinanceClient returns a dict; mock/absent
        # clients (or anything non-dict) fall through to the estimate.
        if isinstance(res, dict) and res.get("ok"):
            pnl_usdt = res["net"]
            pos.realized_pnl_exchange = res.get("realized_pnl", 0.0)
            pos.commission_paid = res.get("commission", 0.0)
            pos.funding_paid = res.get("funding", 0.0)
            pos.pnl_source = "exchange"

        pos.closed_at = pd.Timestamp.now(tz="UTC").isoformat()
        pos.exit_reason = reason
        pos.exit_price = exit_price
        pos.pnl_usdt = pnl_usdt

        log.info(
            f"{reason}: {pos.symbol} {pos.direction} | "
            f"Entry={pos.entry:.4f} Exit={exit_price:.4f} | "
            f"PnL={pnl_pct:+.2f}% (${pnl_usdt:+.2f}) [{pos.pnl_source}]"
        )

        self.closed_positions.append(pos)
        self._journal_record_close(pos, exit_price, reason)
        self._emit("position_closed", pos)

    def _fetch_protection_order_ids(self, symbol: str):
        """Return (set_of_order_ids, ok). Merges regular open orders + algo
        (server-side TP/SL) orders, using the SAME account-wide fetch shape as
        reconcile() (fetch_open_orders() -> [{id}], fapiPrivateGetOpenAlgoOrders({})
        -> [{algoId}]) so a symbol-form mismatch can't read a live leg as
        missing. Membership is tested by order-id, so account-wide is fine.
        ok=False on the regular-orders fetch failure so the caller does not
        misread a transient error as 'all orders gone' (and never force-closes
        a healthy position on a read failure).
        """
        ids = set()
        try:
            for o in (self.client.exchange.fetch_open_orders() or []):
                oid = o.get("id") if isinstance(o, dict) else None
                if oid is not None:
                    ids.add(str(oid))
        except Exception as e:
            log.warning(f"verify: fetch_open_orders failed for {symbol}: {e}")
            return set(), False
        try:
            algo = self.client.exchange.fapiPrivateGetOpenAlgoOrders({}) or []
            for a in algo:
                oid = a.get("algoId") or a.get("id") if isinstance(a, dict) else None
                if oid is not None:
                    ids.add(str(oid))
        except Exception as e:
            # Algo fetch is best-effort; regular open orders already retrieved.
            log.debug(f"verify: algo-order fetch failed for {symbol}: {e}")
        return ids, True

    def _verify_and_repair_protection(self, pos: "Position") -> dict:
        """Confirm SL/TP orders are live on the exchange shortly after entry.

        Per attempt: re-query live orders; latch each leg 'secured' once it is
        confirmed present OR successfully (re)placed; re-place a confirmed-missing
        leg AT MOST ONCE (avoids stacking duplicate SL/TP when the algo endpoint
        merely lags). Fallback after attempts:
        - SL never secured AND at least one read succeeded → cancel siblings +
          market-close (never hold bare). The sibling-cancel is essential: TP1/TP2
          may already be live, so closing without it would orphan reduceOnly orders.
        - only TP unsecured → tolerate; store the -2021 sentinel (NOT blank) so
          reconcile's repair skips it instead of churning.
        - NO read ever succeeded (network partition) → DO NOT rollback. Forcing a
          close on a position whose SL is really live would be the worst outcome;
          tolerate and let reconcile handle it once reads recover (mirrors
          reconcile's own 'missing != filled when fetch failed' rule).

        Gated by enable_post_placement_verify. No-op (skipped) when disabled or
        dry_run. Returns a dict summary for logging/tests.
        """
        if not getattr(self, "enable_post_placement_verify", False) or self.dry_run:
            return {"skipped": True, "sl_ok": True}

        ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
        reverse_side = "sell" if pos.direction == "LONG" else "buy"
        # Latching flags — once True they stay True (a later lagging read or a
        # successful re-place can only confirm, never un-confirm, a leg).
        sl_secured = tp1_secured = False
        tp2_secured = pos.tp2 is None         # no TP2 leg = nothing to secure
        sl_tried = tp1_tried = tp2_tried = False   # re-place at most once per leg
        any_fetch_ok = False

        for attempt in range(1, max(1, self.verify_max_attempts) + 1):
            if self.verify_delay_sec > 0:
                _time.sleep(self.verify_delay_sec)
            ids, fetched_ok = self._fetch_protection_order_ids(pos.symbol)
            if not fetched_ok:
                continue                       # don't judge legs on a failed read
            any_fetch_ok = True

            # Confirm-present latches (a leg with no real id needs no protection).
            if (not self._is_real_oid(pos.sl_order_id)) or pos.sl_order_id in ids:
                sl_secured = True
            if (not self._is_real_oid(pos.tp1_order_id)) or pos.tp1_order_id in ids:
                tp1_secured = True
            if pos.tp2 is not None and (
                    (not self._is_real_oid(pos.tp2_order_id)) or pos.tp2_order_id in ids):
                tp2_secured = True

            if sl_secured and tp1_secured and tp2_secured:
                return {"skipped": False, "sl_ok": True, "tp1_ok": True,
                        "tp2_ok": True, "attempts": attempt}

            # Re-place confirmed-missing legs, once each.
            if not sl_secured and not sl_tried:
                sl_tried = True
                sl_params = {"stopPrice": pos.sl}
                if self.hedge_mode:
                    sl_params["positionSide"] = pos.direction
                else:
                    sl_params["reduceOnly"] = True
                new_sl = self._retry_tp_order(
                    ccxt_sym=ccxt_sym, order_type="STOP_MARKET", side=reverse_side,
                    amount=pos.size, params=sl_params, label="SL",
                    symbol=pos.symbol, direction=pos.direction,
                    entry_order_id=pos.order_id, sl_order_id="", price_display=pos.sl,
                )
                if self._is_real_oid(new_sl):
                    pos.sl_order_id = new_sl
                    sl_secured = True

            if not tp1_secured and not tp1_tried:
                tp1_tried = True
                tp1_params = {"stopPrice": pos.tp1}
                if self.hedge_mode:
                    tp1_params["positionSide"] = pos.direction
                else:
                    tp1_params["reduceOnly"] = True
                tp1_size = pos.size if pos.tp2 is None else pos.size / 2
                new_tp1 = self._retry_tp_order(
                    ccxt_sym=ccxt_sym, order_type="TAKE_PROFIT_MARKET", side=reverse_side,
                    amount=tp1_size, params=tp1_params, label="TP1",
                    symbol=pos.symbol, direction=pos.direction,
                    entry_order_id=pos.order_id, sl_order_id=pos.sl_order_id,
                    price_display=pos.tp1,
                )
                if self._is_real_oid(new_tp1):
                    pos.tp1_order_id = new_tp1
                    tp1_secured = True
                elif new_tp1 == _TP_UNREACHABLE_SENTINEL:
                    # Price already past TP1 → unplaceable. Store the sentinel
                    # (not blank) so reconcile/_is_real_oid skips it and does not
                    # churn re-repairing (PR #102a contract).
                    pos.tp1_order_id = _TP_UNREACHABLE_SENTINEL
                    tp1_secured = True

            if pos.tp2 is not None and not tp2_secured and not tp2_tried:
                tp2_tried = True
                tp2_params = {"stopPrice": pos.tp2}
                if self.hedge_mode:
                    tp2_params["positionSide"] = pos.direction
                else:
                    tp2_params["reduceOnly"] = True
                new_tp2 = self._retry_tp_order(
                    ccxt_sym=ccxt_sym, order_type="TAKE_PROFIT_MARKET", side=reverse_side,
                    amount=pos.size / 2, params=tp2_params, label="TP2",
                    symbol=pos.symbol, direction=pos.direction,
                    entry_order_id=pos.order_id, sl_order_id=pos.sl_order_id,
                    price_display=pos.tp2, tp1_order_id=pos.tp1_order_id,
                )
                if self._is_real_oid(new_tp2):
                    pos.tp2_order_id = new_tp2
                    tp2_secured = True
                elif new_tp2 == _TP_UNREACHABLE_SENTINEL:
                    pos.tp2_order_id = _TP_UNREACHABLE_SENTINEL
                    tp2_secured = True

            if sl_secured and tp1_secured and tp2_secured:
                return {"skipped": False, "sl_ok": True, "tp1_ok": True,
                        "tp2_ok": True, "attempts": attempt}

        # Attempts exhausted — fallback decision.
        if not any_fetch_ok:
            # Could not read the exchange at all → never force-close (would be
            # the network-partition false-close). Tolerate; reconcile recovers.
            log.warning(
                "verify.no_read_tolerated: %s %s — could not confirm SL/TP "
                "(all reads failed); leaving to reconcile", pos.symbol, pos.direction,
            )
            return {"skipped": False, "sl_ok": True, "tolerated_no_read": True}

        if not sl_secured and self.rollback_on_sl_failure:
            log.critical(
                "verify.sl_unconfirmed_rollback: %s %s entry=%s — cancelling "
                "siblings + market-closing to avoid a bare position",
                pos.symbol, pos.direction, pos.order_id,
                extra={"event": "verify.sl_unconfirmed_rollback",
                       "symbol": pos.symbol, "direction": pos.direction},
            )
            try:
                # Cancel any already-live TP1/TP2 (and SL) first so the market
                # close does not leave orphaned reduceOnly orders on a flat symbol.
                self._cancel_position_siblings(pos, ccxt_sym, reason="VERIFY_ROLLBACK")
                self._rollback_entry_after_protection_failure(
                    ccxt_sym=ccxt_sym, rollback_side=reverse_side,
                    rollback_size=pos.size, symbol=pos.symbol,
                    direction=pos.direction, entry_order_id=pos.order_id,
                    original_error=Exception("SL unconfirmed after post-placement verify"),
                )
            finally:
                if pos in self.positions:
                    self.positions.remove(pos)
                self._persist()
            return {"skipped": False, "sl_ok": False, "rolled_back": True}

        if not (tp1_secured and tp2_secured):
            log.warning(
                "verify.tp_unconfirmed_tolerated: %s %s — SL is live; reconcile "
                "will keep retrying TP", pos.symbol, pos.direction,
            )
        return {"skipped": False, "sl_ok": sl_secured,
                "tp1_ok": tp1_secured, "tp2_ok": tp2_secured}

    def _maybe_run_pnl_audit(self) -> None:
        """Tick the cycle counter; run the audit sweep every N cycles."""
        if not self.enable_pnl_audit:
            return
        self._pnl_audit_cycle += 1
        if self._pnl_audit_cycle % max(1, self.pnl_audit_every_cycles) != 0:
            return
        try:
            self.audit_realized_pnl(window_hours=24)
        except Exception as e:
            log.warning(f"pnl_audit sweep failed: {e}")

    def audit_realized_pnl(self, window_hours: int = 24) -> int:
        """Re-reconcile recently-closed positions still tagged 'estimated'.

        Pulls exchange income for each estimated close within the window and
        upgrades pnl_usdt to net exchange truth. Returns the number corrected.
        Soft-fails per position so one bad read never aborts the sweep.

        Limitation: closed_positions is in-memory (not persisted/restored), so
        the sweep only reaches closes from the current process lifetime. A close
        that soft-failed to 'estimated' just before a restart keeps its estimate
        in the journal. Acceptable given the breaker is not back-corrected either
        (reporting-only PR); a future journal-sourced audit could close this gap.
        """
        try:
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=window_hours)
        except Exception:
            return 0
        corrected = 0
        self._last_pnl_corrections = []  # M4: fresh per sweep
        self._detailed_pnl_corrections = []
        for pos in self.closed_positions:
            if pos.pnl_source == "exchange":
                continue
            if not pos.closed_at:
                continue
            try:
                closed_ts = pd.Timestamp(pos.closed_at)
                if closed_ts < cutoff:
                    continue
                since_ms = int(pd.Timestamp(pos.opened_at).value // 1_000_000)
                # Bound the income window to THIS position's lifetime (+5s for
                # fill-time posting lag) so a later trade on the same symbol
                # cannot have its realizedPnl/commission misattributed here.
                until_ms = int(closed_ts.value // 1_000_000) + 5_000
            except Exception:
                continue
            try:
                res = self.client.fetch_realized_pnl(
                    pos.symbol, since_ms=since_ms, until_ms=until_ms)
            except Exception:
                res = {"ok": False}
            if not (isinstance(res, dict) and res.get("ok")):
                continue
            old = pos.pnl_usdt
            pos.pnl_usdt = res["net"]
            pos.realized_pnl_exchange = res.get("realized_pnl", 0.0)
            pos.commission_paid = res.get("commission", 0.0)
            pos.funding_paid = res.get("funding", 0.0)
            pos.pnl_source = "exchange"
            corrected += 1
            self._last_pnl_corrections.append(
                (pos.order_id or f"{pos.symbol}-{pos.opened_at}", old, pos.pnl_usdt)
            )
            self._detailed_pnl_corrections.append({
                "order_id": pos.order_id,
                "symbol": pos.symbol,
                "trace_id": getattr(pos, "trace_id", None),
                "old_pnl": old,
                "new_pnl": pos.pnl_usdt
            })
            log.info(
                "pnl_audit: corrected %s %s est=%.4f → exchange=%.4f",
                pos.symbol, pos.direction, old, pos.pnl_usdt,
            )
            # Idempotent in-place journal update — NOT _journal_record_close,
            # which would append a duplicate entry row (no dedup in record_entry).
            if self.trade_journal is not None:
                trade_id = pos.order_id or f"{pos.symbol}-{pos.opened_at}"
                self.trade_journal.update_realized_pnl(
                    trade_id, realized_pnl=pos.pnl_usdt, pnl_source="exchange",
                    realized_pnl_exchange=pos.realized_pnl_exchange,
                    commission_paid=pos.commission_paid,
                    funding_paid=pos.funding_paid,
                )
        return corrected

    def _journal_record_close(self, pos: Position, exit_price: float, reason: str) -> None:
        """Write a full TradeSnapshot (entry+exit atomically) to TradeJournal.

        No-op when self.trade_journal is None. trade_id derives from the
        exchange order_id (or a symbol-timestamp fallback when missing).
        bars_held is 0 here; per-bar tracking arrives in a follow-up PR.
        MAE/MFE likewise. Wrapped in try/except so journal failures degrade
        to a log warning — never break the close flow.
        """
        if self.trade_journal is None:
            return
        # Lazy import to keep engine.journal a soft dependency.
        from engine.journal import TradeSnapshot

        trade_id = pos.order_id or f"{pos.symbol}-{pos.opened_at}"
        try:
            snap = TradeSnapshot(
                trade_id=trade_id,
                symbol=pos.symbol,
                direction=pos.direction,
                timeframe="",
                entry_timestamp=pos.opened_at,
                entry_price=pos.entry,
                sl_initial=pos.sl,
                tp1_initial=pos.tp1,
                tp2_initial=pos.tp2,
                position_size=pos.size,
                htf_bias="",
                intent_score_entry=0,
                intent_label_entry="",
                confluence_score=0,
                pnl_source=pos.pnl_source,
                realized_pnl_exchange=pos.realized_pnl_exchange,
                commission_paid=pos.commission_paid,
                funding_paid=pos.funding_paid,
            )
            self.trade_journal.record_entry(snap)
            self.trade_journal.record_exit(
                trade_id=trade_id,
                exit_price=exit_price,
                exit_reason=reason,
                realized_pnl=pos.pnl_usdt,
                bars_held=0,
                mfe_pct=pos.mfe_pct,
                mae_pct=pos.mae_pct,
            )
        except Exception as e:
            log.warning(f"trade_journal write failed for {pos.symbol} {trade_id}: {e}")

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

            # TP2 fallback — guard against single-target Position (tp2=None).
            # Mirrors engine/lifecycle.py:on_tick TP2 guard added in PR #S5.
            if pos.tp2 is not None and (
                (is_long and price >= pos.tp2) or (not is_long and price <= pos.tp2)
            ):
                log.warning(f"Polling TP2 hit detected for {pos.symbol} (server-side missed?)")
                self._fallback_close(pos, price, "TP2_POLL")

    def _fallback_close(self, pos: Position, price: float, reason: str):
        """Polling fallback: market close + cancel pending TP/SL orders."""
        if not self.dry_run:
            close_side = "sell" if pos.direction == "LONG" else "buy"
            ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
            try:
                close_params = {}
                if self.hedge_mode:
                    close_params["positionSide"] = pos.direction
                else:
                    close_params["reduceOnly"] = True
                self.client.exchange.create_order(
                    ccxt_sym, "market", close_side, pos.size,
                    params=close_params)
            except Exception as e:
                log.error(f"Fallback close failed: {e}")

            # Pending order cleanup — DRY via shared helper
            self._cancel_position_siblings(pos, ccxt_sym, reason=f"FALLBACK_{reason}")

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
