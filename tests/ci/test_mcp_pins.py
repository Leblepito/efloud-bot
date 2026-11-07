"""TEST-SEC-06: repo-scoped MCP servers stay pinned to an exact version.

An unpinned `npx -y <pkg>` runs whatever the registry serves at launch
(security audit 2026-11-06, T-20261107-09). Every npx/uvx package argument in
.mcp.json must carry an exact `@<version>` (no ranges, no `latest`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXACT = re.compile(r"^(@[\w.-]+/)?[\w.-]+@\d+(\.\d+)*$")


def _package_args():
    cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    for name, server in cfg.get("mcpServers", {}).items():
        if server.get("command") in ("npx", "uvx", "bunx", "pnpx"):
            for arg in server.get("args", []):
                if not arg.startswith("-"):
                    yield name, arg


def test_mcp_config_has_package_servers():
    assert list(_package_args()), "expected at least one npx/uvx MCP server"


def test_every_mcp_package_is_pinned_exactly():
    unpinned = [(n, a) for n, a in _package_args() if not EXACT.match(a)]
    assert unpinned == []


def test_pin_pattern_rejects_ranges_and_latest():
    for bad in ("@modelcontextprotocol/server-github", "pkg@latest", "pkg@^1.2.0", "pkg@~1"):
        assert not EXACT.match(bad)
    assert EXACT.match("@modelcontextprotocol/server-github@2025.4.8")
