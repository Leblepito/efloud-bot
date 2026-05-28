"""Read-only social research report builders for dashboard/API use."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.social.archive import load_doctrine_snapshots
from backend.social.hypotheses import generate_hypotheses
from backend.social.research_runs import (
    DEFAULT_REPORTS_ROOT,
    research_runs_payload,
)

DEFAULT_ARCHIVE_PATH = Path("state/social_doctrine.jsonl")


def build_social_research_snapshot(
    path: str | Path = DEFAULT_ARCHIVE_PATH,
    reports_root: str | Path = DEFAULT_REPORTS_ROOT,
) -> dict[str, Any]:
    rows = load_doctrine_snapshots(path)
    doctrine = [row.get("doctrine", {}) for row in rows if row.get("doctrine")]
    return {
        "archive_count": len(rows),
        "doctrine": doctrine,
        "hypotheses": generate_hypotheses(doctrine),
        "research_runs": research_runs_payload(reports_root),
        "research_only": True,
    }
