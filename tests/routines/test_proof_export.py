"""T-012 proof_export tests — privacy whitelist (G-P3-1), curve math, gating.

T-014 eki: uptime bloğu (compute_uptime/load_uptime_samples, schema 1.1.0).
"""
import json

import pytest

from scripts.routines.proof_export import (
    ALLOWED_TOP_KEYS,
    assert_whitelist,
    build_daily_curve,
    build_snapshot,
    compute_uptime,
    load_baseline,
    load_closed_trades,
    load_uptime_samples,
    max_drawdown_pct,
    run,
    sample_healthz,
)

# Deliberately odd baseline so its digits can't coincide with counts/rates.
BASELINE = {"baseline_equity_usdt": 2417.53}


def _trade(exit_ts, pnl, **extra):
    t = {"trade_id": f"t-{exit_ts}-{pnl}", "exit_timestamp": exit_ts,
         "realized_pnl": pnl, "is_winner": pnl > 0}
    t.update(extra)
    return t


def _write_journal(path, trades):
    path.write_text("\n".join(json.dumps(t) for t in trades) + "\n", encoding="utf-8")


# ── Privacy / whitelist (G-P3-1) ─────────────────────────────────────────

class TestPrivacyWhitelist:
    def test_snapshot_keys_are_exactly_whitelist(self):
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 50.0)], BASELINE)
        assert set(snap.keys()) == ALLOWED_TOP_KEYS

    def test_baseline_value_never_leaks_into_snapshot(self):
        # Fixed now_iso: a live microsecond timestamp could coincidentally
        # contain the baseline digits and make a privacy test flaky.
        snap = build_snapshot(
            [_trade("2026-06-01T10:00:00", 50.0), _trade("2026-06-02T10:00:00", -20.0)],
            BASELINE, now_iso="2026-06-11T00:00:00+00:00",
        )
        dumped = json.dumps(snap)
        assert "2417" not in dumped
        assert "usdt" not in dumped.lower()

    def test_absolute_pnl_values_not_in_snapshot(self):
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 123.45)], BASELINE,
                              now_iso="2026-06-11T00:00:00+00:00")
        assert "123.45" not in json.dumps(snap)

    def test_whitelist_guard_rejects_extra_top_key(self):
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 1.0)], BASELINE)
        snap["balance_usdt"] = 999
        with pytest.raises(ValueError, match="non-whitelisted|forbidden"):
            assert_whitelist(snap)

    def test_whitelist_guard_rejects_forbidden_substring_nested(self):
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 1.0)], BASELINE)
        snap["equity_curve"][0] = {"date": "2026-06-01", "equity_norm": 1.0}
        good = json.loads(json.dumps(snap))
        good["period"]["from_position_size"] = "x"  # nested forbidden key
        with pytest.raises(ValueError):
            assert_whitelist(good)

    def test_curve_normalized_starts_at_one(self):
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 50.0)], BASELINE)
        assert snap["equity_curve"][0]["equity_norm"] == 1.0


# ── Curve math ───────────────────────────────────────────────────────────

class TestCurveMath:
    def test_daily_close_granularity_groups_same_day(self):
        trades = [
            _trade("2026-06-01T10:00:00", 30.0),
            _trade("2026-06-01T18:00:00", -10.0),  # same UTC day
            _trade("2026-06-02T09:00:00", 5.0),
        ]
        curve = build_daily_curve(trades, 1000.0)
        # initial point + 2 trade days (NOT 3 intraday points — G-P3-1)
        assert len(curve) == 3
        # anchor sits one day BEFORE the first trade day (no date collision)
        assert curve[0] == {"date": "2026-05-31", "equity_norm": 1.0}
        assert curve[1] == {"date": "2026-06-01", "equity_norm": 1.02}
        assert curve[2] == {"date": "2026-06-02", "equity_norm": 1.025}

    def test_anchor_date_never_collides_with_first_trade_day(self):
        curve = build_daily_curve([_trade("2026-06-01T10:00:00", 5.0)], 1000.0)
        dates = [p["date"] for p in curve]
        assert len(dates) == len(set(dates))

    def test_max_drawdown_peak_relative(self):
        # 1.0 → 1.2 (peak) → 0.9 → 1.1 : dd = (1.2-0.9)/1.2 = 25%
        curve = [
            {"date": "d1", "equity_norm": 1.0},
            {"date": "d2", "equity_norm": 1.2},
            {"date": "d3", "equity_norm": 0.9},
            {"date": "d4", "equity_norm": 1.1},
        ]
        assert max_drawdown_pct(curve) == 25.0

    def test_max_drawdown_is_real_pct_thanks_to_baseline(self):
        # baseline 2000, +100 then -300: peak 2100 → trough 1800 = 14.29%
        trades = [_trade("2026-06-01T10:00:00", 100.0),
                  _trade("2026-06-02T10:00:00", -300.0)]
        snap = build_snapshot(trades, {"baseline_equity_usdt": 2000.0})
        assert snap["max_dd_pct"] == pytest.approx(14.29, abs=0.01)

    def test_since_filters_older_trades(self):
        trades = [_trade("2026-05-01T10:00:00", 999.0),
                  _trade("2026-06-02T10:00:00", 10.0)]
        snap = build_snapshot(trades, {"baseline_equity_usdt": 1000.0, "since": "2026-06-01"})
        assert snap["trade_count"] == 1
        assert snap["period"]["from"] == "2026-06-01"


