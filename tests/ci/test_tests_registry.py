"""TESTS.md evidence pointers must resolve (T-20261107-13).

Every backticked `path` or `path::node[::node]` in TESTS.md that points into the
repo must exist, and each node name must appear in that file. A renamed or
deleted test then fails CI instead of silently orphaning a TEST-ID.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = re.compile(r"`((?:tests|backend|u2algo-site|frontend|scripts|docs|collab)/[^`\s]+?)`")


def _refs():
    text = (ROOT / "TESTS.md").read_text(encoding="utf-8")
    for raw in REF.findall(text):
        path, *nodes = raw.split("::")
        if "*" in path or path.endswith("/"):
            continue  # globs/dirs in the asset map
        yield raw, path, nodes


def test_registry_has_evidence_refs():
    assert len(list(_refs())) > 30


def test_every_evidence_ref_resolves():
    broken = []
    for raw, path, nodes in _refs():
        f = ROOT / path
        if not f.is_file():
            broken.append(f"missing file: {raw}")
            continue
        src = f.read_text(encoding="utf-8")
        for node in nodes:
            if not re.search(rf"\b(def|class)\s+{re.escape(node)}\b", src):
                broken.append(f"missing node: {raw}")
    assert broken == []


def test_test_ids_are_unique():
    text = (ROOT / "TESTS.md").read_text(encoding="utf-8")
    ids = re.findall(r"^\| (TEST-[A-Z0-9]+-[A-Z0-9-]+) \|", text, flags=re.MULTILINE)
    assert len(ids) == len(set(ids)) and len(ids) > 40
