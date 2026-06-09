"""Pipeline orchestrator + Lane F metrics — Phase 4b (PR #15).

Ties the offline draft pipeline together for one cron tick: Lane B → Lane C →
Lane D, chaining the artifact directories under a single work dir, then rolls up
per-stage metrics (Lane F) and the budget into one summary. Draft-only — the
approval → publish step is event-driven (Phase 5 poller + Lane E), kept separate.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lane_b_consumer import DEFAULT_BATCH_CAP, DEFAULT_DAILY_CAP, LaneBConsumer
from scripts.lane_c_copywriter import LaneCCopywriter
from scripts.lane_d_visual import LaneDVisual

log = logging.getLogger("efloud.pipeline")


class PipelineOrchestrator:
    def __init__(self, *, jobs_path, work_dir, lane_b_processor,
                 notifier: Optional[Callable[[str], None]] = None,
                 daily_cap: int = DEFAULT_DAILY_CAP, batch_cap: int = DEFAULT_BATCH_CAP):
        self.jobs_path = Path(jobs_path)
        self.work_dir = Path(work_dir)
        self.processor = lane_b_processor
        self.notifier = notifier
        self.daily_cap = daily_cap
        self.batch_cap = batch_cap

    def run(self, date: str) -> dict:
        analysis_dir = self.work_dir / "analysis"
        copy_dir = self.work_dir / "copy"
        visual_dir = self.work_dir / "visual"
        state_dir = self.work_dir / "state"

        b = LaneBConsumer(
            jobs_path=self.jobs_path, state_path=state_dir, artifacts_path=self.work_dir,
            processor=self.processor, daily_cap=self.daily_cap, batch_cap=self.batch_cap,
        ).run_batch(date)
        c = LaneCCopywriter(analysis_dir=analysis_dir, out_dir=copy_dir).run(date)
        d = LaneDVisual(copy_dir=copy_dir, out_dir=visual_dir).run(date)

        metrics = {
            "date": date,
            "lane_b": b,
            "lane_c": c,
            "lane_d": d,
            "cost_usd": b.get("cost_usd", 0.0),
            "budget_remaining": b.get("budget_remaining"),
            "budget_exceeded": b.get("budget_exceeded", False),
        }
        self._notify(metrics)
        return metrics

    def _notify(self, m: dict) -> None:
        if self.notifier is None:
            return
        msg = (f"[Pipeline] {m['date']}: B {m['lane_b'].get('succeeded', 0)} → "
               f"C {m['lane_c'].get('generated', 0)} → D {m['lane_d'].get('generated', 0)} "
               f"| ${m['cost_usd']:.3f} (budget {m['budget_remaining']} left)")
        if m["budget_exceeded"]:
            msg += " ⚠️ BUDGET CAP"
        try:
            self.notifier(msg)
        except Exception as e:
            log.warning("pipeline_notify_failed err=%s", e)


def main(argv: Optional[list[str]] = None, *, processor=None) -> dict:
    """Cron entry: run the offline B→C→D pipeline for a date."""
    import argparse
    import os

    from scripts.lane_b_consumer import _dry_run_processor

    ap = argparse.ArgumentParser(description="Offline content pipeline orchestrator (B→C→D)")
    ap.add_argument("--jobs", default=os.environ.get("EFLOUD_CONTENT_JOBS_PATH", "/app/data/content_jobs"))
    ap.add_argument("--work", default=os.environ.get("EFLOUD_PIPELINE_WORK", "/tmp/efloud-pipeline"))
    ap.add_argument("--date", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    proc = processor or (_dry_run_processor if args.dry_run else None)
    if proc is None:
        raise SystemExit("no Lane B processor: pass --dry-run or wire a Manus processor")
    metrics = PipelineOrchestrator(jobs_path=args.jobs, work_dir=args.work,
                                   lane_b_processor=proc).run(date=args.date)
    print(json.dumps(metrics, ensure_ascii=False))
    return metrics


__all__ = ["PipelineOrchestrator", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
