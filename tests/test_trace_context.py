"""trace_id contextvar helpers — set, get, scope."""
from __future__ import annotations

import asyncio

import pytest

from utils.logging import get_trace_id, new_trace_id, set_trace_id


def test_get_trace_id_returns_none_when_unset():
    # Fresh context; should be None
    assert get_trace_id() is None


def test_set_and_get_trace_id():
    set_trace_id("abc123")
    assert get_trace_id() == "abc123"
    set_trace_id(None)  # reset


def test_new_trace_id_returns_12_char_hex():
    tid = new_trace_id()
    assert isinstance(tid, str)
    assert len(tid) == 12
    assert all(c in "0123456789abcdef" for c in tid)


def test_new_trace_id_is_unique_across_calls():
    tids = {new_trace_id() for _ in range(100)}
    assert len(tids) == 100, "expected 100 unique trace_ids in 100 calls"


@pytest.mark.asyncio
async def test_trace_id_isolated_across_tasks():
    """Each asyncio Task gets its own contextvar copy."""
    set_trace_id("outer")

    async def inner_task(tid: str) -> str:
        set_trace_id(tid)
        await asyncio.sleep(0.001)
        return get_trace_id() or ""

    results = await asyncio.gather(
        inner_task("task1"),
        inner_task("task2"),
        inner_task("task3"),
    )
    assert results == ["task1", "task2", "task3"]
    # Outer context unchanged
    assert get_trace_id() == "outer"
    set_trace_id(None)  # cleanup
