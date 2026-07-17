"""E-1/E-2/E-6 (2026-07-17 review): persist crash/eşzamanlılık güvenliği.

E-1: OrderManager._persist ve StateStore.save SABİT tmp adı kullanıyordu.
_persist hem bot executor thread'inden (reconcile/open) hem FastAPI loop
thread'inden (kill-switch, /orders/close → _fallback_close) çağrılır; paylaşılan
tmp'de eşzamanlı iki yazım birbirinin dosyasını truncate/rename edip bozuk
snapshot terfi ettirebiliyordu → restart'ta quarantine → SIFIR pozisyonla açılış
(2026-05-08 reconcile-körlüğü sınıfı). Fix: yazar-özel (pid+tid) tmp adı.

E-2: TradeJournal._persist truncate-in-place yazıyordu — yazım ortasında
crash tüm journal kuyruğunu kalıcı siliyordu. Fix: tmp + fsync + os.replace.

E-6: sync_release_symbol içindeki future.result() CancelledError'ı
(Py≥3.8'de BaseException) `except Exception` yakalamıyordu → run_cycle
finally'sinden kaçıp asıl hatayı maskeliyordu. Fix: açık CancelledError dalı.
"""

import asyncio
import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

from exchange import OrderManager, Position
from engine.safety.state import StateStore
from engine.journal import TradeJournal, TradeSnapshot


def _snap(i: int) -> TradeSnapshot:
    return TradeSnapshot(
        trade_id=f"t{i}", symbol="ETH/USDT", direction="LONG", timeframe="15m",
        entry_timestamp="2026-07-17T00:00:00", entry_price=100.0, sl_initial=99.0,
        tp1_initial=103.0, tp2_initial=106.0, position_size=1.0, htf_bias="BULL",
        intent_score_entry=50, intent_label_entry="ok", confluence_score=60,
    )


class TestOrderManagerPersistConcurrency:
    def test_concurrent_persist_never_promotes_corrupt_file(self, tmp_path):
        client = Mock()
        om = OrderManager(client, dry_run=True, state_dir=str(tmp_path))
        om.positions.append(Position("ETH/USDT", "LONG", 100.0, 99.0, 103.0, 106.0, 1.0))

        errors = []

        def hammer():
            try:
                for _ in range(40):
                    om._persist()
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        state_file = om._state_file
        assert state_file.exists()
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        assert "positions" in payload and len(payload["positions"]) == 1
        # Yarım kalmış tmp artığı kalmamalı (hepsi replace edildi ya da temizlendi).
        leftovers = list(Path(tmp_path).glob("*.tmp.*"))
        assert leftovers == [], f"stray tmp files: {leftovers}"

    def test_tmp_name_is_writer_unique(self, tmp_path):
        """İki farklı thread'in tmp yolu çakışmamalı (pid+tid suffix)."""
        client = Mock()
        om = OrderManager(client, dry_run=True, state_dir=str(tmp_path))
        seen = []

        real_open = open

        def spy_open(path, *a, **kw):
            p = str(path)
            if ".json.tmp." in p:
                seen.append(p)
            return real_open(path, *a, **kw)

        import builtins
        orig = builtins.open
        builtins.open = spy_open
        try:
            om._persist()
            t = threading.Thread(target=om._persist)
            t.start(); t.join()
        finally:
            builtins.open = orig

        assert len(seen) >= 2
        assert seen[0] != seen[1], "tmp adı thread'ler arası paylaşılıyor (E-1 regresyonu)"


class TestStateStoreConcurrency:
    def test_concurrent_save_never_promotes_corrupt_file(self, tmp_path):
        store = StateStore(state_dir=str(tmp_path))
        errors = []

        def hammer(n):
            try:
                for i in range(40):
                    assert store.save("breaker", {"state": "OPEN", "n": n, "i": i})
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=hammer, args=(k,)) for k in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        payload = json.loads((Path(tmp_path) / "breaker.json").read_text(encoding="utf-8"))
        assert payload["data"]["state"] == "OPEN"
        assert list(Path(tmp_path).glob("*.tmp.*")) == []


class TestJournalCrashAtomicity:
    def test_failed_rewrite_leaves_previous_journal_intact(self, tmp_path, monkeypatch):
        path = tmp_path / "trade_journal.jsonl"
        j = TradeJournal(journal_path=str(path))
        j.record_entry(_snap(1))
        j.record_entry(_snap(2))
        before = path.read_text(encoding="utf-8")
        assert before.count("\n") == 2

        # Crash simülasyonu: yeniden-yazım ortasında patlat (2. satırda).
        calls = {"n": 0}
        import engine.journal as journal_mod
        real_dumps = journal_mod.json.dumps

        def exploding_dumps(obj, *a, **kw):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("simulated crash mid-rewrite")
            return real_dumps(obj, *a, **kw)

        monkeypatch.setattr(journal_mod.json, "dumps", exploding_dumps)
        with pytest.raises(RuntimeError):
            j._persist(j._cache[0])
        monkeypatch.undo()

        # Truncate-in-place olsaydı dosya 1 satıra (ya da 0'a) inmişti;
        # tmp+replace ile ÖNCEKİ içerik el değmemiş kalmalı.
        assert path.read_text(encoding="utf-8") == before


class TestReleaseLeaseCancelledError:
    def test_cancelled_release_returns_false_instead_of_raising(self, monkeypatch):
        from engine.instance_manager import InstanceManager

        im = InstanceManager.__new__(InstanceManager)
        im.coordination_enabled = True
        im._loop = Mock()
        im.instance_id = "i1"
        im._active_leases = {"ETH/USDT": "tok"}
        im.release_timeout_sec = 0.1
        im.db = Mock()

        fut = Mock()
        fut.result = Mock(side_effect=asyncio.CancelledError())
        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", lambda *a, **k: fut)

        assert im.sync_release_symbol("ETH/USDT") is False
