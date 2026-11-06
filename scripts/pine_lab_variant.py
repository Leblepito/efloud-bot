"""Write a temp copy of pine/efloud_lab.pine with layer defaults set for verification.

Never touches the repo source; only rewrites `input.bool` defaults of the show* layer
flags, `showHistory`, and (optionally) the `maxZonesPerSide` default.

usage: python scripts/pine_lab_variant.py OUT [--zones N] [--history] LAYER...
  LAYER in showObs showZones showLevels showBreakers showFvg showLiq showOte
  (layers not listed are set to false)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "pine" / "efloud_lab.pine"
LAYERS = ("showObs", "showZones", "showLevels", "showBreakers", "showFvg", "showLiq", "showOte")


def make_variant(src: str, layers: list[str], zones: int | None = None, history: bool = False) -> str:
    for name in LAYERS:
        val = "true" if name in layers else "false"
        src, n = re.subn(rf"^({name}\s*=\s*input\.bool\()(true|false)", rf"\g<1>{val}", src, flags=re.M)
        assert n == 1, name
    src, n = re.subn(r"^(showHistory\s*=\s*input\.bool\()(true|false)",
                     rf"\g<1>{'true' if history else 'false'}", src, flags=re.M)
    assert n == 1
    if zones is not None:
        src, n = re.subn(r"^(maxZonesPerSide\s*=\s*input\.int\()(\d+)", rf"\g<1>{zones}", src, flags=re.M)
        assert n == 1
    return src


def main(argv: list[str]) -> None:
    args = list(argv)
    out = args.pop(0)
    zones = None
    history = False
    if "--zones" in args:
        i = args.index("--zones")
        zones = int(args[i + 1])
        del args[i:i + 2]
    if "--history" in args:
        history = True
        args.remove("--history")
    text = make_variant(SRC.read_text(encoding="utf-8"), args, zones, history)
    Path(out).write_text(text, encoding="utf-8")
    print("wrote", out, "layers ON =", sorted(args) or "none", "| zones =", zones, "| history =", history)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    main(sys.argv[1:])
