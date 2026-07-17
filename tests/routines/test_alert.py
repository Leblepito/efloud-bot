from scripts.routines._alert import AlertRouter

class FakeTg:
    def __init__(self):
        self.sent = []
    def send(self, text):
        self.sent.append(text)
        return True

def test_dedup_suppresses_repeat(tmp_path):
    r = AlertRouter(tg=FakeTg(), dedup_db=str(tmp_path / "d.sqlite"), ttl_sec=3600)
    r.send("critical", "k1", "T", "body")
    r.send("critical", "k1", "T", "body")
    assert len(r.tg.sent) == 1

def test_distinct_keys_send(tmp_path):
    r = AlertRouter(tg=FakeTg(), dedup_db=str(tmp_path / "d.sqlite"), ttl_sec=3600)
    r.send("warn", "k1", "T", "b")
    r.send("warn", "k2", "T", "b")
    assert len(r.tg.sent) == 2

def test_no_tg_is_noop(tmp_path):
    r = AlertRouter(tg=None, dedup_db=str(tmp_path / "d.sqlite"))
    r.send("info", "k", "T", "b")  # must not raise


# ── R-6 (2026-07-17): dedup teslimat-sonrası düşülür + HTML escape ──────────

class FailingTg:
    def __init__(self):
        self.calls = 0
    def send(self, text):
        self.calls += 1
        return False


def test_failed_send_does_not_consume_dedup(tmp_path):
    """Gönderim başarısızsa dedup penceresi tüketilmez — sonraki deneme gider."""
    r = AlertRouter(tg=FailingTg(), dedup_db=str(tmp_path / "d.sqlite"), ttl_sec=3600)
    assert r.send("critical", "k1", "T", "b") is False
    assert r.tg.calls == 1
    # Aynı key ile ikinci deneme: eski davranışta dedup yutardı (calls 1 kalırdı).
    r.send("critical", "k1", "T", "b")
    assert r.tg.calls == 2


def test_successful_send_consumes_dedup(tmp_path):
    ok_tg = FakeTg()
    r = AlertRouter(tg=ok_tg, dedup_db=str(tmp_path / "d.sqlite"), ttl_sec=3600)
    assert r.send("critical", "k1", "T", "b") is True
    r.send("critical", "k1", "T", "b")
    assert len(ok_tg.sent) == 1


def test_text_is_html_escaped(tmp_path):
    """telegram_client parse_mode=HTML: ham '<' Telegram 400'üne yol açıyordu
    (örn. breaker 'balance $X < threshold $Y' gövdesi)."""
    tg = FakeTg()
    r = AlertRouter(tg=tg, dedup_db=str(tmp_path / "d.sqlite"), ttl_sec=3600)
    r.send("critical", "k1", "Emergency", "balance $95.00 < threshold $100.00")
    assert "&lt;" in tg.sent[0]
    assert "<" not in tg.sent[0].replace("&lt;", "")
