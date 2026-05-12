from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"postgres(?:ql)?://[^\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9_]*(?:TOKEN|SECRET|API_KEY|PASSWORD)[A-Za-z0-9_]*\s*=\s*[^\s]+", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
]


def assert_no_secrets(text: str) -> None:
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            raise ValueError("Potential secret detected in Phase 0 output")
