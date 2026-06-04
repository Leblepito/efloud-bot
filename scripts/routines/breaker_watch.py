from scripts.routines.runner import register
from scripts.routines._base import read_snapshot, write_snapshot, write_report, RoutineResult

def evaluate(prev, cur):
    prev_state = prev.get("state", "OPEN")
    cur_state = cur.get("state", "OPEN")

    breaches = []

    # State transitions
    if prev_state == "OPEN" and cur_state in ("HALTED", "TRIPPED"):
        breaches.append({
            "severity": "critical",
            "key": f"breaker_state:{cur_state}",
            "title": f"Circuit Breaker Tripped: {cur_state}",
            "body": f"State transitioned from {prev_state} to {cur_state}. Reason: {cur.get('reason', 'N/A')}"
        })
    elif prev_state in ("HALTED", "TRIPPED") and cur_state == "OPEN":
        breaches.append({
            "severity": "info",
            "key": f"breaker_state:{cur_state}",
            "title": f"Circuit Breaker Recovered: {cur_state}",
            "body": f"State transitioned from {prev_state} to {cur_state}."
        })

    # Generate report
    report_lines = [
        "# Circuit Breaker Watch Report",
        f"**Current State:** {cur_state}",
        f"**Reason:** {cur.get('reason', 'N/A')}",
        f"**Resume At:** {cur.get('resume_at', 'N/A')}",
        f"**Current Balance:** {cur.get('current_balance', 'N/A')}",
        f"**Peak Balance:** {cur.get('peak_balance', 'N/A')}",
    ]
    metrics = cur.get("metrics")
    if metrics:
        report_lines.append("\n### Metrics:")
        for k, v in metrics.items():
            report_lines.append(f"- **{k}:** {v}")

    report_text = "\n".join(report_lines)
    return report_text, breaches

@register("breaker_watch")
def run(client=None, alert=None, cfg=None):
    prev_path = "state/breaker_watch_snapshot.json"
    cur_path = "state/breaker.json"
    report_path = "reports/breaker_watch.md"

    prev = read_snapshot(prev_path)
    cur = read_snapshot(cur_path)

    # If breaker.json doesn't exist, default to OPEN state
    if not cur:
        cur = {"state": "OPEN", "reason": "", "current_balance": 0.0, "peak_balance": 0.0, "metrics": {}}

    report_text, breaches = evaluate(prev, cur)

    write_report(report_path, report_text)
    write_snapshot(prev_path, cur)

    return RoutineResult(
        name="breaker_watch",
        ok=True,
        breaches=breaches,
        report_path=report_path
    )
