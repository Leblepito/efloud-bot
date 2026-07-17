import html
import os
from ops.alerter.dedup import Dedup
from ops.alerter.telegram_client import send_message

class AlertRouter:
    def __init__(self, tg=None, dedup_db="state/routines_dedup.sqlite", ttl_sec=3600):
        self.tg = tg
        self.dedup = Dedup(dedup_db)
        self.ttl_sec = ttl_sec

    def send(self, severity, dedup_key, title, body):
        # R-6 fix (2026-07-17):
        # 1) Dedup kaydı teslimat BAŞARILI olunca düşülür — başarısız gönderim
        #    tek-atımlık transition alert'ini (breaker trip) window boyunca
        #    yutmasın.
        # 2) html.escape: telegram_client parse_mode=HTML kullanır; breach
        #    gövdeleri ham '<' içerebiliyor (örn. breaker "balance $X <
        #    threshold $Y") → Telegram 400 "can't parse entities" ile TAM DA o
        #    kritik alert'i düşürüyordu. Rutin alert'leri düz metindir; kasıtlı
        #    HTML yok.
        text = html.escape(f"[{severity.upper()}] {title}\n{body}")
        if not self.dedup.would_fire(dedup_key, self.ttl_sec):
            return False
        if self.tg:
            ok = bool(self.tg.send(text))
            if ok:
                self.dedup.mark_fired(dedup_key)
            return ok
        # tg yok (dry ortam): eski davranış — teslim edilmiş say ve kaydet.
        self.dedup.mark_fired(dedup_key)
        return True

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
