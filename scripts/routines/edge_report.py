from scripts.routines.runner import register

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
    if not o.get("n"):
        # activation item I: explicit empty-ledger line
        lines.insert(1, "No signals recorded yet — the ledger is empty.")
    lines.append(f"Primary hypothesis: {metrics.get('primary_hypothesis','')}")
    lines.append(f"Status breakdown: {metrics.get('status_breakdown', {})}")
    lines.append(f"Timeout rate: {o.get('timeout_rate', 0):.1%}")
    if o.get("expectancy") is not None:
        lines.append(f"NET expectancy: {o['expectancy']:.3f} R | win-rate CI: {o.get('win_rate_ci')}")
        lines.append(f"Profit factor: {o.get('profit_factor')}")
    lines.append("")
    lines.append("Breakdowns (SECONDARY/exploratory — UNCORRECTED, multiple-testing NOT yet applied):")
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


# ---------------------------------------------------------------------------
# Task 7 — CLI/@register entrypoints
# ---------------------------------------------------------------------------

@register("edge_report")
def _routine_run(client=None, alert=None, cfg=None):
    """Scheduler-facing wrapper. Runs main() and returns a RoutineResult."""
    from scripts.routines._base import RoutineResult, write_report
    report_text = main()
    report_path = "reports/edge_report.md"
    write_report(report_path, report_text)
    return RoutineResult(
        name="edge_report",
        ok=True,
        breaches=[],
        report_path=report_path,
    )


def main(cfg_path="configs/config.phase2_1k.yaml"):
    import yaml
    from pathlib import Path
    from engine.signal_ledger import SignalLedger
    from engine.edge_metrics import aggregate
    cfg_all = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    from engine.signal_ledger import ledger_enabled
    if not ledger_enabled(cfg_all.get("signal_ledger")):
        return "signal_ledger disabled (config/env) — edge measurement OFF, no data being recorded"
    state_dir = cfg_all.get("operation", {}).get("state_dir", "./state")
    ledger = SignalLedger(Path(state_dir) / "signal_ledger.jsonl")
    return build_report(aggregate(ledger.all_signals()))


if __name__ == "__main__":
    print(main())
