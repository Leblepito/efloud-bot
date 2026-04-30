"""Pozisyon boyutu hesaplama — risk bazlı + notional cap."""

import logging

log = logging.getLogger("efloud.risk")


def calc_position_size(
    balance: float,
    risk_pct: float,          # %1.5 → 1.5
    entry: float,
    sl: float,
    leverage: int = 1,
    max_notional_pct: float = None,  # Tek pozisyon max bakiye % (örn 3.0)
) -> float:
    """
    Risk bazlı pozisyon boyutu + notional cap.
    
    İki cap:
      1. Risk cap: (balance × risk_pct) / SL_distance
      2. Notional cap: balance × max_notional_pct (verilmişse)
    
    Sonuç: ikisinin küçüğü.
    """
    risk_amount = balance * (risk_pct / 100)
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        log.warning("SL distance = 0, returning 0")
        return 0.0

    # Risk-based sizing
    position_usdt_risk = risk_amount / sl_distance * entry

    # Notional cap (eğer verildiyse)
    if max_notional_pct is not None:
        max_notional_usdt = balance * (max_notional_pct / 100) * leverage
        position_usdt = min(position_usdt_risk, max_notional_usdt)
        if position_usdt < position_usdt_risk:
            log.debug(f"Size capped by notional: {position_usdt_risk:.2f} → {position_usdt:.2f}")
    else:
        position_usdt = position_usdt_risk

    # Kontrat = USDT değer / fiyat
    contracts = position_usdt / entry

    log.debug(f"Position: balance={balance:.0f} risk=${risk_amount:.2f} "
              f"sl_dist={sl_distance:.4f} size={contracts:.6f} ({position_usdt:.2f} USDT)")
    return round(contracts, 6)
