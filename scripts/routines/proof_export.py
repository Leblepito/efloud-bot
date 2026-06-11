"""T-012 (P-003 W1): Public proof snapshot export.

Reads the closed-trade journal (state/trade_journal.jsonl) and produces a
privacy-safe, WHITELIST-ONLY snapshot (state/proof_snapshot.json) intended
for static publication on u2algo-site. The bot API is never exposed —
publication is a static-file copy gated by operator approval (G-P3-B4).

Privacy model (G-P3-1, UR-003):
  * Equity curve is NORMALIZED to an operator-provided baseline
    (state/proof_baseline.json, e.g. {"baseline_equity_usdt": 2000.0}).
    The curve starts at 1.0; the baseline value itself NEVER appears in the
    snapshot, so real % drawdown is published without leaking account size.
  * Daily-close granularity, CLOSED trades only — more frequent/granular
    output would become a de-facto real-time signal feed (P-003 §2b guard).
  * A runtime whitelist guard rejects any snapshot containing keys outside
    the schema or forbidden substrings (usdt/balance/baseline/...).

Side effect: each run appends one healthz sample to state/uptime_samples.jsonl
(service_uptime vs trading_active design — docs/runbooks/healthz-contract.md §3).
Sampling failures never fail the routine.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.routines.runner import register
from scripts.routines._base import RoutineResult

SCHEMA_VERSION = "1.0.0"

# ── Whitelist (G-P3-1) ───────────────────────────────────────────────────
ALLOWED_TOP_KEYS = frozenset({
    "schema_version", "generated_at", "period",
    "trade_count", "win_rate_pct", "profit_factor", "max_dd_pct",
    "equity_curve",
})
ALLOWED_PERIOD_KEYS = frozenset({"from", "to"})
ALLOWED_CURVE_KEYS = frozenset({"date", "equity_norm"})

# Defense-in-depth: no key anywhere in the snapshot may contain these.
FORBIDDEN_KEY_SUBSTRINGS = (
    "usdt", "balance", "baseline", "position", "size",
    "symbol", "price", "pnl", "leverage", "margin",
)

DEFAULT_PATHS = {
    "journal": "state/trade_journal.jsonl",
    "baseline": "state/proof_baseline.json",
    "out": "state/proof_snapshot.json",
    "uptime_samples": "state/uptime_samples.jsonl",
}


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_keys(item)


def assert_whitelist(snapshot: dict) -> None:
    """Raise ValueError if the snapshot violates the publication whitelist."""
    extra = set(snapshot.keys()) - ALLOWED_TOP_KEYS
    if extra:
        raise ValueError(f"proof snapshot: non-whitelisted top-level keys: {sorted(extra)}")
    period = snapshot.get("period", {})
    if set(period.keys()) - ALLOWED_PERIOD_KEYS:
        raise ValueError("proof snapshot: non-whitelisted period keys")
    for point in snapshot.get("equity_curve", []):
        if set(point.keys()) - ALLOWED_CURVE_KEYS:
            raise ValueError("proof snapshot: non-whitelisted equity_curve keys")
    for key in _iter_keys(snapshot):
        lk = str(key).lower()
        for bad in FORBIDDEN_KEY_SUBSTRINGS:
            if bad in lk:
                raise ValueError(f"proof snapshot: forbidden key substring '{bad}' in '{key}'")


# ── Inputs ───────────────────────────────────────────────────────────────

def load_closed_trades(journal_path: str | Path,
                       corrupt_sink: list | None = None) -> list[dict]:
    """Closed trades only (exit_timestamp set), sorted by exit time.

    A torn LAST line is tolerated by design (append-only journal snapshotted
    mid-write — see backup-restore runbook). A corrupt NON-terminal line is
    NOT normal: its line number is appended to corrupt_sink so the caller can
    warn the operator (published stats would silently skew otherwise).
    """
    p = Path(journal_path)
    if not p.exists():
        return []
    raw_lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    trades: list[dict] = []
    for idx, line in enumerate(raw_lines):
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            if corrupt_sink is not None and idx < len(raw_lines) - 1:
                corrupt_sink.append(idx + 1)
            continue
        if t.get("exit_timestamp"):
            trades.append(t)
    trades.sort(key=lambda t: t["exit_timestamp"])
    return trades


def load_baseline(baseline_path: str | Path) -> dict | None:
    """{"baseline_equity_usdt": float > 0, "since": optional "YYYY-MM-DD"}."""
    p = Path(baseline_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    eq = data.get("baseline_equity_usdt")
    if not isinstance(eq, (int, float)) or eq <= 0:
        return None
    return data


# ── Metrics ──────────────────────────────────────────────────────────────

def _is_win(trade: dict) -> bool:
    if "is_winner" in trade:
        return bool(trade["is_winner"])
    return float(trade.get("realized_pnl", 0) or 0) > 0


def build_daily_curve(trades: list[dict], baseline_equity: float,
                      since: str | None = None) -> list[dict]:
    """Daily-close normalized equity curve. Starts at 1.0; never exposes
    the baseline. Sparse: only days with at least one closed trade."""
    from datetime import timedelta

    daily_pnl: dict[str, float] = {}
    for t in trades:
        day = str(t["exit_timestamp"])[:10]
        if since and day < since:
            continue
        daily_pnl[day] = daily_pnl.get(day, 0.0) + float(t.get("realized_pnl", 0) or 0)

    days = sorted(daily_pnl)
    if since:
        start_date = since
    elif days:
        # Anchor one day BEFORE the first trade day so date-keyed chart
        # consumers (T-014) never see two points on the same date.
        first = datetime.strptime(days[0], "%Y-%m-%d")
        start_date = (first - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    curve = [{"date": start_date, "equity_norm": 1.0}]
    cum = 0.0
    for day in days:
        cum += daily_pnl[day]
        curve.append({"date": day, "equity_norm": round((baseline_equity + cum) / baseline_equity, 4)})
    return curve


def max_drawdown_pct(curve: list[dict]) -> float:
    """Peak-relative max drawdown (%) over the normalized curve. Because
    normalization is linear, this equals the true account drawdown."""
    peak = float("-inf")
    max_dd = 0.0
    for point in curve:
        val = float(point["equity_norm"])
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 2)


def build_snapshot(trades: list[dict], baseline: dict,
                   now_iso: str | None = None) -> dict:
    since = baseline.get("since")
    if since:
        trades = [t for t in trades if str(t["exit_timestamp"])[:10] >= since]

    wins = [t for t in trades if _is_win(t)]
    losses = [t for t in trades if not _is_win(t)]
    gross_win = sum(float(t.get("realized_pnl", 0) or 0) for t in wins)
    gross_loss = sum(float(t.get("realized_pnl", 0) or 0) for t in losses)

    curve = build_daily_curve(trades, float(baseline["baseline_equity_usdt"]), since)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso or datetime.now(timezone.utc).isoformat(),
        "period": {
            "from": curve[0]["date"],
            "to": curve[-1]["date"],
        },
        "trade_count": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "profit_factor": round(abs(gross_win / gross_loss), 2) if gross_loss != 0 else 0.0,
        "max_dd_pct": max_drawdown_pct(curve),
        "equity_curve": curve,
    }
    assert_whitelist(snapshot)
    return snapshot


# ── Healthz sampling side effect (healthz-contract.md §3) ────────────────

def sample_healthz(samples_path: str | Path, now_iso: str | None = None,
                   http_get=None) -> str:
    """Append one {ts, status} sample. status ∈ ok|suspended|unhealthy|unreachable.
    Best-effort: never raises."""
    status = "unreachable"
    try:
        if http_get is None:
            import httpx

            def http_get(url):  # pragma: no cover - exercised via injection in tests
                return httpx.get(url, timeout=5.0)

        base = os.environ.get("EFLOUD_API_BASE_URL", "http://localhost:8080")
        res = http_get(f"{base}/healthz")
        payload = res.json()
        status = str(payload.get("status", "unhealthy"))
        # Coerce into the healthz-contract.md §3 set so uptime_samples.jsonl
        # stays consumable by T-021 monitors.
        if status not in ("ok", "suspended", "unhealthy"):
            status = "unhealthy"
    except Exception:
        # Reachable-but-non-JSON (e.g. proxy HTML on 503) also lands here;
        # acceptable for a best-effort sampler.
        status = "unreachable"
    try:
        p = Path(samples_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        sample = {"ts": now_iso or datetime.now(timezone.utc).isoformat(), "status": status}
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample) + "\n")
    except Exception:
        pass
    return status


# ── Routine entrypoint ───────────────────────────────────────────────────

@register("proof_export")
def run(client=None, alert=None, cfg=None) -> RoutineResult:
    paths = dict(DEFAULT_PATHS)
    paths.update((cfg or {}).get("proof_export", {}))

    sample_healthz(paths["uptime_samples"])

    baseline = load_baseline(paths["baseline"])
    if baseline is None:
        return RoutineResult(
            name="proof_export",
            ok=False,
            breaches=[{
                "severity": "warning",
                "key": "proof_export_baseline_missing",
                "title": "proof_export: baseline yok",
                "body": f"{paths['baseline']} eksik/geçersiz — runbook'taki operatör "
                        f"adımıyla oluşturulmalı. Snapshot ÜRETİLMEDİ.",
            }],
        )

    corrupt: list = []
    trades = load_closed_trades(paths["journal"], corrupt_sink=corrupt)
    snapshot = build_snapshot(trades, baseline)

    out = Path(paths["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    os.replace(tmp, out)

    breaches = []
    if corrupt:
        breaches.append({
            "severity": "warning",
            "key": "proof_export_journal_corrupt",
            "title": "proof_export: journal'da bozuk ara satır",
            "body": f"{paths['journal']} satır(lar) {corrupt} decode edilemedi (son satır "
                    f"DEĞİL — torn-line toleransı dışında). Yayınlanan istatistikler eksik "
                    f"olabilir; journal bütünlüğünü kontrol edin.",
        })

    return RoutineResult(name="proof_export", ok=True, breaches=breaches,
                         report_path=str(out))
