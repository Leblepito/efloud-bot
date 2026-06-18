from pathlib import Path
from engine.signal_ledger import SignalLedger, SignalRecord

BASE = dict(symbol="BNB/USDT", direction="SHORT", brk_ts=1781774400000,
            emitted_entry=601.73, sl=607.0, tp1=590.0, tp2=585.0, confluence=80,
            rr1=2.7, rr2=3.2, timeframe="15m", htf_bias="LONG", regime="trend",
            reasons=["OB","CHoCH"], was_tradeable=True, entry_is_retrace=False,
            exit_model="partial_ladder", ts_emitted=1781774400000)

def test_record_and_roundtrip(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl")
    sid = led.record_signal(**BASE)
    assert sid and sid.startswith("BNB/USDT-SHORT-1781774400000-")
    led2 = SignalLedger(tmp_path / "sig.jsonl")
    rows = led2.all_signals()
    assert len(rows) == 1 and rows[0].symbol == "BNB/USDT" and rows[0].direction == "SHORT"

def test_dedup_same_break_no_duplicate(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl")
    sid1 = led.record_signal(**BASE)
    sid2 = led.record_signal(**{**BASE, "ts_emitted": BASE["ts_emitted"] + 3_600_000})
    assert sid2 is None
    assert len(led.all_signals()) == 1

def test_dedup_survives_restart(tmp_path):
    SignalLedger(tmp_path / "sig.jsonl").record_signal(**BASE)
    led = SignalLedger(tmp_path / "sig.jsonl")
    assert led.record_signal(**BASE) is None
    assert len(led.all_signals()) == 1

def test_subcent_tolerance(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl")
    a = dict(BASE, symbol="DOGE/USDT", emitted_entry=0.12345, sl=0.130, tp1=0.118, tp2=None, exit_model="single_target", rr2=None)
    led.record_signal(**a)
    assert led.record_signal(**dict(a, emitted_entry=0.123455)) is None

def test_mint_id_stable():
    a = SignalLedger.mint_id("BNB/USDT", "SHORT", 1781774400000, 601.73, 607.0, 590.0)
    b = SignalLedger.mint_id("BNB/USDT", "SHORT", 1781774400000, 601.73, 607.0, 590.0)
    assert a == b
