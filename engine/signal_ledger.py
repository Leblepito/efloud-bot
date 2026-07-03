from __future__ import annotations
import json, hashlib, logging
from dataclasses import dataclass, asdict, fields as dc_fields
from pathlib import Path

log = logging.getLogger("efloud.signal_ledger")

def _tol_round(symbol: str, price: float) -> float:
    if price == 0:
        return 0.0
    from math import floor, log10
    digits = 4 - int(floor(log10(abs(price))))
    return round(price, max(digits, 2))

@dataclass
class SignalRecord:
    signal_id: str
    ts_emitted: int
    brk_ts: int
    symbol: str
    direction: str
    emitted_entry: float
    sl: float
    tp1: float
    tp2: float | None
    confluence: float
    rr1: float
    rr2: float | None
    timeframe: str
    htf_bias: str
    regime: str
    reasons: list
    was_tradeable: bool
    entry_is_retrace: bool
    exit_model: str
    kronos_verdict: dict | None = None
    agents_verdict: dict | None = None
    status: str = "open"
    disposition: str = "readonly"
    outcome: str | None = None
    fill_price: float | None = None
    hypo_r_gross: float | None = None
    hypo_r_net: float | None = None
    ts_filled: int | None = None
    ts_resolved: int | None = None
    bars_to_fill: int | None = None
    bars_to_resolve: int | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    resolved_at_granularity: str | None = None
    trade_id: str | None = None

_FIELDS = {f.name for f in dc_fields(SignalRecord)}

class SignalLedger:
    def __init__(self, path):
        self.path = Path(path)
        self._rows: dict[str, SignalRecord] = {}
        self._seen: set[tuple] = set()
        self._load()

    @staticmethod
    def dedup_key(symbol, direction, entry) -> tuple:
        return (symbol, direction, _tol_round(symbol, float(entry)))

    @staticmethod
    def mint_id(symbol, direction, brk_ts_ms, entry, sl, tp1) -> str:
        h = hashlib.sha1(f"{entry}|{sl}|{tp1}".encode()).hexdigest()[:8]
        return f"{symbol}-{direction}-{int(brk_ts_ms)}-{h}"

    def _load(self):
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = {k: v for k, v in json.loads(line).items() if k in _FIELDS}
                rec = SignalRecord(**d)
            except Exception:
                continue
            self._rows[rec.signal_id] = rec
            self._seen.add(self.dedup_key(rec.symbol, rec.direction, rec.emitted_entry))

    def _persist(self):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as fh:
            for rec in self._rows.values():
                fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def record_signal(self, **fields) -> str | None:
        key = self.dedup_key(fields["symbol"], fields["direction"], fields["emitted_entry"])
        if key in self._seen:
            return None
        sid = self.mint_id(fields["symbol"], fields["direction"], fields["brk_ts"],
                           fields["emitted_entry"], fields["sl"], fields["tp1"])
        rec = SignalRecord(signal_id=sid, **{k: v for k, v in fields.items() if k in _FIELDS})
        self._rows[sid] = rec
        self._seen.add(key)
        self._persist()
        return sid

    def attach_kronos(self, signal_id, verdict):
        rec = self._rows.get(signal_id)
        if rec and rec.kronos_verdict is None:
            rec.kronos_verdict = verdict
            self._persist()

    def set_trade_id(self, signal_id, trade_id):
        rec = self._rows.get(signal_id)
        if rec:
            rec.trade_id = trade_id
            rec.disposition = "opened"
            self._persist()

    def update_resolution(self, signal_id, **fields):
        rec = self._rows.get(signal_id)
        if not rec:
            return
        for k, v in fields.items():
            if k in _FIELDS:
                setattr(rec, k, v)
        self._persist()

    def open_signals(self):
        return [r for r in self._rows.values() if r.status in ("open", "filled")]

    def all_signals(self):
        return list(self._rows.values())


def ledger_enabled(cfg_block) -> bool:
    """Master on/off for the Edge Measurement Core.

    Env EFLOUD_SIGNAL_LEDGER_ENABLED (1/true/yes/on or 0/false/no/off)
    overrides the config block's `enabled` value, so prod can activate via
    .env.production without editing the baked-in config (repo default stays
    OFF per dev-contract).
    """
    import os
    env = os.environ.get("EFLOUD_SIGNAL_LEDGER_ENABLED", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    return bool((cfg_block or {}).get("enabled"))