# ── Stats semantics (journal.stats() parity) ─────────────────────────────

class TestStats:
    def test_win_rate_and_profit_factor(self):
        trades = [
            _trade("2026-06-01T10:00:00", 100.0),
            _trade("2026-06-02T10:00:00", 50.0),
            _trade("2026-06-03T10:00:00", -75.0),
        ]
        snap = build_snapshot(trades, BASELINE)
        assert snap["trade_count"] == 3
        assert snap["win_rate_pct"] == 66.7
        assert snap["profit_factor"] == 2.0  # 150 / 75

    def test_zero_loss_profit_factor_is_zero_like_journal_stats(self):
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 10.0)], BASELINE)
        assert snap["profit_factor"] == 0.0


# ── Journal loading ──────────────────────────────────────────────────────

class TestJournalLoading:
    def test_open_trades_excluded(self, tmp_path):
        j = tmp_path / "journal.jsonl"
        _write_journal(j, [
            _trade("2026-06-01T10:00:00", 10.0),
            {"trade_id": "open-1", "exit_timestamp": None, "realized_pnl": 0.0},
        ])
        assert len(load_closed_trades(j)) == 1

    def test_torn_last_line_tolerated(self, tmp_path):
        j = tmp_path / "journal.jsonl"
        j.write_text(
            json.dumps(_trade("2026-06-01T10:00:00", 10.0)) + "\n" + '{"trade_id": "torn',
            encoding="utf-8",
        )
        sink: list = []
        assert len(load_closed_trades(j, corrupt_sink=sink)) == 1
        assert sink == []  # terminal torn line is NOT flagged

    def test_mid_file_corruption_flagged(self, tmp_path):
        j = tmp_path / "journal.jsonl"
        j.write_text(
            "not-json-at-all\n" + json.dumps(_trade("2026-06-01T10:00:00", 10.0)) + "\n",
            encoding="utf-8",
        )
        sink: list = []
        assert len(load_closed_trades(j, corrupt_sink=sink)) == 1
        assert sink == [1]  # non-terminal corrupt line IS flagged (1-based)

    def test_missing_journal_returns_empty(self, tmp_path):
        assert load_closed_trades(tmp_path / "nope.jsonl") == []


# ── Baseline gating ──────────────────────────────────────────────────────

class TestBaselineGating:
    def test_missing_baseline_blocks_snapshot(self, tmp_path):
        cfg = {"proof_export": {
            "journal": str(tmp_path / "j.jsonl"),
            "baseline": str(tmp_path / "missing.json"),
            "out": str(tmp_path / "snap.json"),
            "uptime_samples": str(tmp_path / "u.jsonl"),
        }}
        result = run(cfg=cfg)
        assert result.ok is False
        assert result.breaches[0]["key"] == "proof_export_baseline_missing"
        assert not (tmp_path / "snap.json").exists()

    def test_invalid_baseline_rejected(self, tmp_path):
        p = tmp_path / "baseline.json"
        p.write_text(json.dumps({"baseline_equity_usdt": -5}), encoding="utf-8")
        assert load_baseline(p) is None
        p.write_text("not json", encoding="utf-8")
        assert load_baseline(p) is None


# ── End-to-end run() ─────────────────────────────────────────────────────

class TestRun:
    def test_run_writes_whitelisted_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EFLOUD_API_BASE_URL", "http://127.0.0.1:1")  # unreachable
        j = tmp_path / "j.jsonl"
        _write_journal(j, [_trade("2026-06-01T10:00:00", 25.0)])
        (tmp_path / "baseline.json").write_text(json.dumps(BASELINE), encoding="utf-8")
        cfg = {"proof_export": {
            "journal": str(j),
            "baseline": str(tmp_path / "baseline.json"),
            "out": str(tmp_path / "snap.json"),
            "uptime_samples": str(tmp_path / "u.jsonl"),
        }}
        result = run(cfg=cfg)
        assert result.ok is True
        snap = json.loads((tmp_path / "snap.json").read_text(encoding="utf-8"))
        assert set(snap.keys()) == ALLOWED_TOP_KEYS
        # healthz sample appended even though API unreachable
        sample = json.loads((tmp_path / "u.jsonl").read_text(encoding="utf-8").strip())
        assert sample["status"] == "unreachable"

    def test_registered_in_runner(self):
        from scripts.routines.runner import REGISTRY
        import scripts.routines.proof_export  # noqa: F401 — ensure import side effect
        assert "proof_export" in REGISTRY


# ── Healthz sampling ─────────────────────────────────────────────────────

