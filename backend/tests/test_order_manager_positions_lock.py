"""B1 (W1.4): OrderManager.positions thread-safety — RLock'lu kritik-bölge yardımcıları.

positions listesine bot cycle thread'i + backend API tarafı erişiyordu, kilit yoktu.
Riskler: kontrol-et-ve-sil yarışında ValueError (çifte silme), yürüyüş/persist
snapshot'ı sırasında mutasyon. Fix: _positions_add/_discard/_snapshot (RLock).

Not (dürüstlük): eşzamanlılık testleri deterministik RED üretmez (GIL zamanlamaya
bağlı) — bu dosya kilitli implementasyonun davranış sözleşmesini sabitleyen bir
regresyon ağıdır; _positions_discard'ın atomik bool sözleşmesi ise deterministiktir.
Tasarım: docs/dev/2026-07-15-b1-ordermanager-positions-lock.md
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

from exchange import OrderManager, Position


def _om(tmp_path=None):
    return OrderManager(client=MagicMock(), dry_run=True,
                        state_dir=str(tmp_path) if tmp_path else None)


def _pos(i: int) -> Position:
    return Position(symbol=f"SYM{i}/USDT", direction="LONG", entry=100.0,
                    sl=95.0, tp1=110.0, tp2=None, size=1.0)


def test_discard_is_atomic_and_reports_result():
    """Sözleşme: listede varsa siler ve True; yoksa dokunmaz ve False (exception yok)."""
    om = _om()
    p = _pos(0)
    om._positions_add(p)
    assert om._positions_discard(p) is True
    assert om._positions_discard(p) is False  # eski kod yolu ValueError riskiydi
    assert om.open_count == 0


def test_concurrent_double_discard_exactly_one_winner():
    """Aynı pozisyonu iki thread aynı anda silmeye çalışır → tam 1 True, 0 hata."""
    om = _om()
    for round_no in range(50):  # yarış penceresini genişlet
        p = _pos(round_no)
        om._positions_add(p)
        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker():
            try:
                barrier.wait()
                results.append(om._positions_discard(p))
            except Exception as e:  # pragma: no cover — kilit varken imkansız
                errors.append(e)

        t1, t2 = threading.Thread(target=worker), threading.Thread(target=worker)
        t1.start(); t2.start(); t1.join(); t2.join()
        assert not errors, f"round {round_no}: {errors}"
        assert sorted(results) == [False, True], f"round {round_no}: {results}"
    assert om.open_count == 0


def test_hammer_add_discard_snapshot_persist(tmp_path):
    """4 rol × eşzamanlı: adder / discarder / snapshotter / persister.
    Beklenti: exception yok + final sayım tutarlı + persist edilen dosya okunur."""
    om = _om(tmp_path)
    N = 200
    added = [_pos(i) for i in range(N)]
    errors: list = []
    start = threading.Barrier(4)

    def adder():
        try:
            start.wait()
            for p in added:
                om._positions_add(p)
        except Exception as e:
            errors.append(("adder", e))

    def discarder():
        try:
            start.wait()
            for p in added[: N // 2]:
                while not om._positions_discard(p):
                    pass  # adder henüz eklememiş olabilir — ekleneni sil
        except Exception as e:
            errors.append(("discarder", e))

    def snapshotter():
        try:
            start.wait()
            for _ in range(300):
                snap = om._positions_snapshot()
                for q in snap:  # mutasyon-altında yürüyüş güvenli olmalı
                    assert q.symbol
                _ = om.open_count
        except Exception as e:
            errors.append(("snapshotter", e))

    def persister():
        try:
            start.wait()
            for _ in range(60):
                om._persist()
        except Exception as e:
            errors.append(("persister", e))

    threads = [threading.Thread(target=f) for f in (adder, discarder, snapshotter, persister)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=30)
    assert not errors, errors
    assert om.open_count == N - N // 2
    om._persist()
    import json
    payload = json.loads((tmp_path / "order_manager_positions.json").read_text(encoding="utf-8"))
    assert len(payload["positions"]) == N - N // 2
