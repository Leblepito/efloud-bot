import os
from ops.alerter.dedup import Dedup
from ops.alerter.telegram_client import send_message

class AlertRouter:
    def __init__(self, tg=None, dedup_db="state/routines_dedup.sqlite", ttl_sec=3600):
        self.tg = tg
        self.dedup = Dedup(dedup_db)
        self.ttl_sec = ttl_sec

    def send(self, severity, dedup_key, title, body):
        text = f"[{severity.upper()}] {title}\n{body}"
        if self.dedup.should_fire(dedup_key, self.ttl_sec):
            if self.tg:
                return self.tg.send(text)
            return True
        return False

    @classmethod
    def from_env(cls, dedup_db="state/routines_dedup.sqlite", ttl_sec=3600):
        token = os.environ.get("EFLOUD_TELEGRAM_TOKEN")
        chat_id = os.environ.get("EFLOUD_TELEGRAM_CHAT_ID")
        
        class RealTg:
            def __init__(self, token, chat_id):
                self.token = token
                self.chat_id = chat_id
            def send(self, text):
                return send_message(self.token, self.chat_id, text)
                
        tg = RealTg(token, chat_id) if (token and chat_id) else None
        return cls(tg=tg, dedup_db=dedup_db, ttl_sec=ttl_sec)
