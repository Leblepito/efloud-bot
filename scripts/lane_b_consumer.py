"""Lane B consumer harness — Phase 4a (PR #11).

Reads Lane A `content_job` JSONL (one event per line, written by
``engine/content_jobs.py``), dispatches each *unprocessed* event to an injected
per-event ``processor`` (the real TradingView screenshot + Gemini analysis runs
as a **Manus task** in production; this harness only orchestrates), enforces a
daily + per-batch budget, writes the analysis artifact to a local-fallback
directory, and persists an idempotent processed-set so re-runs never
double-process an event.

**Draft-only:** the harness never posts anything anywhere (Lane E owns
publishing). It never touches trade execution.

Spec: ``docs/superpowers/specs/2026-06-04-lane-b-screenshot-design.md``
  §4 flow · §6 failure modes · §7 budget ($5/day = 300 events binding; 100/batch)
  ``docs/superpowers/specs/2026-06-04-content-jobs-consumer-design.md`` §5 consumer.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("efloud.lane_b")

# §7 budget. $5/day at ~$0.012–0.02/event ≈ 300 events; 100 per batch run.
DEFAULT_DAILY_CAP = 300
DEFAULT_BATCH_CAP = 100

Processor = Callable[[dict], dict]
Notifier = Callable[[str], None]


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class LaneBConsumer:
    """Pull-based, idempotent, budgeted consumer for Lane A content jobs.

    ``processor(event) -> analysis_dict`` does the actual screenshot + analysis
    (Manus task in prod) and returns the §3.2 analysis JSON. It may raise; a
    raising event is counted as failed and is **not** marked processed, so the
    next run retries it.
    """

    def __init__(
        self,
        *,
        jobs_path,
        state_path,
        artifacts_path,
        processor: Processor,
        daily_cap: int = DEFAULT_DAILY_CAP,
        batch_cap: int = DEFAULT_BATCH_CAP,
        notifier: Optional[Notifier] = None,
    ):
        self.jobs_path = Path(jobs_path)
        self.state_path = Path(state_path)
        self.artifacts_path = Path(artifacts_path)
        self.processor = processor
        self.daily_cap = int(daily_cap)
        self.batch_cap = int(batch_cap)
        self.notifier = notifier

    # ── state (idempotent processed-set + per-day attempt counter) ───────────
    @property
    def _state_file(self) -> Path:
        return self.state_path / "lane_b_state.json"

    def _load_state(self) -> dict:
        f = self._state_file
        if not f.exists():
            return {"processed": [], "daily": {}}
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("lane_b_state_load_failed err=%s", e)
            return {"processed": [], "daily": {}}
        if not isinstance(data, dict):
            return {"processed": [], "daily": {}}
        data.setdefault("processed", [])
        data.setdefault("daily", {})
        return data

    def _save_state(self, state: dict) -> None:
        self.state_path.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self._state_file) + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._state_file)  # atomic rename

    # ── read Lane A JSONL ────────────────────────────────────────────────────
    def read_events(self, date: str) -> tuple[list[dict], int]:
        """Return ``(events, malformed_count)`` for the day's JSONL file.

        Blank lines are ignored; corrupt lines and non-dict / no-``event_id``
        rows are skipped defensively (§6) and counted as malformed.
        """
        f = self.jobs_path / f"{date}.jsonl"
        if not f.exists():
            return [], 0
        events: list[dict] = []
        malformed = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                log.warning("lane_b_malformed_line date=%s", date)
                continue
            if not isinstance(ev, dict) or "event_id" not in ev:
                malformed += 1
                continue
            events.append(ev)
        return events, malformed

    # ── artifact (local fallback, §6.1) ──────────────────────────────────────
    def _write_artifact(self, date: str, event_id: str, analysis: dict) -> Path:
        out_dir = self.artifacts_path / "analysis" / date
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{event_id}.json"
        out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    # ── orchestrate one batch ────────────────────────────────────────────────
    def run_batch(self, date: Optional[str] = None) -> dict:
        date = date or _utc_today()
        events, malformed = self.read_events(date)
        state = self._load_state()
        processed: set[str] = set(state["processed"])
        daily_count = int(state["daily"].get(date, 0))

        eligible = [e for e in events if e["event_id"] not in processed]
        skipped = len(events) - len(eligible)

        remaining_daily = max(0, self.daily_cap - daily_count)
        allowed = min(self.batch_cap, remaining_daily, len(eligible))
        # Binding daily cap forced us to leave eligible work undone → alert (§7).
        budget_exceeded = len(eligible) > remaining_daily

        succeeded = failed = 0
        cost = 0.0
        for ev in eligible[:allowed]:
            eid = ev["event_id"]
            daily_count += 1  # every attempt incurs cost → counts toward budget
            try:
                analysis = self.processor(ev)
            except Exception as e:  # §6.3/§6.4 — failure is not terminal; retry next run
                failed += 1
                log.warning("lane_b_event_failed event_id=%s err=%s", eid, e)
                continue
            self._write_artifact(date, eid, analysis)
            processed.add(eid)
            try:
                cost += float(analysis.get("cost_usd", 0) or 0)
            except (TypeError, ValueError):
                pass
            succeeded += 1

        state["processed"] = sorted(processed)
        state["daily"][date] = daily_count
        self._save_state(state)

        summary = {
            "date": date,
            "total": len(events),
            "eligible": len(eligible),
            "attempted": succeeded + failed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "deferred": len(eligible) - allowed,
            "malformed": malformed,
            "cost_usd": round(cost, 6),
            "daily_count": daily_count,
            "budget_remaining": max(0, self.daily_cap - daily_count),
            "budget_exceeded": budget_exceeded,
        }
        self._notify(summary)
        return summary

    def _notify(self, s: dict) -> None:
        if self.notifier is None:
            return
        msg = (
            f"[Lane B] {s['date']}: {s['succeeded']} ok, {s['failed']} fail, "
            f"{s['skipped']} skip, {s['deferred']} deferred, "
            f"${s['cost_usd']:.3f} (budget {s['budget_remaining']} left)"
        )
        if s["budget_exceeded"]:
            msg += " ⚠️ DAILY BUDGET CAP"
        try:
            self.notifier(msg)
        except Exception as e:  # a broken notifier must never fail the batch
            log.warning("lane_b_notify_failed err=%s", e)


# ── processors ───────────────────────────────────────────────────────────────

def _chart_url(symbol: Optional[str], timeframe: Optional[str]) -> str:
    """TradingView chart URL for a Binance perp (§4)."""
    sym = (symbol or "").replace("/", "")
    return (
        f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P"
        f"&interval={timeframe}"
    )


def _dry_run_processor(event: dict) -> dict:
    """Offline stub processor — no screenshot, no Gemini, no network, no cost.

    Exercises the whole harness path (artifact write + processed-set) so the
    cron wiring can be validated before the Manus connector is live (§6/§7
    blocker: Drive auth + Manus key). Records the intended chart URL only.
    """
    sig = event.get("signal", {}) or {}
    sym = sig.get("symbol")
    return {
        "event_id": event.get("event_id"),
        "symbol": sym,
        "timeframe": sig.get("timeframe"),
        "chart_url": _chart_url(sym, sig.get("timeframe")),
        "model": "dry-run",
        "analysis": {"structure": None, "confidence": "low",
                     "summary": "dry-run: screenshot/analysis skipped"},
        "cost_usd": 0.0,
        "dry_run": True,
    }


def _build_manus_processor() -> Processor:  # pragma: no cover - external, wired later
    """The live processor POSTs a Manus task (Playwright screenshot + Gemini).

    Not wired in PR #11 — it needs a Manus API key + Drive auth (§6/§7 blocker).
    Run with ``--dry-run`` (or inject a ``processor``) until it lands.
    """
    raise RuntimeError(
        "Lane B Manus processor not configured (needs MANUS_API_KEY + Drive auth). "
        "Run with --dry-run or inject a processor."
    )


def main(argv: Optional[list[str]] = None, *, processor: Optional[Processor] = None,
         notifier: Optional[Notifier] = None) -> dict:
    """Cron entry (§10.2). Reads a day's content_job JSONL and runs one batch."""
    import argparse
    import os

    ap = argparse.ArgumentParser(description="Lane B consumer — Lane A jobs → analysis drafts")
    ap.add_argument("--jobs", default=os.environ.get("EFLOUD_CONTENT_JOBS_PATH", "/app/data/content_jobs"))
    ap.add_argument("--state", default=os.environ.get("EFLOUD_LANE_B_STATE", "state/lane_b"))
    ap.add_argument("--artifacts", default=os.environ.get("EFLOUD_LANE_B_ARTIFACTS", "/tmp/lane-b"))
    ap.add_argument("--date", default=None, help="UTC date YYYY-MM-DD (default: today)")
    ap.add_argument("--daily-cap", type=int, default=DEFAULT_DAILY_CAP)
    ap.add_argument("--batch-cap", type=int, default=DEFAULT_BATCH_CAP)
    ap.add_argument("--dry-run", action="store_true", help="offline stub processor (no Manus/Gemini)")
    args = ap.parse_args(argv)

    proc = processor or (_dry_run_processor if args.dry_run else _build_manus_processor())
    consumer = LaneBConsumer(
        jobs_path=args.jobs, state_path=args.state, artifacts_path=args.artifacts,
        processor=proc, daily_cap=args.daily_cap, batch_cap=args.batch_cap, notifier=notifier,
    )
    summary = consumer.run_batch(date=args.date)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


__all__ = ["LaneBConsumer", "DEFAULT_DAILY_CAP", "DEFAULT_BATCH_CAP", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
