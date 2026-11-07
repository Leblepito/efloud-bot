---
id: T-20261107-01
title: live-write gate — şemasız URL, httpie ve ssh üzerinden compose boşluklarını kapat
from: claude-code
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: T-20261106-06
created: 2026-11-07
touches_live: false
---

## Amaç
Güvenlik denetimi (T-20261106-06) fix PR'ı #1. `hooks/live_write_gate.py` canlı-yazma
benzeri Bash komutlarında "ask" döndüren backstop'tur; üç komut biçimi hiç görüş
döndürmüyordu. Değişiklik yalnız kapıyı **güçlendirir** (yeni "ask" yolları); hiçbir mevcut
"ask" yolu zayıflamaz, kapı hâlâ asla "allow" döndürmez.

## Kapatılan boşluklar
1. Şemasız bot kontrol URL'leri — `curl -X POST localhost:8000/api/bot/start`,
   `127.0.0.1:8080/...`, IP / noktalı host (curl şemasız URL kabul eder).
2. httpie — `http POST :8000/api/kill-switch`, `http POST <host>/api/...`.
3. `ssh` ile uzak host'a gönderilen compose durum değişikliği (`up/down/restart/...`),
   `-f`'li ya da `-f`'siz. VPS'te varsayılan `docker-compose.yml` de
   `container_name: efloud-bot` tanımladığı için `-f`'siz `up` prod container'ını
   değiştirebilir. Yerel `docker compose up -d` bilinçli olarak sessiz kalır (mevcut test).

## Beklenen çıktı (Definition of Done)
- [x] Önce failing testler (9 RED) → regex değişikliği → GREEN
- [x] Okuma komutları sessiz kalır (6 yeni + mevcut sessiz testler)
- [x] `tests/hooks` tamamı yeşil
- [x] Review (efloud-code-reviewer: APPROVE_WITH_NITS → 2 MAJOR + 2 MINOR aynı PR'da düzeltildi)

## Kısıtlar
- Yalnız `hooks/live_write_gate.py` + `tests/hooks/test_live_write_gate.py` + collab dosyaları.

## Log
- 2026-11-07 claude-code: RED 9 → GREEN; `tests/hooks` 90 passed; audit probe 8/8 ask, 12/12 okuma sessiz.
- 2026-11-07 claude-code: review düzeltmeleri — heredoc/çok satırlı uzak komut, tırnaklı `-f`, docker servis adı+port (`efloud-bot:8000`), `.ssh`/`ssh-keygen`/`status=up` yanlış alarmları; ssh…compose deseni ikiye bölündü + span 200 kr ile sınırlandı (kübik backtracking → 192 KB'de 0.04 sn; hook timeout = fail-open). RED 10 → GREEN; `tests/hooks`+`tests/collab` 164 passed.
- Takip (kapsam dışı, işaretlendi): önceden var olan `PROD_COMPOSE_RE` tek satırlık dev girdide karesel (192 KB ≈ 4.6 sn, timeout 10 sn altında).

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
