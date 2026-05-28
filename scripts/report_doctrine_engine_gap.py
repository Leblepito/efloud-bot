"""Doctrine ↔ engine gap report.

Reads social doctrine snapshots from ``state/social_doctrine.jsonl``,
aggregates the tags Efloud's public posts repeatedly use, and checks
which SMC v2 engine modules currently implement them. Writes the
result as a markdown report under ``reports/social_research/``.

Research-only. The script never edits engine code or live config. Gaps
are surfaced as candidate tasks, never as runtime behaviour changes.
See docs/runbooks/social-research-promotion.md Gate 4.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# tag -> expected engine module (relative to repo root)
TAG_TO_MODULE: dict[str, str] = {
    # zones
    "FVG": "engine/smc_v2/zones.py",
    "OTE": "engine/smc_v2/zones.py",
    "Order Block": "engine/smc_v2/zones.py",
    # market structure / swing
    "MSB": "engine/smc_v2/swing_anchor.py",
    "BOS": "engine/smc_v2/swing_anchor.py",
    "CHOCH": "engine/smc_v2/swing_anchor.py",
    "HH": "engine/smc_v2/swing_anchor.py",
    "HL": "engine/smc_v2/swing_anchor.py",
    "LH": "engine/smc_v2/swing_anchor.py",
    "LL": "engine/smc_v2/swing_anchor.py",
    # liquidity
    "liquidity_sweep": "engine/smc_v2/liquidity_pools.py",
    "liquidity_target": "engine/smc_v2/liquidity_pools.py",
    # risk / lifecycle (live outside smc_v2)
    "risk_management": "engine/safety/__init__.py",
    "TP1": "engine/lifecycle.py",
    "BE": "engine/lifecycle.py",
}

DOCTRINE_BUCKETS = ("zones", "structure_terms", "liquidity_terms", "risk_terms")


def collect_tag_usage(archive_path: Path | str) -> Counter[str]:
    """Aggregate tag counts across every snapshot in the JSONL archive."""
    archive_path = Path(archive_path)
    counts: Counter[str] = Counter()
    if not archive_path.exists():
        return counts
    with archive_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            doctrine = row.get("doctrine") or {}
            for bucket in DOCTRINE_BUCKETS:
                for tag in doctrine.get(bucket, []) or []:
                    counts[str(tag)] += 1
    return counts


def classify_tags(usage: dict[str, int], *, repo_root: Path | str) -> list[dict[str, Any]]:
    """Map each used tag to its expected engine module and check existence."""
    repo_root = Path(repo_root)
    out: list[dict[str, Any]] = []
    for tag, count in sorted(usage.items(), key=lambda kv: (-kv[1], kv[0])):
        module = TAG_TO_MODULE.get(tag)
        if module is None:
            out.append({"tag": tag, "count": count, "status": "unmapped", "module": None})
            continue
        exists = (repo_root / module).exists()
        out.append(
            {
                "tag": tag,
                "count": count,
                "status": "implemented" if exists else "missing",
                "module": module,
            }
        )
    return out


def render_markdown(classified: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# Doctrine ↔ Engine Gap Report")
    lines.append("")
    lines.append(
        "Research only — this report does not change engine behaviour or live "
        "config. It is consumed by Gate 4 of "
        "`docs/runbooks/social-research-promotion.md`."
    )
    lines.append("")

    if not classified:
        lines.append("No doctrine snapshots found in the archive.")
        lines.append("")
        return "\n".join(lines)

    impl = [row for row in classified if row["status"] == "implemented"]
    missing = [row for row in classified if row["status"] == "missing"]
    unmapped = [row for row in classified if row["status"] == "unmapped"]

    def _table(rows: list[dict[str, Any]]) -> list[str]:
        out = ["| Tag | Count | Module |", "|-----|-------|--------|"]
        for row in rows:
            module = row["module"] or "—"
            out.append(f"| {row['tag']} | {row['count']} | `{module}` |")
        return out

    lines.append("## Implemented")
    lines.append("")
    if impl:
        lines.extend(_table(impl))
    else:
        lines.append("_None._")
    lines.append("")

    lines.append("## Missing modules")
    lines.append("")
    if missing:
        lines.append(
            "These tags appear in social posts but the expected engine "
            "module does not exist. They become candidate tasks, not live "
            "behaviour."
        )
        lines.append("")
        lines.extend(_table(missing))
    else:
        lines.append("_None._")
    lines.append("")

    lines.append("## Unmapped tags")
    lines.append("")
    if unmapped:
        lines.append(
            "These tags are observed in doctrine but have no mapping in "
            "`scripts/report_doctrine_engine_gap.py:TAG_TO_MODULE`. Either "
            "extend the mapping or treat them as out of scope for the "
            "engine."
        )
        lines.append("")
        lines.extend(_table(unmapped))
    else:
        lines.append("_None._")
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="report_doctrine_engine_gap",
        description="Compare social doctrine tags to SMC v2 engine modules.",
    )
    parser.add_argument(
        "--archive",
        default="state/social_doctrine.jsonl",
        help="Path to JSONL doctrine archive.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root used to resolve engine module paths.",
    )
    parser.add_argument(
        "--out",
        default="reports/social_research/latest_gap_report.md",
        help="Markdown report output path.",
    )

    args = parser.parse_args(argv)

    archive_path = Path(args.archive)
    if not archive_path.exists():
        print(f"ERROR: archive not found: {archive_path}", file=sys.stderr)
        return 2

    usage = collect_tag_usage(archive_path)
    classified = classify_tags(usage, repo_root=args.repo_root)
    body = render_markdown(classified)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    print(f"Wrote gap report to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