class TestHealthzSampling:
    def test_sample_statuses(self, tmp_path):
        class FakeRes:
            def __init__(self, payload):
                self._p = payload

            def json(self):
                return self._p

        path = tmp_path / "u.jsonl"
        assert sample_healthz(path, http_get=lambda url: FakeRes({"status": "ok"})) == "ok"
        assert sample_healthz(path, http_get=lambda url: FakeRes({"status": "suspended"})) == "suspended"
        assert sample_healthz(path, http_get=lambda url: (_ for _ in ()).throw(OSError())) == "unreachable"
        # contract coercion: unknown body status → "unhealthy" (healthz-contract §3)
        assert sample_healthz(path, http_get=lambda url: FakeRes({"status": "weird"})) == "unhealthy"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert [json.loads(line)["status"] for line in lines] == [
            "ok", "suspended", "unreachable", "unhealthy"]


# ── Uptime (T-014, healthz-contract §3) ──────────────────────────────────

NOW_ISO = "2026-06-11T12:00:00+00:00"


def _sample(ts, status):
    return {"ts": ts, "status": status}


class TestUptime:
    def test_two_metrics_separated(self):
        """service_uptime = (ok+suspended)/n; trading_active = ok/n — KARIŞMAZ."""
        samples = [
            _sample("2026-06-10T00:00:00+00:00", "ok"),
            _sample("2026-06-10T06:00:00+00:00", "ok"),
            _sample("2026-06-10T12:00:00+00:00", "suspended"),
            _sample("2026-06-10T18:00:00+00:00", "unreachable"),
        ]
        u = compute_uptime(samples, now_iso=NOW_ISO, window_days=30)
        assert u["sample_count"] == 4
        assert u["service_uptime_pct"] == 75.0   # (2 ok + 1 suspended) / 4
        assert u["trading_active_pct"] == 50.0   # 2 ok / 4

    def test_window_excludes_old_samples(self):
        samples = [
            _sample("2026-03-01T00:00:00+00:00", "unhealthy"),  # pencere dışı
            _sample("2026-06-10T00:00:00+00:00", "ok"),
        ]
        u = compute_uptime(samples, now_iso=NOW_ISO, window_days=30)
        assert u["sample_count"] == 1
        assert u["service_uptime_pct"] == 100.0

    def test_zero_samples_is_no_measurement_not_100(self):
        u = compute_uptime([], now_iso=NOW_ISO)
        assert u["sample_count"] == 0
        assert u["service_uptime_pct"] is None
        assert u["trading_active_pct"] is None

    def test_naive_timestamps_tolerated(self):
        u = compute_uptime([_sample("2026-06-10T00:00:00", "ok")], now_iso=NOW_ISO)
        assert u["sample_count"] == 1

    def test_load_samples_skips_corrupt_lines(self, tmp_path):
        p = tmp_path / "u.jsonl"
        p.write_text(
            json.dumps(_sample("2026-06-10T00:00:00+00:00", "ok")) + "\nnot-json\n",
            encoding="utf-8",
        )
        assert len(load_uptime_samples(p)) == 1

    def test_snapshot_includes_uptime_and_passes_whitelist(self):
        u = compute_uptime([_sample("2026-06-10T00:00:00+00:00", "ok")], now_iso=NOW_ISO)
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 5.0)], BASELINE,
                              now_iso=NOW_ISO, uptime=u)
        assert set(snap.keys()) == ALLOWED_TOP_KEYS
        assert snap["uptime"]["service_uptime_pct"] == 100.0
        assert snap["schema_version"] == "1.1.0"

    def test_whitelist_rejects_extra_uptime_key(self):
        snap = build_snapshot([_trade("2026-06-01T10:00:00", 1.0)], BASELINE,
                              now_iso=NOW_ISO,
                              uptime={"window_days": 30, "sample_count": 1,
                                      "service_uptime_pct": 100.0,
                                      "trading_active_pct": 100.0})
        bad = json.loads(json.dumps(snap))
        bad["uptime"]["heartbeat_age"] = 5
        with pytest.raises(ValueError, match="uptime"):
            assert_whitelist(bad)

    def test_run_snapshot_contains_uptime_block(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EFLOUD_API_BASE_URL", "http://127.0.0.1:1")  # unreachable
        j = tmp_path / "j.jsonl"
        _write_journal(j, [_trade("2026-06-01T10:00:00", 25.0)])
        (tmp_path / "baseline.json").write_text(json.dumps(BASELINE), encoding="utf-8")
        cfg = {"proof_export": {
            "journal": str(j),
            "baseline": str(tmp_path / "baseline.json"),
            "out": str(tmp_path / "snap.json"),
            "uptime_samples": str(tmp_path / "u.jsonl"),
        }}
        result = run(cfg=cfg)
        assert result.ok is True
        snap = json.loads((tmp_path / "snap.json").read_text(encoding="utf-8"))
        # run() önce sample alır (unreachable) → uptime bloğu 1 örnekle hesaplanır
        assert snap["uptime"]["sample_count"] == 1
        assert snap["uptime"]["service_uptime_pct"] == 0.0
        assert snap["uptime"]["trading_active_pct"] == 0.0
