"""Doc⇄code parity guards (D1): the CLAUDE.md parameter reference table must not
drift from the engine default / production config. The canonical value is 5
(engine smc.py, prod config, Pine port, PINE_SPEC) — only CLAUDE.md had drifted."""
import inspect
import re
from pathlib import Path

import yaml

from engine.smc import SMCEngine

ROOT = Path(__file__).parent.parent


def test_claude_md_swing_lookback_matches_engine_default():
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    m = re.search(r"Swing Lookback\*\*:\s*(\d+)", claude)
    assert m, "could not find the Swing Lookback bullet in CLAUDE.md"
    doc_lb = int(m.group(1))

    engine_default = inspect.signature(SMCEngine.__init__).parameters["swing_lb"].default

    cfg = yaml.safe_load(
        (ROOT / "configs" / "config.phase2_1k.yaml").read_text(encoding="utf-8")
    )
    prod_lb = cfg["structure"]["swing_lookback"]

    assert doc_lb == engine_default == prod_lb == 5, (
        f"swing_lookback drift: CLAUDE.md={doc_lb}, engine default={engine_default}, "
        f"prod config={prod_lb} (all must be 5)"
    )
