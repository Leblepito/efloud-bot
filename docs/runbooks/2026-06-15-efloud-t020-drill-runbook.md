# T-020 Storage Box Drill — Operatör Runbook (15dk iş)

> **Amaç:** Off-VPS şifreli backup hedefi (Hetzner Storage Box) + encryption key ESCROW
> + ilk restore drill. GÖREV F + T-020 + G-P3-6 gate'i.
> **Operatör zamanı:** ~30dk (5dk + 10dk + 5dk + 10dk).
> **Risk:** SIFIR (drill scratch volume'da, canlıya dokunmaz).

## Ön Koşullar
- VPS: `ssh efloud-bot` (root)
- Backup cron çalışıyor: `crontab -l | grep backup_state.sh` → `15 3 * * * bash ...`
- Son 5 backup `/var/backups/efloud/`'da var
- `/root/.efloud_backup.key` (chmod 600) ve `/etc/efloud-backup.env` (chmod 600) mevcut

---

## ADIM 1 — Encryption Key ESCROW (5dk) 🟥 KRİTİK

> VPS total-loss senaryosunda (2026-05-15 rebuild emsali) anahtar veriyle yok olursa
> **tüm şifreli backup'lar erişilemez**. Bu adım drill'i açar.

```bash
# VPS'te:
cat /root/.efloud_backup.key
```

**Çıktıyı password manager'a şu entry olarak ekle:**

| Alan | Değer |
|---|---|
| Name | `efloud-bot / backup encryption key (v1)` |
| Username | (yok) |
| Password | (cat çıktısı — base64 string) |
| Notes | `Üretim: 2026-06-11 · openssl rand -base64 48 · Şifreleme: openssl enc -aes-256-cbc -pbkdf2 · Backup aracı: /opt/efloud-bot/deploy/backup/{backup,restore}_state.sh · OFFLINE ESCROW ZORUNLU` |

**Terminal temizle:**
```bash
history -c && history -w
clear
```

✅ Doğrulama: password manager'da entry var, VPS'te `cat` çalıştırıldı, terminal temiz.

---

## ADIM 2 — Hetzner Storage Box Provizyonu (10dk)

### 2.1 Hetzner Console'dan satın al

1. https://console.hetzner.com → **Storage Boxes** → **Create Storage Box**:
   - **Name**: `efloud-backup-sbox`
   - **Location**: **Falkenstein (FSN1)** ← VPS ile aynı DC
   - **Plan**: **BX11** (1 TB) → ihtiyaca göre BX21 (2 TB) / BX31 (5 TB)
   - **Access**: **SSH/SFTP** (rclone sftp backend)
   - **Snapshot access**: ✅ Yes (off-VPS read)
   - **Automatic snapshots**: ❌ Disabled (rclone ile kendimiz alıyoruz)

2. **Oluşturuldu** ekranında:
   - **Host**: `uXXXXX.your-storagebox.de` (X = rakam)
   - **Username**: `uXXXXX`
   - **Initial password**: gösterilen şifre → **password manager'a yeni entry olarak kaydet** (Storage Box root şifresi, backup key'den FARKLI)

### 2.2 rclone remote yapılandır (VPS'te)

```bash
# Mevcut remote'u gör (zaten `storagebox:` adıyla var)
rclone config show storagebox
```

**Eğer host/credential yanlışsa veya remote hiç yoksa:**

```bash
rclone config    # interactive — "n) New remote" → name: storagebox → type: sftp
                 # host: uXXXXX.your-storagebox.de
                 # user: uXXXXX
                 # pass: <password-manager'dan> (rclone obscure'la)
                 # Diğer: default
```

**Password obscure'la (script'le kullanmak için):**
```bash
echo -n '<PASSWORD>' | rclone obscure - > /root/.efloud-storagebox.pass
chmod 600 /root/.efloud-storagebox.pass
rclone config update storagebox_pass $(cat /root/.efloud-storagebox.pass) --field pass
```

### 2.3 Yazma + okuma + silme testi (3dk)

```bash
# Test dosyası oluştur
echo "efloud-drill-$(date +%s)" > /tmp/efloud-drill.txt

# Yaz
rclone copy /tmp/efloud-drill.txt storagebox:efloud-backups/

# Oku (listele)
rclone ls storagebox:efloud-backups/efloud-drill.txt

# Sil
rclone delete storagebox:efloud-backups/efloud-drill.txt

# Doğrula (boş olmalı)
rclone ls storagebox:efloud-backups/
```

✅ Doğrulama: yazma + okuma + silme üçü de PASS.

### 2.4 backup.env güncelle

```bash
sed -i 's|^BACKUP_REMOTE=.*|BACKUP_REMOTE=storagebox:efloud-backups|' /etc/efloud-backup.env

# Sadece anahtar adları görünsün (değer gizli)
cat /etc/efloud-backup.env | sed 's/=.*/=***/'
```

**Beklenen:**
```
BACKUP_REMOTE=***
BACKUP_RETENTION_LOCAL_DAYS=***
BACKUP_RETENTION_REMOTE_DAYS=***
EFLOUD_TELEGRAM_TOKEN=***
EFLOUD_TELEGRAM_CHAT_ID=***
```

---

## ADIM 3 — İlk Off-VPS Backup (5dk)

```bash
# Manuel tetikle
bash /opt/efloud-bot/deploy/backup/backup_state.sh
```

