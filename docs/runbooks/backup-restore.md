# Runbook: State Backup & Restore (T-020 / P-003 W-R)

> **Amaç:** Prod VPS'teki named volume'ların (`efloud_state`, `efloud_state_1k`,
> `efloud_state_aggressive` — `trade_journal.jsonl`, `positions.json`, `breaker.json` dahil)
> günlük şifreli off-VPS yedeği + test edilmiş restore prosedürü.
> **Gate bağlantısı:** G-P3-6 — ilk public proof yayını, ilk restore tatbikatı PASS olmadan açılamaz.

## Hedefler (SLA girdisi — T-022)

| Metrik | Hedef |
|---|---|
| RPO (veri kaybı penceresi) | ≤ 24 saat (günlük cron) |
| RTO (state restore süresi) | ≤ 1 saat (drill ile doğrulanır) |
| Tatbikat sıklığı | İlk kurulumda 1× (G-P3-6) + üç ayda bir |

## 1. Kurulum (bir kez, VPS'te — Hermes GÖREV F ile koordineli)

```bash
# 1) Şifreleme anahtarı üret
openssl rand -base64 48 > /root/.efloud_backup.key
chmod 600 /root/.efloud_backup.key

# 2) ⚠️ ESCROW — ZORUNLU (UR-003): anahtarın kopyasını operatör password
#    manager'ına kaydet. VPS total-loss senaryosunda (2026-05-15 rebuild
#    emsali) anahtar veriyle birlikte yok olursa backup AÇILAMAZ.
#    Anahtar repo'ya / chat'e / Telegram'a ASLA girmez.
cat /root/.efloud_backup.key   # → password manager'a yapıştır, terminali temizle

# 3) Off-VPS hedef (GÖREV F kararı: Hetzner Storage Box önerilir)
apt-get install -y rclone
rclone config   # ör. "storagebox" adlı sftp remote

# 4) Konfig dosyası
#    ⚠️ ZORUNLU: BACKUP_REMOTE bu işe ADANMIŞ bir path olmalı (retention
#    prune o path'in tamamında *.enc/*.manifest siler — paylaşılan path'te
#    başka yedekleri yer).
cat > /etc/efloud-backup.env <<'EOF'
BACKUP_REMOTE=storagebox:efloud-backups
BACKUP_RETENTION_LOCAL_DAYS=7
BACKUP_RETENTION_REMOTE_DAYS=30
# Başarısızlık alarmı için (alerter ile aynı değerler):
EFLOUD_TELEGRAM_TOKEN=<token>
EFLOUD_TELEGRAM_CHAT_ID=<chat-id>
EOF
chmod 600 /etc/efloud-backup.env

# 5) Smoke + ilk koşu
bash /opt/efloud-bot/deploy/backup/backup_state.sh --dry-run
bash /opt/efloud-bot/deploy/backup/backup_state.sh

# 6) Cron (günlük 03:15 UTC — bot cycle'larıyla çakışma derdi yok; mount :ro)
crontab -l | { cat; echo "15 3 * * * bash /opt/efloud-bot/deploy/backup/backup_state.sh >> /var/log/efloud-backup.log 2>&1"; } | crontab -
```

## 2. Güvenlik değişmezleri

- Snapshot container'ı volume'ları **`:ro`** mount eder — canlı state'e yazma fiziken imkânsız.
- `trade_journal.jsonl` append-only: canlı yazım sırasında alınan snapshot'ta **kesik (torn)
  son satır tolere edilir** — restore sonrası `tail -1` parse hatası beklenen durumdur, veri
  kaybı değildir.
- Staging disk doluluğu kontrol edilir (`BACKUP_MIN_FREE_MB`, default 1 GB) — disk dolarsa
  script backup'ı REDDEDER (dolu disk canlı journal yazımını etkilerdi; alarm atılır).
- Başarısızlıkta Telegram alarmı (`🔴 efloud backup FAILED: ...`) + `last_backup_status.json`.

## 3. Restore tatbikatı (drill — G-P3-6 + üç aylık)

```bash
# En güncel backup'ı bul (lokal staging veya rclone'dan indir)
ls -t /var/backups/efloud/*.enc | head -3

# SCRATCH volume'a restore (canlıya DOKUNMAZ — default mod)
bash /opt/efloud-bot/deploy/backup/restore_state.sh \
  /var/backups/efloud/<dosya>.tar.gz.enc

# Script çıktısındaki checklist'i doldur; sonucu T-020 kartının Log'una işle.
# Temizlik: docker volume rm efloud_restore_drill_<ts>
```

## 4. Restore-to-LIVE (felaket senaryosu — OPERATÖR-GATED)

> Yalnız gerçek veri kaybında. Sıradan sorunlarda ASLA. Üç güvenlik kilidi var:
> canlı volume adı + sentinel, target'ı mount eden HERHANGİ bir çalışan container,
> mevcut-volume merge reddi → script reddeder.

```bash
# 1) TÜM stack'i durdur — sadece bot DEĞİL: alerter/overseer/routines da
#    efloud_state'i RW mount eder; çalışırken restore = bozuk volume.
#    Ayrıca restore süresince host cron'larındaki compose-run job'larını
#    (daily-report / routines-scheduled / overseer-scheduled) geçici devre
#    dışı bırak — mount-guard'dan sonra başlayan cron TOCTOU penceresi açar.
cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml stop

# 2) ZORUNLU: mevcut (bozuk da olsa) içeriğin pre-restore kopyası — script
#    forced modda volume'u extract öncesi TEMİZLER, geri dönüş bu kopyadır
pre="efloud_state_pre_restore_$(date +%s)"
docker volume create "$pre"
docker run --rm -v <proje>_efloud_state:/src:ro -v "$pre":/dst alpine:3 cp -a /src/. /dst/

# 3) Zorla restore (script: mount-kontrol + temizle + extract + sha256 doğrulama)
EFLOUD_RESTORE_FORCE_LIVE=YES_I_UNDERSTAND \
  bash deploy/backup/restore_state.sh <dosya>.enc <proje>_efloud_state

# 4) Doğrula (positions.json/breaker.json parse + journal satır sayısı) → stack'i başlat
docker compose -f docker-compose.prod.yml start
# 5) /healthz + ilk cycle loglarını izle; pozisyon reconcile'ı Binance'ten gelir
```

## 5. VPS total-loss (DR — T-022 disaster-recovery.md ile birlikte)

1. Yeni VPS: `deploy/HETZNER_GUIDE.md` ile bootstrap.
2. Anahtarı **password-manager escrow'undan** `/root/.efloud_backup.key`'e geri koy (chmod 600).
3. Backup'ları Storage Box'tan çek: `rclone copy storagebox:efloud-backups/ /var/backups/efloud/ --include "*_<en-güncel-ts>*"` (remote düz/flat tutulur)
4. §4'teki akışla volume'ları restore et → `.env.production` secrets'ları operatörden → bot start.
5. Not: breaker HALT durumu restore edilen `breaker.json`'dan gelir; bayatsa operatör reset
   runbook'u uygulanır.

## 6. Bilinen sınırlar

- `efloud_logs` / `efloud_reports` / `efloud_data` yedeklenmez (yeniden üretilebilir;
  istenirse `BACKUP_VOLUMES`'a eklenir).
- DB (Supabase) bu runbook'un dışında — Supabase kendi günlük yedeğini tutar (prod şu an DB-less).
- Backup penceresinde yazılan son journal satırı kesik olabilir (yukarıda; kabul edilmiş).
