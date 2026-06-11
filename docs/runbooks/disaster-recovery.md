# Runbook: Disaster Recovery (T-022 / P-003 W-R)

> **Amaç:** Üç felaket senaryosunun adım adım kurtarma prosedürü. Her senaryo gerçek
> deneyime dayanır (2026-05-15 VPS rebuild fiilen yaşandı ve kurtarıldı).
> **Tatbikat:** üç ayda bir tabletop (masa başı) + yılda bir Senaryo-1 gerçek drill
> (scratch volume — `backup-restore.md` §3). Sonuçlar bu dosyanın §5 log'una işlenir.
> **Ön koşullar:** T-020 backup'ı kurulu + anahtar ESCROW'da (operatör password manager).

## Senaryo 1 — State volume kaybı/bozulması (VPS ayakta)

**Belirti:** bot state okuyamıyor / `positions.json`-`breaker.json` bozuk / volume silinmiş.
**RTO hedefi: ≤ 1 saat.**

1. **TÜM stack'i durdur** — `docker compose -f docker-compose.prod.yml stop`
   (yalnız bot DEĞİL: alerter/overseer/routines da state'i RW mount eder).
2. Restore cron'larını geçici kapat: `crontab -l > /tmp/crontab.bak && crontab -l | grep -v efloud | crontab -`
   (geri alma: `crontab /tmp/crontab.bak`). TOCTOU — `backup-restore.md` §4 notu.
3. En güncel backup'ı seç: lokal `/var/backups/efloud/` veya Storage Box'tan `rclone copy`.
4. `backup-restore.md` §4 akışı: zorunlu pre-restore kopya → `EFLOUD_RESTORE_FORCE_LIVE=YES_I_UNDERSTAND`
   ile restore (3-kilitli script sha256 doğrular + volume'u temizleyip açar).
5. Doğrula: `positions.json`/`breaker.json` JSON parse; journal satır sayısı makul;
   torn son satır normaldir.
6. Stack'i başlat: `docker compose -f docker-compose.prod.yml start` (cron'ları da geri aç)
   → `/healthz` izle. **Pozisyon gerçeği Binance'ten reconcile edilir**
   (bot ground-truth'u exchange'dir) — restore edilen state bayatsa bot açılışta
   Binance'le hizalar; yine de açık pozisyonları dashboard + bağımsız ccxt ile ÇAPRAZ doğrula
   (2026-05-14 bare-positions dersi: TP/SL'siz pozisyon kalmadığını kontrol et).
7. Breaker durumu: restore edilen `breaker.json` HALTED ise ve bayatsa → operatör reset
   akışı: `docs/runbooks/breaker-reset.md` (kök neden değerlendirmesi ZORUNLU; restart
   çözmez, yalnız `POST /api/breaker/reset`). Asla otomatik resetleme.

## Senaryo 2 — VPS total-loss (2026-05-15 emsali)

**Belirti:** sunucu erişilemez/silinmiş/yeniden kurulmuş.
**Hedef: ≤ 1 iş günü.** (2026-05-15'te backup YOKTU ve her şey kaybedildi — T-020 bu
senaryoyu kapatmak için var.)

1. **Önce trade riskini kapat:** Binance'e bağımsız erişimle (operatör API anahtarı + ccxt
   veya Binance UI) açık pozisyonları ve emirleri kontrol et. Bot ölü = SL/TP emirleri
   exchange'de DURUYOR (bot onları borsaya koyar) — ama doğrula; korumasız pozisyon varsa
   manuel SL koy veya kapat. **Bu adım her şeyden önce gelir.**
2. Yeni VPS: `deploy/HETZNER_GUIDE.md` bootstrap (SSH key'i Hetzner paneline manuel
   yükle — `hetzner-ssh-access` notu: panelde kayıtlı değil).
3. Repo: `git clone` → master. `.env.production` secrets'ları operatörden
   (password manager — repo'da YOK, olmamalı).
4. Backup anahtarını **ESCROW'dan** `/root/.efloud_backup.key`'e koy (chmod 600).
5. Storage Box'tan backup çek + Senaryo 1 adım 3-5 ile volume'ları restore et.
6. DNS/Caddy: `bot.ualgotrade.com` A kaydı yeni IP'ye; Caddy sertifikayı otomatik alır
   (nip.io fallback: `<yeni-ip>.nip.io`).
7. `docker compose -f docker-compose.prod.yml up -d --build` → `.env.production`'da
   **`EFLOUD_AUTOSTART=0` olduğunu DOĞRULA** (kod varsayılanı 1'dir — satır env
   dosyasından gelmek zorunda; eksikse bot otomatik trade'e başlar!) → bot idle başlar
   → healthz/dashboard doğrula → operatör onayıyla start.
8. T-020 backup cron'unu YENİDEN kur (yeni makinede cron yok!) + alerter Telegram testi.

## Senaryo 3 — DB kaybı (Supabase)

**Mevcut durum:** prod **DB-LESS** (DATABASE_URL yok) — bu senaryo bugün fiilen no-op;
kayıt: file-state + journal zaten birincil. DB Track-A Faz 4'te etkinleştirilirse:

1. Supabase yönetilen günlük yedeği vardır → dashboard/CLI'dan restore.
2. `EFLOUD_AUTO_MIGRATE=1` ile migration zincirini taze projeye uygula (`backend/migrate.py`).
3. File-state birincil kalır (breaker/pozisyon); DB mirror best-effort — drift varsa
   file-state kazanır. Trade history backfill: journal'dan replay (Track-A Faz 4 kapsamı).

## 4. Senaryo dışı (bilinçli)

- **Exchange kesintisi:** healthz `exchange_ping_stale` → 503 → autoheal restart;
  süreklilik halinde breaker/operatör. DR değil, ops akışı.
- **Kod regresyonu:** rollback = önceki master'a deploy; DR değil, deploy akışı.

## 5. Tatbikat Logu

| Tarih | Tip | Senaryo | Sonuç | Not |
|---|---|---|---|---|
| 2026-06-11 | Tabletop (live-ops-sentinel, 22 adım × repo gerçeği) | S1+S2+S3 | ✅ PASS (2. tur) | 1. turda 2 BLOCKING: var olmayan "breaker reset runbook'u" referansı → `breaker-reset.md` oluşturuldu (mekanik api.py:348'den doğrulandı) + 3 advisory (AUTOSTART kod-default'u 1!, crontab/start komutları, heartbeat inceleme) → hepsi fix, 2. tur temiz |
| (sıradaki: T-020 VPS kurulumu sonrası gerçek drill — G-P3-6) | | | | |