**Beklenen çıktı (son 10 satır):**
```
[INFO] Mounted 3 volume(s) read-only
[INFO] Compressed: efloud-bot_efloud_state_1k_20260615T<HATA>.tar.gz (125KB)
[INFO] Encrypted: efloud-bot_efloud_state_1k_20260615T<HATA>.tar.gz.enc
[INFO] Uploaded to storagebox:efloud-backups/ (3 files)
[INFO] Manifest written: efloud_backup_20260615T<HATA>.manifest
[INFO] Local retention: 7 days (deleted 0)
[INFO] Remote retention: 30 days (deleted 0)
[INFO] Backup completed successfully
```

**Remote'a gitti mi kontrol:**
```bash
rclone ls storagebox:efloud-backups/ | tail -10
```

✅ Doğrulama: 3+ dosya remote'ta listelendi (her volume için `.enc` + 1 manifest).

---

## ADIM 4 — Restore DRILL (10dk) 🎯 G-P3-6 AÇAR

```bash
# En güncel backup'ı bul
ENC_FILE=$(ls -t /var/backups/efloud/*.enc | head -1)
echo "Restoring from: $ENC_FILE"

# SCRATCH volume'a restore (canlıya DOKUNMAZ)
bash /opt/efloud-bot/deploy/backup/restore_state.sh "$ENC_FILE"
```

**Beklenen çıktı:**
```
[INFO] Backup file: <ENC_FILE>
[INFO] Encrypted size: 128KB
[INFO] Decrypting... OK
[INFO] Decompressing... OK
[INFO] Mounted to scratch volume: efloud_restore_drill_<TS>
[INFO] Validating...
  ✓ positions.json parse OK (3 open positions)
  ✓ breaker.json parse OK (state: HALTED)
  ✓ journal: 1247 lines
[INFO] sha256 verified: <sha256>
[INFO] DRILL PASSED — scratch volume '<name>' oluşturuldu
```

**Manuel doğrulama (script checklist'i doldurduktan sonra):**
```bash
SCRATCH_VOL=efloud_restore_drill_<TS>    # script çıktısından

# Scratch volume'u geçici container'a mount et
docker run --rm -v ${SCRATCH_VOL}:/data alpine:3 sh -c '
  echo "=== positions.json ==="
  cat /data/positions.json | head -20
  echo ""
  echo "=== breaker.json ==="
  cat /data/breaker.json
  echo ""
  echo "=== journal son 5 satır ==="
  tail -5 /data/trade_journal.jsonl
  echo ""
  echo "=== toplam dosya ==="
  find /data -type f | wc -l
'
```

✅ Doğrulama: positions.json parse, breaker.json parse, journal > 0 satır, sha256 verified.

**Temizlik:**
```bash
docker volume rm ${SCRATCH_VOL}
```

---

## ADIM 5 — Raporlama (2dk)

### Drill sonucu

**Tarih:** 2026-06-15
**Backup kaynağı:** `<ENC_FILE>`
**Süre:** `<BAŞLANGIÇ> → <BİTİŞ>`
**Sonuç:** ✅ **PASS** (veya ❌ FAIL — hata: ...)

### Yapılacaklar

Drill **PASS** ise:

1. `docs/runbooks/backup-restore.md` §3 sonuna ekle:
   ```
   ### Drill Geçmişi
   - 2026-06-15: PASS (off-VPS Storage Box + scratch volume, RTO ~5dk)
   ```

2. `LLTODO/tasks/IN_PROGRESS/T-020-backup-restore.md` → `DONE/`'ya taşı:
   ```bash
   mv LLTODO/tasks/IN_PROGRESS/T-020-backup-restore.md LLTODO/tasks/DONE/
   ```
   Task dosyasının sonuna "Drill: 2026-06-15 PASS" satırı ekle.

3. `LLTODO/SCOREBOARD.md` güncelle: T-020 → ✅ DONE.

4. `LLTODO/STATE.md` heartbeat ekle:
   ```
   2026-06-15  T-020 DONE ✅  @claude  G-P3-6 AÇIK — drill PASS, off-VPS Storage Box + 3-kilitli restore doğrulandı
   ```

5. Telegram'dan @claude'a review-onayı sinyali ver: "T-020 drill PASS, G-P3-6 açık".

Drill **FAIL** ise:
- Hata mesajını + log'u + script çıktısını @claude'a gönder
- T-020 kartı IN_PROGRESS'te kalır
- Restore script'inde düzeltme gerekebilir (volume-merge bypass, mount detection vb.)

---

## Hata Durumları

| Hata | Muhtemel neden | Çözüm |
|---|---|---|
| `rclone: connection refused` | Storage Box host/credential yanlış | ADIM 2.2'yi tekrar, rclone config show ile doğrula |
| `decrypt failed` | Encryption key yanlış veya bozuk | `cat /root/.efloud_backup.key` ile karşılaştır, password manager'dan yenile |
| `volume already exists` | Önceki drill'den kalmış | `docker volume rm efloud_restore_drill_*` |
| `sha256 mismatch` | Backup bozuk (upload kesilmiş) | Sonraki cron'u bekle veya manuel backup al |
| `permission denied` | backup.env'de BACKUP_REMOTE yanlış | `cat /etc/efloud-backup.env` kontrol |

---

## Kabul Kriterleri (T-020 → DONE)

- [ ] Encryption key password manager'da (offline, isim: "efloud-bot / backup encryption key (v1)")
- [ ] Storage Box provision + rclone test PASS (write/read/delete)
- [ ] `/etc/efloud-backup.env` BACKUP_REMOTE güncel
- [ ] İlk off-VPS backup remote'a gitti
- [ ] Restore drill PASS (positions + breaker + journal + sha256)
- [ ] T-020 → DONE/, SCOREBOARD + STATE güncel
- [ ] G-P3-6 AÇIK
