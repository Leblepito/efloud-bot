# Runbook: Circuit Breaker Reset (operatör-gated)

> **T-022 tabletop bulgusuyla oluşturuldu (2026-06-11):** iki dokümanda "breaker reset
> runbook'u" referans veriliyordu ama dosya yoktu. Mekanik: `POST /api/breaker/reset`
> (`backend/api.py:348`) → `breaker.manual_reset()` → durum OPEN + DB mirror + audit log.

## Ne zaman

healthz `200 {"status":"suspended","failures":["breaker_halted"]}` — breaker HALTED
(haftalık DD / emergency balance / ardışık kayıp eşiği). **Bu bir hata değil güvenlik
durağıdır:** restart ÇÖZMEZ (autoheal bilerek dokunmaz — `healthz-contract.md`).

## Reset ÖNCESİ zorunlu değerlendirme

1. **Kök nedeni anla:** hangi eşik tetiklendi? (`state/breaker.json` → `reason` alanı;
   dashboard status; alerter mesajı.)
2. Tetikleyen koşul hâlâ geçerliyse reset bir sonraki cycle'da YENİDEN trip eder
   (tasarım gereği — `api.py` docstring). Körü körüne reset etme; gerekiyorsa önce
   pozisyon/bakiye durumunu Binance'ten bağımsız doğrula.
3. Haftalık DD kaynaklı HALT'ta reset kararı = bilinçli risk kabulü → not düş (audit
   log'a `reason` parametresiyle geçer).

## Reset adımları

Bot container'ı portu host'a publish ETMEZ; erişim container içinden
(`reference: canlı bot API kontrolü`). Bot RUNNING olmalı — idle ise endpoint 503
döner: önce `/api/bot/start` (o da auth'lu, aynı mekanik).

```bash
# VPS'te — login + reset tek akışta (cookie secure=True → header'la taşınır):
docker exec efloud-bot python - <<'EOF'
import httpx, os
base = "http://localhost:8080"
pw = os.environ["DASHBOARD_PASSWORD"]
c = httpx.Client(base_url=base, timeout=10)
r = c.post("/api/login", json={"password": pw}); r.raise_for_status()
cookie = r.headers.get("set-cookie", "").split(";")[0]
r = c.post("/api/breaker/reset",
           params={"reason": "operator reset — <KÖK NEDEN NOTU BURAYA>"},
           headers={"Cookie": cookie})
print(r.status_code, r.json())
EOF
```

Alternatif: dashboard UI'daki breaker reset butonu (aynı endpoint'i çağırır).

## Reset SONRASI

1. `/healthz` → `{"status":"ok"}` doğrula (1-2 cycle bekle).
2. İlk cycle loglarını izle: yeniden trip ederse koşul geçerli demektir — tekrar
   reset ETME, kök nedene dön.
3. Olay P2 ise on-call playbook §3 post-incident notu düş.

## İlgili

- `engine/safety/breaker.py:230` — `manual_reset()` (state OPEN, sayaçlar sıfır)
- `docs/runbooks/healthz-contract.md` — suspended semantiği
- `docs/runbooks/crash-loop-recovery.md` — diğer `suspended` nedeni (crash_loop)
