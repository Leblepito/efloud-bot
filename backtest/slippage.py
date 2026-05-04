"""Per-leg slippage model for backtest fills."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SlippageConfig:
    entry_slip_pct: float = 0.05  # 5 bp adverse on market entry
    sl_slip_pct: float = 0.10     # 10 bp adverse on SL fills (gaps)
    exit_slip_pct: float = 0.05   # 5 bp adverse on TP fills


def adverse_fill(price: float, direction: str, leg: str, cfg: SlippageConfig) -> float:
    """Apply per-leg slippage in trader-adverse direction.

    LONG entry  → buy → adverse-up
    SHORT entry → sell → adverse-down
    LONG SL/TP  → sell → adverse-down
    SHORT SL/TP → buy → adverse-up
    """
    pct_map = {"entry": cfg.entry_slip_pct, "SL": cfg.sl_slip_pct, "TP": cfg.exit_slip_pct}
    if leg not in pct_map:
        raise ValueError(f"Unknown leg: {leg!r}")
    pct = pct_map[leg]
    is_buy = (direction == "LONG" and leg == "entry") or (direction == "SHORT" and leg in ("SL", "TP"))
    sign = +1 if is_buy else -1
    return price * (1 + sign * pct / 100)
