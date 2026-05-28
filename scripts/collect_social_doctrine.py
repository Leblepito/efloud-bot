"""Collect social feeds, extract doctrine, append to local archive.

Research-only collection job. Calls ``fetch_social_feeds()``, runs the
deterministic doctrine parser per item, and appends each result through
``append_doctrine_snapshot`` so the snapshot store is idempotent and
deduplicated.

Live config, ``.env`` and the production compose file are off-limits as
archive targets; the script refuses any path whose basename matches a
production-control file (per docs/runbooks/social-research-promotion.md
"Forbidden shortcuts").

Usage:
    python -m scripts.collect_social_doctrine
    python -m scripts.collect_social_doctrine --archive state/social_doctrine.jsonl
    python -m scripts.collect_social_doctrine --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

from backend.social.archive import (
    _dedup_key,
    append_doctrine_snapshot,
    content_hash,
    load_doctrine_snapshots,
)
from backend.social.doctrine import extract_doctrine
from backend.social.feeds import fetch_social_feeds

log = logging.getLogger("efloud.scripts.collect_social_doctrine")

DEFAULT_ARCHIVE = Path("state/social_doctrine.jsonl")
PROTECTED_NAMES = {
    "config.yaml",
    "config.phase2_1k.yaml",
    "docker-compose.prod.yml",
    ".env",
}


def _flatten_feed(feed: dict[str, list[dict[str, Any]]]) -> Iterable[dict[str, Any]]:
    for bucket in ("telegram", "twitter"):
        for item in feed.get(bucket, []) or []:
            if not isinstance(item, dict):
                continue
            yield item


def _refuse_protected(archive_path: Path) -> None:
    if archive_path.name in PROTECTED_NAMES:
        raise ValueError(
            f"Refusing to use production-control file as doctrine archive: {archive_path}"
        )


def run(
    *,
    archive_path: Path | str = DEFAULT_ARCHIVE,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch feeds, extract doctrine, persist archive snapshots.

    Returns a summary dict with ``written``, ``skipped``, ``would_write``,
    ``feed_count`` keys.
    """
    archive_path = Path(archive_path)
    _refuse_protected(archive_path)

    feed = asyncio.run(fetch_social_feeds())
    items = list(_flatten_feed(feed))

    summary: dict[str, Any] = {
        "archive": str(archive_path),
        "feed_count": len(items),
        "written": 0,
        "skipped": 0,
        "would_write": 0,
        "dry_run": dry_run,
    }

    if dry_run:
        existing_keys = {
            row.get("dedup_key") for row in load_doctrine_snapshots(archive_path)
        }
        for item in items:
            digest = content_hash(str(item.get("content", "")))
            dedup_key = _dedup_key(item, digest)
            if dedup_key in existing_keys:
                summary["skipped"] += 1
            else:
                summary["would_write"] += 1
                existing_keys.add(dedup_key)
        return summary

    for item in items:
        doctrine = extract_doctrine(item)
        result = append_doctrine_snapshot(archive_path, item, doctrine)
        if result.get("written"):
            summary["written"] += 1
        else:
            summary["skipped"] += 1
    return summary


def _format_summary(summary: dict[str, Any]) -> str:
    return json.dumps(summary, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="collect_social_doctrine",
        description="Fetch social feeds and persist deterministic doctrine snapshots.",
    )
    parser.add_argument(
        "--archive",
        default=str(DEFAULT_ARCHIVE),
        help="Path to JSONL archive (default: state/social_doctrine.jsonl).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report what would be written, but do not touch the archive.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable INFO-level logging."
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        summary = run(archive_path=Path(args.archive), dry_run=args.dry_run)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(_format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
