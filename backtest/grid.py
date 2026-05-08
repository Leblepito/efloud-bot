"""Grid search over backtest configs with resume support.

`run_one_fn` contract:
    Signature: (cfg: dict) -> dict
    Must be picklable (top-level function, NO closures over local state).
    The cfg dict contains all overrides applied; the function is responsible
    for loading data and running the backtest. Return dict must be JSON-serializable
    and SHOULD include `config_hash` for traceability.

Multiprocessing logging:
    Each worker is initialized with `multiprocessing.get_logger()` configured
    with a NullHandler to prevent worker logs from leaking to parent stdout.
    Worker-specific debug logs (if needed) should be written to per-worker files
    inside the run_one_fn itself.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import product
from pathlib import Path
from typing import Callable, Iterable, Iterator


def _worker_init():
    """Per-worker logger setup — runs once at pool spawn."""
    logger = mp.get_logger()
    logger.setLevel(logging.WARNING)
    # NullHandler so worker logs don't leak to parent stdout
    logger.addHandler(logging.NullHandler())


def _set_dotted(d: dict, dotted_key: str, value) -> None:
    """Set d['a']['b'] = value when dotted_key='a.b'."""
    parts = dotted_key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def expand_grid(base_config: dict, grid: dict[str, list]) -> Iterator[dict]:
    """Expand a base config + dotted-key grid into the cartesian product of override configs."""
    keys = list(grid.keys())
    for combo in product(*(grid[k] for k in keys)):
        cfg = copy.deepcopy(base_config)
        for k, v in zip(keys, combo):
            _set_dotted(cfg, k, v)
        yield cfg


def config_hash(cfg: dict) -> str:
    """Deterministic 12-char sha256 prefix over the canonical JSON form."""
    blob = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


class GridRunner:
    """Multiprocessing grid runner with checkpoint resumability.

    Each completed config's result is saved to `{output_dir}/configs/{hash}.json` atomically.
    Re-running with the same configs skips already-completed ones.
    """

    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.configs_dir = self.output_dir / "configs"
        self.configs_dir.mkdir(exist_ok=True)

    def is_complete(self, cfg_hash: str) -> bool:
        return (self.configs_dir / f"{cfg_hash}.json").exists()

    def save_result(self, cfg_hash: str, result: dict) -> None:
        """Atomic save: write to .tmp, then rename."""
        path = self.configs_dir / f"{cfg_hash}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, default=str, indent=2))
        tmp.replace(path)

    def run(self, configs: Iterable[dict], run_one_fn: Callable[[dict], dict], workers: int = 4) -> list[dict]:
        """Submit configs to a process pool; skip already-complete; return all results.

        run_one_fn must be a picklable top-level function with signature `(cfg) -> dict`.
        """
        # Materialize so we can iterate twice
        configs = list(configs)

        pending = []
        for cfg in configs:
            h = config_hash(cfg)
            if self.is_complete(h):
                continue
            pending.append((h, cfg))

        results: list[dict] = []
        # Load already-done
        for done_file in self.configs_dir.glob("*.json"):
            results.append(json.loads(done_file.read_text()))

        if not pending:
            return results

        with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as pool:
            futures = {pool.submit(run_one_fn, cfg): h for h, cfg in pending}
            for fut in as_completed(futures):
                h = futures[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"config_hash": h, "error": str(e), "error_type": type(e).__name__}
                self.save_result(h, res)
                results.append(res)
        return results
