"""Doc⇄code parity guards (D1): the v1 parameter reference must not drift from
the engine default / production config. The reference lives in the
`pine/PINE_SPEC.md` appendix "Ek V1 — v1 referansı" (moved out of CLAUDE.md).
The canonical value is 5 (engine smc.py, prod config, Pine port, PINE_SPEC)."""
import inspect
import re
from pathlib import Path

import yaml

from engine.smc import SMCEngine

ROOT = Path(__file__).parent.parent


def test_v1_reference_swing_lookback_matches_engine_default():
    spec = (ROOT / "pine" / "PINE_SPEC.md").read_text(encoding="utf-8")
    m = re.search(r"Swing Lookback\*\*:\s*(\d+)", spec)
    assert m, "could not find the Swing Lookback bullet in pine/PINE_SPEC.md (v1 reference)"
    doc_lb = int(m.group(1))
    engine_default = inspect.signature(SMCEngine.__init__).parameters["swing_lb"].default
    cfg = yaml.safe_load((ROOT / "configs" / "config.phase2_1k.yaml").read_text(encoding="utf-8"))
    prod_lb = cfg["structure"]["swing_lookback"]
    assert doc_lb == engine_default == prod_lb == 5, (
        f"swing_lookback drift: PINE_SPEC={doc_lb}, engine default={engine_default}, prod config={prod_lb}"
    )
