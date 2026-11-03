"""Every desk script must run by path from the repo root, as the docs and cron lines show
(`python scripts/desk/<name>.py ...`), not only via `python -m`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "scripts" / "desk").glob("*.py"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_runs_by_path(script):
    out = subprocess.run([sys.executable, str(script.relative_to(ROOT)), "--help"], cwd=ROOT,
                         capture_output=True, text=True, check=False, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "usage:" in out.stdout
