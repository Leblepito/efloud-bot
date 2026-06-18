"""M6 template compliance verifier.

Loads templates.yaml, fills each template's sample values, and runs the REAL
repo gate (scripts.content_compliance.find_violations) on every rendered EN/TR
example. Prints a per-template result table and exits non-zero if any example
trips a violation. Also reports X 280-char budget (warn only, not a gate).

Run from anywhere — the repo root is derived from this file's location
(scripts/content_templates/ -> repo root is two parents up), so the
`scripts.content_compliance` import resolves on Windows and on the VPS alike.
Override with the EFLOUD_REPO env var if the layout ever changes:
    python scripts/content_templates/verify_compliance.py
    EFLOUD_REPO=/opt/efloud-bot python scripts/content_templates/verify_compliance.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

try:  # Windows console defaults to cp1252; our notes use → and emoji.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# scripts/content_templates/verify_compliance.py -> parents[2] == repo root.
REPO = os.environ.get("EFLOUD_REPO") or str(Path(__file__).resolve().parents[2])
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.content_compliance import find_violations  # noqa: E402

YAML_PATH = Path(__file__).with_name("templates.yaml")
X_LIMIT = 280


def render(spec: dict) -> tuple[str, list[int]]:
    """Return (full_text_for_gate, [per-tweet char counts])."""
    sample = spec.get("sample", {}) or {}
    if spec.get("format") == "thread":
        tweets = [t.format(**sample) for t in spec.get("tweets", [])]
        return "\n".join(tweets), [len(t) for t in tweets]
    body = (spec.get("body") or "").format(**sample)
    return body, [len(body)]


def main() -> int:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    templates = data["templates"]
    failures = 0
    checked = 0

    print(f"{'template':<24} {'lang':<5} {'gate':<6} {'chars':<14} status")
    print("-" * 70)
    for tpl in templates:
        tid = tpl["id"]
        for lang, spec in tpl["langs"].items():
            body = spec.get("body")
            tweets = spec.get("tweets")
            is_stub = (body == "TODO") or (tweets == ["TODO"])
            if is_stub:
                print(f"{tid:<24} {lang:<5} {'-':<6} {'(stub)':<14} TODO RU/KZ")
                continue
            checked += 1
            text, lens = render(spec)
            v = find_violations(text)
            over = [n for n in lens if n > X_LIMIT]
            gate = "CLEAN" if not v else "FAIL"
            chars = ",".join(str(n) for n in lens)
            note = ""
            if v:
                failures += 1
                note = "VIOLATIONS: " + ", ".join(v)
            elif over:
                note = f"over-280 ({over}) → use thread"
            else:
                note = "ok"
            print(f"{tid:<24} {lang:<5} {gate:<6} {chars:<14} {note}")

    # Negative control: prove the gate is live (these MUST trip it).
    print()
    print("negative control (gate MUST flag these):")
    controls = [
        ("banned phrase", "Garantili getiri sunuyoruz"),
        ("absolute money", "Bugün 250$ kâr kilitledik"),
        ("perf-% (TR)", "%80 kazanç oranı"),
        ("perf-% (EN)", "73.2% win rate"),
    ]
    control_ok = True
    for label, txt in controls:
        v = find_violations(txt)
        flagged = bool(v)
        control_ok = control_ok and flagged
        print(f"  [{'PASS' if flagged else 'FAIL'}] {label:<16} -> {v}")

    print("-" * 70)
    print(f"checked={checked}  clean={checked - failures}  failed={failures}")
    if not control_ok:
        print("RESULT: gate appears INERT (negative control did not fire) — abort.")
        return 1
    if failures:
        print("RESULT: NOT COMPLIANT — fix the FAIL rows above.")
        return 1
    print("RESULT: ALL TEMPLATES PASS find_violations == [] (0 violations).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
