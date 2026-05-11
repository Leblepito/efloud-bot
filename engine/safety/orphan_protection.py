"""Default-off orphan position auto-protection.

Detects whether exchange-only positions have protective SL coverage and, when
explicitly enabled, can place a close-position STOP_MARKET SL. It never imports
orphans into lifecycle state, never places TP orders, and never cancels orders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

log = logging.getLogger("efloud.orphan_protection")

Mode = Literal["warn_only", "place_missing_sl"]
Action = Literal[
    "none_protected", "warn_only", "placed_sl", "skipped_critical_warning",
    "skipped_too_close", "skipped_max_per_cycle", "skipped_no_tp",
]


@dataclass(frozen=True)
class OrphanProtectionConfig:
    enabled: bool
    mode: Mode
    default_sl_pct: float
    max_auto_protect_per_cycle: int
    min_distance_to_mark_pct: float
    require_tp_present: bool


@dataclass(frozen=True)
class CoverageStatus:
    symbol: str
    side: Literal["long", "short"]
    size: float
    has_protective_sl: bool
    sl_is_wrong_direction: bool
    sl_not_reduce_only: bool
    has_tp: bool
    raw_sl_orders: list
    reason_if_unprotected: Optional[str]


@dataclass(frozen=True)
class ProtectionAction:
    symbol: str
    action: Action
    sl_price: Optional[float] = None
    error: Optional[str] = None


def load_orphan_protection_config(safety_cfg: dict | None) -> OrphanProtectionConfig:
    safety_cfg = safety_cfg or {}
    raw = safety_cfg.get("orphan_protection", {}) or {}
    mode = raw.get("mode", "warn_only")
    if mode not in ("warn_only", "place_missing_sl"):
        log.warning("unknown orphan_protection mode %r; falling back to warn_only", mode)
        mode = "warn_only"
    cfg = OrphanProtectionConfig(
        enabled=bool(raw.get("enabled", False)),
        mode=mode,
        default_sl_pct=float(raw.get("default_sl_pct", 2.0)),
        max_auto_protect_per_cycle=int(raw.get("max_auto_protect_per_cycle", 1)),
        min_distance_to_mark_pct=float(raw.get("min_distance_to_mark_pct", 0.5)),
        require_tp_present=bool(raw.get("require_tp_present", True)),
    )
    log.info(
        "orphan_protection config loaded: enabled=%s mode=%s",
        cfg.enabled, cfg.mode,
        extra={
            "event": "orphan_protection.config_loaded",
            "enabled": cfg.enabled,
            "mode": cfg.mode,
        },
    )
    return cfg


class OrphanProtector:
    PROTECTIVE_TYPES = {
        "STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET",
        "TRAILING_STOP_MARKET", "TRIGGER_LIMIT", "TRIGGER_MARKET",
    }

    def __init__(self, config: OrphanProtectionConfig, client):
        self.config = config
        self.client = client

    @staticmethod
    def _strip_symbol(symbol: str) -> str:
        return symbol.split(":", 1)[0] if ":" in symbol else symbol

    @staticmethod
    def _raw_symbol(symbol: str) -> str:
        return OrphanProtector._strip_symbol(symbol).replace("/", "")

    @staticmethod
    def _field(order: dict, *names, default=None):
        info = order.get("info", {}) if isinstance(order.get("info"), dict) else {}
        for name in names:
            if name in order and order.get(name) is not None:
                return order.get(name)
            if name in info and info.get(name) is not None:
                return info.get(name)
        return default

    @staticmethod
    def _truthy(value) -> bool:
        return value is True or str(value).lower() == "true"

    def analyze_coverage(self, position, all_algo_orders) -> CoverageStatus:
        symbol = position.get("symbol", "")
        side = (position.get("side") or "").lower()
        size = abs(float(position.get("contracts", 0) or position.get("positionAmt", 0) or 0))
        expected_close_side = "SELL" if side == "long" else "BUY"
        symbol_candidates = {symbol, self._strip_symbol(symbol), self._raw_symbol(symbol)}

        has_protective_sl = False
        sl_wrong_direction = False
        sl_not_reduce_only = False
        has_tp = False
        raw_sl_orders = []
        saw_undercovered_sl = False

        for order in all_algo_orders:
            o_symbol = self._field(order, "symbol", default="")
            if o_symbol not in symbol_candidates:
                continue
            o_type = str(self._field(order, "type", "origType", "orderType", default="")).upper()
            if o_type not in self.PROTECTIVE_TYPES and "STOP" not in o_type and "PROFIT" not in o_type:
                continue
            o_side = str(self._field(order, "side", default="")).upper()
            o_qty_raw = self._field(order, "amount", "origQty", "quantity", default=0)
            try:
                o_qty = float(o_qty_raw or 0)
            except (TypeError, ValueError):
                o_qty = 0.0
            o_close_position = self._truthy(self._field(order, "closePosition", default=False))
            o_reduce_only = self._truthy(self._field(order, "reduceOnly", default=False))
            is_sl = "STOP" in o_type and "PROFIT" not in o_type
            is_tp = "PROFIT" in o_type

            if is_tp:
                has_tp = True
            if not is_sl:
                continue

            raw_sl_orders.append(order)
            direction_ok = o_side == expected_close_side
            reduce_only_ok = o_reduce_only or o_close_position
            qty_covers_full = o_close_position or (size > 0 and o_qty >= size * 0.99)

            if not direction_ok:
                sl_wrong_direction = True
            if not reduce_only_ok:
                sl_not_reduce_only = True
            if not qty_covers_full:
                saw_undercovered_sl = True
            if qty_covers_full and direction_ok and reduce_only_ok:
                has_protective_sl = True

        reason = None
        if not has_protective_sl:
            if raw_sl_orders and saw_undercovered_sl:
                reason = "undercovered_sl"
            else:
                reason = "missing_sl"

        return CoverageStatus(
            symbol=self._strip_symbol(symbol),
            side=side,
            size=size,
            has_protective_sl=has_protective_sl,
            sl_is_wrong_direction=sl_wrong_direction,
            sl_not_reduce_only=sl_not_reduce_only,
            has_tp=has_tp,
            raw_sl_orders=raw_sl_orders,
            reason_if_unprotected=reason,
        )

    def place_close_position_sl(self, position) -> ProtectionAction:
        symbol = position.get("symbol", "")
        side = (position.get("side") or "").lower()
        entry = float(position.get("entryPrice", 0) or 0)
        mark = float(position.get("markPrice", entry) or entry or 0)
        if entry <= 0 or side not in ("long", "short"):
            return ProtectionAction(symbol=self._strip_symbol(symbol), action="skipped_critical_warning", error="invalid_position")

        if side == "long":
            close_side = "sell"
            sl_price = entry * (1 - self.config.default_sl_pct / 100.0)
        else:
            close_side = "buy"
            sl_price = entry * (1 + self.config.default_sl_pct / 100.0)

        distance_pct = abs(mark - sl_price) / mark * 100 if mark > 0 else 0
        if distance_pct < self.config.min_distance_to_mark_pct:
            return ProtectionAction(symbol=self._strip_symbol(symbol), action="skipped_too_close", sl_price=sl_price)

        try:
            ccxt_symbol = self.client.to_ccxt_symbol(self._strip_symbol(symbol))
            self.client.exchange.create_order(
                ccxt_symbol,
                "STOP_MARKET",
                close_side,
                None,
                params={"stopPrice": sl_price, "closePosition": True, "reduceOnly": True},
            )
            log.info(
                "orphan_protection placed close-position SL",
                extra={"event": "orphan_protection.placed_sl", "symbol": self._strip_symbol(symbol), "sl_price": sl_price},
            )
            return ProtectionAction(symbol=self._strip_symbol(symbol), action="placed_sl", sl_price=sl_price)
        except Exception as e:
            log.critical("orphan_protection SL placement failed for %s: %s", symbol, e)
            return ProtectionAction(symbol=self._strip_symbol(symbol), action="skipped_critical_warning", sl_price=sl_price, error=str(e))

    def protect_cycle(self, orphan_positions, all_algo_orders) -> list[ProtectionAction]:
        actions: list[ProtectionAction] = []
        placed = 0
        for position in orphan_positions:
            status = self.analyze_coverage(position, all_algo_orders)
            if status.has_protective_sl:
                actions.append(ProtectionAction(status.symbol, "none_protected"))
                continue
            if status.sl_is_wrong_direction or status.sl_not_reduce_only:
                log.critical(
                    "orphan_protection critical unsafe SL for %s wrong_direction=%s not_reduce_only=%s",
                    status.symbol, status.sl_is_wrong_direction, status.sl_not_reduce_only,
                )
                actions.append(ProtectionAction(status.symbol, "skipped_critical_warning", error=status.reason_if_unprotected))
                continue
            if self.config.require_tp_present and not status.has_tp:
                log.warning("orphan_protection skip %s: no TP present", status.symbol)
                actions.append(ProtectionAction(status.symbol, "skipped_no_tp"))
                continue
            if (not self.config.enabled) or self.config.mode == "warn_only":
                log.warning("orphan_protection warn_only: %s unprotected (%s)", status.symbol, status.reason_if_unprotected)
                actions.append(ProtectionAction(status.symbol, "warn_only"))
                continue
            if placed >= self.config.max_auto_protect_per_cycle:
                actions.append(ProtectionAction(status.symbol, "skipped_max_per_cycle"))
                continue
            action = self.place_close_position_sl(position)
            if action.action == "placed_sl":
                placed += 1
            actions.append(action)
        return actions
