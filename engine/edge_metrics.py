# engine/edge_metrics.py
from __future__ import annotations
from collections import Counter
from statistics import mean

def _wilson(wins, n, z=1.96):
    if n == 0:
        return (None, None)
    p = wins / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = (z * ((p*(1-p)/n + z*z/(4*n*n)) ** 0.5)) / denom
    return (center - half, center + half)

def _pf(rs):
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)
    if losses == 0:
        return None
    return gains / losses

def _cell(rs, min_n_print, min_n_claim):
    n = len(rs)
    if n < min_n_print:
        return {"n": n, "status": "insufficient_sample", "expectancy": None,
                "win_rate": None, "profit_factor": None}
    wins = sum(1 for r in rs if r > 0)
    wr = wins / n
    lo, hi = _wilson(wins, n)
    exp = mean(rs)
    return {"n": n, "status": "ok" if n >= min_n_claim else "underpowered",
            "expectancy": exp, "win_rate": wr, "win_rate_ci": [lo, hi],
            "profit_factor": _pf(rs)}

def _timeout_panel(resolved_rs, timeout_recs):
    m2m = resolved_rs + [(r.mfe_r + r.mae_r) / 2 if r.mfe_r is not None else 0.0 for r in timeout_recs]
    zero = resolved_rs + [0.0 for _ in timeout_recs]
    excl = resolved_rs[:]
    signs = {"mark_to_market": mean(m2m) if m2m else 0.0,
             "zero": mean(zero) if zero else 0.0,
             "excluded": mean(excl) if excl else 0.0}
    stable = len({1 if v > 0 else -1 if v < 0 else 0 for v in signs.values()}) == 1
    return signs, stable

def aggregate(records, min_n_print=30, min_n_claim=100):
    status_breakdown = Counter(r.status for r in records)
    resolved = [r for r in records if r.status == "resolved" and r.hypo_r_net is not None]
    timeouts = [r for r in records if r.status == "timeout"]
    rs = [r.hypo_r_net for r in resolved]
    overall = _cell(rs, min_n_print, min_n_claim)
    panel, stable = _timeout_panel(rs, timeouts)
    overall["timeout_panel"] = panel
    overall["edge_sign_stable"] = stable
    overall["timeout_rate"] = (len(timeouts) / (len(resolved) + len(timeouts))) if (resolved or timeouts) else 0.0

    def band(c):
        return "55-65" if c < 65 else "65-75" if c < 75 else "75+"
    breakdowns = {"by_confluence": {}, "by_symbol": {}, "by_direction": {}, "by_was_tradeable": {}}
    groups = {
        "by_confluence": lambda r: band(r.confluence),
        "by_symbol": lambda r: r.symbol,
        "by_direction": lambda r: r.direction,
        "by_was_tradeable": lambda r: str(r.was_tradeable),
    }
    for name, keyfn in groups.items():
        buckets: dict[str, list] = {}
        for r in resolved:
            buckets.setdefault(keyfn(r), []).append(r.hypo_r_net)
        breakdowns[name] = {k: _cell(v, min_n_print, min_n_claim) for k, v in buckets.items()}

    return {"overall": overall, "breakdowns": breakdowns,
            "status_breakdown": dict(status_breakdown),
            "fdr": "BH-FDR NOT YET APPLIED — breakdown cells are exploratory/uncorrected",
            "primary_hypothesis": "pooled NET expectancy, tradeable universe"}
