"""Provenance snapshot — git SHA, pip freeze, host, timestamp.

Used by the backtest CLI to record exactly what code + dependencies produced
each run, so results are reproducible (or at least, divergence is explicable).

Grid mode passes `allow_dirty=False` to refuse running on a dirty git tree.
Single mode passes `allow_dirty=True` (default), warns + saves a diff patch.
"""
from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path


def _run(cmd: list[str]) -> str:
    """Run a command, return stdout stripped, or empty string on failure."""
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def capture_provenance(run_dir: Path | str, *, allow_dirty: bool = True) -> dict:
    """Capture provenance into `{run_dir}/provenance.json`.

    Args:
        run_dir: directory to write provenance.json (and provenance_diff.patch if dirty).
        allow_dirty: if False, raises RuntimeError when git tree is dirty.

    Returns: provenance dict (also saved to disk).
    """
    run_dir = Path(run_dir)

    sha = _run(["git", "rev-parse", "HEAD"])
    dirty_status = _run(["git", "status", "--porcelain"])
    is_dirty = bool(dirty_status)

    if is_dirty and not allow_dirty:
        raise RuntimeError(
            f"Refusing to run on dirty git tree:\n{dirty_status}\n"
            f"Commit or stash changes, or pass allow_dirty=True."
        )

    pip_freeze = _run([sys.executable, "-m", "pip", "freeze"])
    pip_sha = hashlib.sha256(pip_freeze.encode()).hexdigest()

    prov = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "git_dirty": is_dirty,
        "pip_freeze_sha256": pip_sha,
        "host": {
            "os": platform.system(),
            "python": sys.version.split()[0],
            "hostname": socket.gethostname(),
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "provenance.json").write_text(json.dumps(prov, indent=2))

    if is_dirty:
        diff = _run(["git", "diff", "HEAD"])
        if diff:
            (run_dir / "provenance_diff.patch").write_text(diff)

    return prov
