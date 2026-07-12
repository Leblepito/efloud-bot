"""Backtest hijyen paketi Batch-1 (2026-07-11 review, ertelenen kalemler).

BT-4  : SlippageConfig.entry_slip_pct hiç uygulanmıyordu — entry fill'leri
        adverse yönde slip edilmeli (piramit tranche'ları dahil, her biri 1 kez).
BT-9  : step_every_n_bars>1 iken yalnız bar i+1 taranıyordu — i+1..i+step
        aralığındaki SL/TP dokunuşları sonsuza dek kayboluyordu.
BT-12 : sim_close_ts karar barının (i) timestamp'iyle damgalanıyordu — fill
        barının timestamp'i olmalı (funding holding-hours doğruluğu).
BT-7  : compute_stop_hunt_rate wall-clock closed_at kullanıyordu (backtest'te
        "şimdi") — tarihsel df.index ile kesişmez, metrik hep ~0 (ölü).
"""
from __future__ import annotations

import pandas as pd
import pytest
import yaml

import backtest.engine as bt_engine
from backtest.engine import run_backtest
from backtest.metrics import compute_stop_hunt_rate
from engine import SafeOrchestrator


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _flat_df(n=400, lows=None, highs=None, price=100.0):
    """Flat OHLC frame; lows/highs: {bar_index: value} nokta müdahaleleri."""
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    df = pd.DataFrame({
        "open": [price] * n, "high": [price] * n,
        "low": [price] * n, "close": [price] * n, "volume": [1.0] * n,
    }, index=idx)
    for i, v in (lows or {}).items():
        df.iloc[i, df.columns.get_loc("low")] = v
    for i, v in (highs or {}).items():
        df.iloc[i, df.columns.get_loc("high")] = v
    return df


class _ScriptedOrch(SafeOrchestrator):
    """run_cycle övermesi: SMC analizi yerine script'teki aksiyonları oynatır.

    SCRIPT: list[(pd.Timestamp, callable(orch))] — sim `now` ilgili timestamp'e
    ulaştığında aksiyon bir kez çalışır. Engine loop'unun kendisi (fill scan,
    slippage, sim-time stamping, funding) GERÇEK kodla koşar.
    """
    SCRIPT: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._script = [{"at": at, "run": fn, "done": False} for at, fn in type(self).SCRIPT]

    def run_cycle(self, symbol, df_htf, df_mtf, df_entry, df_daily=None,
                  balance=0.0, now=None):
        now_ts = pd.Timestamp(now)
        for step in self._script:
            if not step["done"] and now_ts >= step["at"]:
                step["run"](self)
                step["done"] = True


def _run(monkeypatch, base_config, data, script, **kw):
    monkeypatch.setattr(_ScriptedOrch, "SCRIPT", script)
    monkeypatch.setattr(bt_engine, "SafeOrchestrator", _ScriptedOrch)
    return run_backtest(
        symbols=["BTC/USDT"], data={"BTC/USDT": data}, config=base_config,
        initial_balance=2000.0, **kw,
    )


def _data_dict(df):
    return {"4h": df, "12h": df, "15m": df, "1d": df}


# ─────────────────────────── BT-4: entry slippage ───────────────────────────

def test_entry_fill_gets_adverse_slippage(monkeypatch, base_config):
    """LONG entry 100.0 → kayıtlı entry 100 * (1 + 0.05/100) = 100.05."""
    df = _flat_df(lows={380: 88.0})  # SL 90 → bar 380'de fill
    idx = df.index

    def _open(orch):
        orch.lifecycle.open_position(
            symbol="BTC/USDT", direction="LONG", entry_price=100.0,
            sl=90.0, tp1=200.0, tp2=None, size=1.0,
        )

    res = _run(monkeypatch, base_config, _data_dict(df), [(idx[210], _open)])
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["exit_reason"] == "SL"
    assert t["entry"] == pytest.approx(100.05)


def test_pyramid_tranche_each_slipped_exactly_once(monkeypatch, base_config):
    """İlk giriş + piramit ekleme: her tranche kendi fiyatından 1 kez slip edilir.

    1.0 @ 100 + 3.0 @ 102 → avg = 1.0005 * (100*1 + 102*3) / 4 = 101.55075.
    (Yalnız ilk tranche slip edilseydi 101.5125; ilk tranche iki kez slip
    edilseydi > 101.5633 olurdu — ikisi de reddedilir.)
    """
    df = _flat_df(lows={380: 88.0})
    idx = df.index

    def _open(orch):
        orch.lifecycle.open_position(
            symbol="BTC/USDT", direction="LONG", entry_price=100.0,
            sl=90.0, tp1=200.0, tp2=None, size=1.0,
        )

    def _add(orch):
        pos = orch.lifecycle.open_positions("BTC/USDT")[0]
        orch.lifecycle.add_to_position(pos, price=102.0, size=3.0)

    res = _run(monkeypatch, base_config, _data_dict(df),
               [(idx[210], _open), (idx[230], _add)])
    assert len(res["trades"]) == 1
    assert res["trades"][0]["entry"] == pytest.approx(1.0005 * (100.0 + 306.0) / 4)


