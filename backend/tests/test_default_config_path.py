"""F3.6 regression: entrypoint default config paths must resolve to a real file.

`backend.bot_runner.CONFIG_PATH_DEFAULT` and `preflight.py`'s inline default both
pointed at ``configs/config.phase2_micro.yaml`` — a path that does NOT exist
(the file lives at ``configs/archive/config.phase2_micro.yaml``). Consequences
when ``EFLOUD_CONFIG_PATH`` is unset:
  * bot_runner.start() hits "config not found" and silently refuses to start;
  * preflight.py falls into ``except: pass`` and validates the live wallet
    against a bogus ``starting_balance=100`` band.

Fix: both default to the documented production config (``configs/config.phase2_1k.yaml``),
which exists and is what ``deploy/.env.production`` sets.
"""
from pathlib import Path

import backend.bot_runner as br

# Repo root = parent of the `backend/` package directory.
_ROOT = Path(br.__file__).resolve().parents[1]
_PHANTOM = "configs/config.phase2" + "_micro.yaml"  # split: archive path must not false-match


def test_bot_runner_default_config_exists():
    assert (_ROOT / br.CONFIG_PATH_DEFAULT).exists(), (
        f"CONFIG_PATH_DEFAULT={br.CONFIG_PATH_DEFAULT!r} does not resolve to a file"
    )


def test_entrypoint_defaults_do_not_reference_phantom_micro_path():
    for rel in ("backend/bot_runner.py", "preflight.py"):
        text = (_ROOT / rel).read_text(encoding="utf-8")
        assert _PHANTOM not in text, (
            f"{rel} still references the non-existent default config path {_PHANTOM!r}"
        )
