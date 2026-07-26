"""BT-16 (2026-07-25): backtest'te max_holding_hours + NET maliyet kilidi.

Neden var: canli `safe_orchestrator.run_cycle` her cycle'da
`pos_guard.check_holding_time()` calistirip `safety.max_holding_hours`i asan
pozisyonu borsadan zorla kapatiyor (tests/test_max_hold_force_close.py bunu
canli tarafta kilitliyor). BACKTEST bu kurali hic modellemiyordu -> V3 scalp
configi 4 saatlik limitle kosarken backtest 95 SAATLIK trade'ler simule
ediyordu, yani olculen sonucun canlida karsiligi yoktu (2026-07-25 W2 A/B
kosusunda 19 trade'in 14'u 8h+ surmustu). Ayni sekilde hicbir configte
`backtest:` blogu olmadigi icin commission/funding 0.0'a dusuyor ve "NET-cost
gate" aslinda BRUT kosuyordu.

Bu test ikisini de kilitler. Bir refactor `max_holding_hours` cozumlemesini
veya maliyet uygulanmasini sessizce dusurulurse burada patlar.
"""
import math

import pandas as pd
import pytest

from backtest.engine import run_backtest
from backtest.metrics import apply_commission_costs, apply_funding_costs

SYMBOL = "BTC/USDT"


def _flat(n, freq, start="2026-01-01"):
    """Duz fiyat serisi: hicbir SMC sinyali tetiklenmez -> 0 trade.

    Amac trade uretmek DEGIL; `run_backtest`in max_holding_hours cozumlemesini
    ve raporlamasini trade'den bagimsiz dogrulamak.
    """
    idx = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame(
        {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1.0},
        index=idx,
    )


@pytest.fixture
def data():
    return {SYMBOL: {"5m": _flat(400, "5min"), "15m": _flat(400, "15min"),
                     "1h": _flat(400, "1h")}}


def _cfg(**over):
    cfg = {
        "timeframes": {"profile": "custom", "entry": "5m", "mtf": "15m", "htf": "1h",
                       "kline_limit": 500},
        "exchange": {"leverage": 5, "margin_mode": "isolated"},
        "risk": {"position_size_calculation": "fixed", "fixed_position_usdt": 50,
                 "max_open_positions": 10, "min_rr": 1.0, "min_confluence": 55},
        "safety": {"max_total_exposure": 6.0, "max_position_notional_pct": 35.0},
        "engine": {"smc_version": "v1"},
    }
    for k, v in over.items():
        cfg.setdefault(k, {})
        cfg[k].update(v) if isinstance(v, dict) else cfg.__setitem__(k, v)
    return cfg


def _run(data, cfg, **kw):
    return run_backtest(symbols=[SYMBOL], data=data, config=cfg,
                        warmup_bars=200, **kw)


# --------------------------------------------------------------- max_hold

def test_max_hold_resolved_from_safety_block(data):
    """safety.max_holding_hours backtest'e TASINIR (asil regresyon)."""
    cfg = _cfg(safety={"max_holding_hours": 4})
    r = _run(data, cfg)
    assert r["max_holding_hours"] == 4.0


def test_explicit_param_overrides_config(data):
    """Cozumleme sirasi: param -> config -> 0."""
    cfg = _cfg(safety={"max_holding_hours": 4})
    r = _run(data, cfg, max_holding_hours=2.0)
    assert r["max_holding_hours"] == 2.0


def test_absent_max_hold_defaults_off(data):
    """Blok yoksa 0 = KAPALI. Eski baseline'lar birebir korunur."""
    r = _run(data, _cfg())
    assert r["max_holding_hours"] == 0.0
    assert r["max_hold_exits"] == 0


def test_max_hold_exits_always_reported(data):
    """Sayac her kosuda raporlanir (trade olmasa da) — gate bunu okuyor."""
    r = _run(data, _cfg(safety={"max_holding_hours": 4}))
    assert isinstance(r["max_hold_exits"], int)
    assert r["max_hold_exits"] == 0  # duz seride pozisyon acilmaz


# ------------------------------------------------------------- NET cost

def _trade(tid="t1", size=2.0, entry=100.0, exit_=101.0, pnl=2.0):
    return {"id": tid, "size": size, "entry": entry, "exit": exit_, "pnl": pnl}


