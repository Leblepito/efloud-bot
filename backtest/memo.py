"""Backtest-only memoization of per-frame analysis (backlog item 12: backtest speed).

Every 15m cycle re-analyzes the HTF/daily frames although they change only every
16-96 cycles; the orchestrator and signals analyze the same HTF frame three
times per cycle. These analyses are pure functions of (frame, arguments), so an
identical frame gives an identical result.

Safety of a hit:
- exact match only: same arguments (==) and ``DataFrame.equals`` on the frame
  (values, index, columns, dtypes) — no hashing, no time-based key;
- the result is stored pickled and every hit unpickles a fresh object graph
  (a deep copy, ~10x cheaper than copy.deepcopy here), so a caller that
  mutates a result cannot leak state into a later cycle.

Live code is untouched: ``memoized_analysis()`` patches the functions only for
the duration of a backtest run and restores them afterwards.
"""
from __future__ import annotations

import pickle
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Callable

import pandas as pd

_MAX_ENTRIES = 64
_SEEN = object()  # placeholder: frame seen once, result not kept yet  # portfolio: 10 symbols x (HTF + daily + LuxAlgo HTF) fits


class FrameMemo:
    """Wrap ``fn(df, *args)``; reuse the result of an identical earlier call."""

    def __init__(self, fn: Callable[..., Any], max_entries: int = _MAX_ENTRIES):
        self.fn = fn
        self.max_entries = max_entries
        self._cache: "OrderedDict[tuple, list]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(df: pd.DataFrame) -> tuple:
        if len(df) == 0:
            return (0, None, None)
        return (len(df), df.index[0], df.index[-1])

    def __call__(self, df: pd.DataFrame, *args, **kwargs):
        key = self._key(df)
        for cached_df, c_args, c_kwargs, blob in self._cache.get(key, ()):
            if c_args == args and c_kwargs == kwargs and cached_df.equals(df):
                self.hits += 1
                self._cache.move_to_end(key)
                return pickle.loads(blob)
        self.misses += 1
        result = self.fn(df, *args, **kwargs)
        bucket = self._cache.setdefault(key, [])
        bucket.append((df.copy(), args, kwargs, pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)))
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
        return result


@contextmanager
def memoized_analysis(orch):
    """Memoize ``orch.smc.analyze`` and ``engine.smc_v2.luxalgo.analyze`` for one run."""
    import engine.smc_v2.luxalgo as lux

    smc = orch.smc
    had_instance_attr = "analyze" in vars(smc)
    original_smc = smc.analyze
    original_lux = lux.analyze
    smc.analyze = FrameMemo(original_smc)
    lux.analyze = FrameMemo(original_lux)
    try:
        yield
    finally:
        lux.analyze = original_lux
        if had_instance_attr:
            smc.analyze = original_smc
        else:
            del smc.analyze