# ──────────────── BT-9 + BT-12: step>1 fill taraması + sim_close_ts ────────────────

def test_step_gt_1_scans_skipped_bars_for_fills(monkeypatch, base_config):
    """step=3: cycle barları 200,203,...,209,212. Dip yalnız bar 211'de (atlanan
    bar). Eski kod yalnız i+1'i taradığından pozisyon hiç kapanmıyordu."""
    df = _flat_df(lows={211: 94.0})  # SL 95 yalnız bar 211'de dokunulur
    idx = df.index

    def _open(orch):
        orch.lifecycle.open_position(
            symbol="BTC/USDT", direction="LONG", entry_price=100.0,
            sl=95.0, tp1=200.0, tp2=None, size=1.0,
        )

    res = _run(monkeypatch, base_config, _data_dict(df),
               [(idx[209], _open)], step_every_n_bars=3)
    assert len(res["trades"]) == 1, "atlanan bardaki SL fill kayboldu"
    t = res["trades"][0]
    assert t["exit_reason"] == "SL"
    # SL fill 95 → %0.10 adverse → 94.905
    assert t["exit"] == pytest.approx(95.0 * (1 - 0.10 / 100))
    # BT-12: sim_closed_at = fill barının (211) timestamp'i, karar barının değil
    assert t["sim_closed_at"] == str(idx[211])


def test_sim_close_ts_stamped_with_fill_bar_not_decision_bar(monkeypatch, base_config):
    """step=1: bar 379 cycle'ı bar 380'deki fill'i bulur — damga bar 380 olmalı
    (eski kod karar barı 379'un timestamp'ini basıyordu)."""
    df = _flat_df(lows={380: 88.0})
    idx = df.index

    def _open(orch):
        orch.lifecycle.open_position(
            symbol="BTC/USDT", direction="LONG", entry_price=100.0,
            sl=90.0, tp1=200.0, tp2=None, size=1.0,
        )

    res = _run(monkeypatch, base_config, _data_dict(df), [(idx[210], _open)])
    assert len(res["trades"]) == 1
    assert res["trades"][0]["sim_closed_at"] == str(idx[380])


# ─────────────────────── BT-7: stop_hunt_rate ölü metrik ───────────────────────

def _hunt_data(symbol):
    idx = pd.date_range("2025-01-01 00:15", periods=10, freq="15min", tz="UTC")
    n = 10
    highs = [105.0, 108.0, 112.0, 113.0] + [100.0] * (n - 4)
    return {
        symbol: {
            "15m": pd.DataFrame(
                {"open": [100.0] * n, "high": highs, "low": [99.0] * n,
                 "close": [100.0] * n, "volume": [1.0] * n},
                index=idx,
            )
        }
    }


def test_stop_hunt_uses_sim_closed_at_when_present():
    """Backtest kayıtları: closed_at = wall-clock (2026, veri aralığı dışı),
    sim_closed_at = sim barı (2025, veri içinde). Metrik sim zamanını kullanmalı."""
    trades = [{
        "symbol": "ETH/USDT", "direction": "LONG", "entry": 100.0,
        "sl": 95.0, "tp1": 110.0, "pnl": -10.0, "exit_reason": "SL",
        "closed_at": "2026-07-12 09:00:00+00:00",          # wall-clock (işe yaramaz)
        "sim_closed_at": "2025-01-01 00:00:00+00:00",       # sim zamanı
        "exit": 95.0,
    }]
    rate = compute_stop_hunt_rate(trades, _hunt_data("ETH/USDT"), lookback_bars=4)
    assert rate == 1.0, "sim_closed_at yok sayıldı → metrik ölü (0.0)"


def test_stop_hunt_falls_back_to_closed_at():
    """sim_closed_at alanı olmayan (canlı/legacy) kayıtlar closed_at ile çalışmaya
    devam eder — mevcut davranış regresyonu yok."""
    trades = [{
        "symbol": "ETH/USDT", "direction": "LONG", "entry": 100.0,
        "sl": 95.0, "tp1": 110.0, "pnl": -10.0, "exit_reason": "SL",
        "closed_at": "2025-01-01 00:00:00+00:00",
        "exit": 95.0,
    }]
    assert compute_stop_hunt_rate(trades, _hunt_data("ETH/USDT"), lookback_bars=4) == 1.0


def test_stop_hunt_skips_trade_without_any_close_ts():
    trades = [{
        "symbol": "ETH/USDT", "direction": "LONG", "entry": 100.0,
        "sl": 95.0, "tp1": 110.0, "pnl": -10.0, "exit_reason": "SL",
        "closed_at": None, "sim_closed_at": None, "exit": 95.0,
    }]
    # Ne sim ne wall-clock zaman var → trade değerlendirilemez; crash yok.
    assert compute_stop_hunt_rate(trades, _hunt_data("ETH/USDT"), lookback_bars=4) == 0.0
