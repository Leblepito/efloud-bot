"""Lane E publisher protocol — Phase 4b (PR #13c).

A publisher is anything with a ``name``, an ``enabled`` flag (default OFF in
prod), and a ``publish(envelope) -> PublishResult`` method. Real platform
adapters (Telegram, X, IG, LinkedIn, YouTube) implement this; tests inject fakes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class PublishResult:
    platform: str
    ok: bool
    ref: Optional[str] = None       # platform post id on success
    error: Optional[str] = None     # message on failure


@runtime_checkable
class Publisher(Protocol):
    name: str
    enabled: bool

    def publish(self, envelope: dict) -> PublishResult: ...


__all__ = ["Publisher", "PublishResult"]