def test_commission_charges_both_legs():
    """rate x size x (entry + exit) — giris VE cikis bacagi."""
    trades, bal, total = apply_commission_costs([_trade()], 1000.0, 0.04)
    expected = 0.0004 * 2.0 * (100.0 + 101.0)  # = 0.1608
    assert math.isclose(total, expected, rel_tol=1e-9)
    assert math.isclose(trades[0]["pnl"], 2.0 - expected, rel_tol=1e-9)
    assert math.isclose(bal, 1000.0 - expected, rel_tol=1e-9)


def test_zero_commission_is_passthrough():
    """0 => hic dokunma (eski gross baseline'lar bozulmasin)."""
    orig = [_trade()]
    trades, bal, total = apply_commission_costs(orig, 1000.0, 0.0)
    assert total == 0.0 and bal == 1000.0 and trades is orig


@pytest.mark.parametrize("hours,periods", [(0.5, 0), (4.0, 0), (7.9, 0),
                                           (8.0, 1), (17.0, 2)])
def test_funding_counts_completed_8h_periods(hours, periods):
    """floor(hours/8). 4h max_hold ile funding YAPISAL OLARAK 0 —
    2026-07-25 kosusundaki total_funding=0.0 bug degil, bu kuralin sonucu."""
    _, _, total = apply_funding_costs(
        [_trade()], 1000.0, 0.01, {"t1": hours}, {"t1": 250.0})
    assert math.isclose(total, 0.0001 * 250.0 * periods, rel_tol=1e-9)


# ------------------------------------------------- BT-17 intrabar tie-break

class _Pos:
    def __init__(self, direction, entry, sl, tp1):
        self.direction, self.entry, self.sl, self.tp1 = direction, entry, sl, tp1


class _Bar:
    def __init__(self, o, h, l, c):
        self.open, self.high, self.low, self.close = o, h, l, c


def _both_hit_long():
    """SL de TP1 de AYNI barin araligi icinde; bar entry'nin USTUNDE aciliyor.

    Eski kural bunu TP1 sayiyordu. Dar bantli (scalp) bir stratejide HER trade
    boyle cozuluyor -> sahte %84 win_rate. 2026-07-25 olcumu: smc v1 legi
    252 TP1 / 29 SL, PF 7.22, medyan tutus TEK 5m bari, medyan MAE %0.0.
    """
    pos = _Pos("LONG", entry=100.0, sl=99.85, tp1=100.30)
    bar = _Bar(o=100.05, h=100.40, l=99.80, c=100.0)
    return pos, bar


def test_tie_defaults_to_sl():
    """Varsayilan PESIMIST: bar ici sira bilinemez -> SL kazanir."""
    from backtest.intrabar import resolve_fill
    level, _ = resolve_fill(*_both_hit_long())
    assert level == "SL"


def test_legacy_open_heuristic_still_reachable():
    """Eski (iyimser) davranis yalnizca ACIKCA istenirse — eski raporlari
    yeniden uretmek icin."""
    from backtest.intrabar import resolve_fill
    pos, bar = _both_hit_long()
    level, _ = resolve_fill(pos, bar, tie_break="open_heuristic")
    assert level == "TP1"


def test_optimistic_is_upper_bound():
    from backtest.intrabar import resolve_fill
    pos, bar = _both_hit_long()
    level, _ = resolve_fill(pos, bar, tie_break="optimistic")
    assert level == "TP1"


def test_unambiguous_fills_unchanged_by_tie_break():
    """Tek seviye dolduysa tie_break HICBIR SEYI degistirmemeli."""
    from backtest.intrabar import resolve_fill
    only_tp = (_Pos("LONG", 100.0, 99.0, 100.3), _Bar(100.05, 100.4, 99.9, 100.2))
    only_sl = (_Pos("LONG", 100.0, 99.85, 101.0), _Bar(100.05, 100.1, 99.8, 99.9))
    for mode in ("pessimistic", "open_heuristic", "optimistic"):
        assert resolve_fill(*only_tp, tie_break=mode)[0] == "TP1"
        assert resolve_fill(*only_sl, tie_break=mode)[0] == "SL"


def test_short_side_tie_also_defaults_to_sl():
    from backtest.intrabar import resolve_fill
    pos = _Pos("SHORT", entry=100.0, sl=100.15, tp1=99.70)
    bar = _Bar(o=99.95, h=100.20, l=99.60, c=100.0)
    assert resolve_fill(pos, bar)[0] == "SL"
