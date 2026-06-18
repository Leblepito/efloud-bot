LIVE_NET_BASELINE = -5.3  # %, the real track record this shadow must beat

def _status_line(o):
    st = o.get("status")
    n = o.get("n", 0)
    if st == "insufficient_sample":
        return f"INSUFFICIENT EVIDENCE — n={n} resolved (need more), NET, readonly+tradeable universe"
    if not o.get("edge_sign_stable", False):
        return f"NO VERDICT — edge sign unstable across timeout-marking (n={n})"
    exp = o.get("expectancy")
    verdict = "EDGE PRESENT" if (exp is not None and exp > 0 and st == "ok") else "NO EDGE"
    return f"{verdict} — NET E[R]={exp:.3f}, n={n} (vs live net {LIVE_NET_BASELINE}%)"

def build_report(metrics: dict) -> str:
    o = metrics["overall"]
    lines = [_status_line(o), ""]
    lines.append(f"Primary hypothesis: {metrics.get('primary_hypothesis','')}")
    lines.append(f"Status breakdown: {metrics.get('status_breakdown', {})}")
    lines.append(f"Timeout rate: {o.get('timeout_rate', 0):.1%}")
    if o.get("expectancy") is not None:
        lines.append(f"NET expectancy: {o['expectancy']:.3f} R | win-rate CI: {o.get('win_rate_ci')}")
        lines.append(f"Profit factor: {o.get('profit_factor')}")
    lines.append("")
    lines.append("Breakdowns (SECONDARY/exploratory — multiple-testing applies):")
    for name, cells in metrics.get("breakdowns", {}).items():
        lines.append(f"  {name}:")
        for k, c in cells.items():
            if c.get("status") == "insufficient_sample":
                lines.append(f"    {k}: insufficient (n={c['n']})")
            else:
                lines.append(f"    {k}: NET E[R]={c['expectancy']:.3f}, n={c['n']}, PF={c.get('profit_factor')}")
    lines += ["",
              "DISCLAIMER: shadow hypo_r is HYPOTHETICAL (MARKET-at-confirmation fill, conservative",
              f"same-bar=SL, cost-netted) and is NOT the live NET record (~{LIVE_NET_BASELINE}%).",
              "Not financial advice. Research log only."]
    return "\n".join(lines)
