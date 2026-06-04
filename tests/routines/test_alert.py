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
