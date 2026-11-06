"""scripts/pine_lab_variant.py flips only the requested layer defaults."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pine_lab_variant.py"
SRC = ROOT / "pine" / "efloud_lab.pine"
LAYERS = ("showObs", "showZones", "showLevels", "showBreakers", "showFvg", "showLiq", "showOte")


def _run(out: Path, *args: str) -> list[str]:
    subprocess.run([sys.executable, "-I", str(SCRIPT), str(out), *args], check=True, capture_output=True)
    return out.read_text(encoding="utf-8").splitlines()


def _default(lines: list[str], name: str, pat: str) -> str:
    hits = [m.group(1) for ln in lines if (m := re.match(rf"^{name}\s*=\s*input\.(?:bool|int)\(({pat})", ln))]
    assert len(hits) == 1, name
    return hits[0]


def test_variant_flips_requested_defaults(tmp_path):
    out = _run(tmp_path / "v.pine", "--zones", "200", "--history", "showObs", "showOte")
    for name in LAYERS:
        assert _default(out, name, "true|false") == ("true" if name in ("showObs", "showOte") else "false")
    assert _default(out, "showHistory", "true|false") == "true"
    assert _default(out, "maxZonesPerSide", r"\d+") == "200"


def test_variant_changes_only_target_lines(tmp_path):
    base = SRC.read_text(encoding="utf-8").splitlines()
    out = _run(tmp_path / "v.pine", "--zones", "200", "showFvg")
    assert len(out) == len(base)
    changed = {re.match(r"^(\w+)", b).group(1) for b, o in zip(base, out) if b != o}
    assert changed <= set(LAYERS) | {"showHistory", "maxZonesPerSide"}
    assert all(b == o for b, o in zip(base, out) if not re.match(r"^(%s)\b" % "|".join((*LAYERS, "showHistory", "maxZonesPerSide")), b))
