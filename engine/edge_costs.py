# engine/edge_costs.py
"""Cost netting for shadow edge in R-units. Fees+funding+slippage subtracted from raw R."""

def net_r(direction, entry, sl, raw_r, holding_hours, funding_pct_sum,
          taker_rate=0.0004, slippage_r=0.05):
    risk = abs(float(entry) - float(sl))
    if risk == 0:
        return raw_r
    entry = float(entry)
    fee_price = 2.0 * taker_rate * entry
    fee_r = fee_price / risk
    funding_price = float(funding_pct_sum) * entry
    funding_r = (funding_price / risk) * (1.0 if direction == "LONG" else -1.0)
    return raw_r - fee_r - funding_r - float(slippage_r)
