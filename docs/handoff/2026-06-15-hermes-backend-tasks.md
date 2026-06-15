# 🟧 Hermes — Commercial MVP Backend Görevleri (2026-06-15 Sprint)

> Hazırlayan: @hermes (P-003 FAZ 3 ön-işleri)
> Öncelik sırası: **F → A → B → E → D**
> Her görev: branch + PR (master) + test. Claude'a "review" sinyali ver.
> UR-003 onayı zaten tamam (4×APPROVED_WITH_NITS, 0 blocker) — implementasyon dalgası açık.

## Sprint Durumu (15 Jun 06:30 — bu sabah itibarıyla)

| Görev | Önceki (11 Jun) | Şu an (15 Jun) | Aksiyon |
|---|---|---|---|
| **A** Supabase entitlements şema | DDL yazıldı (branch'te) | 🟡 PR AÇILMADI → patch + PR hazır | bugün operatör push + Claude review |
| **B** LS fizibilite + Railway env | Audit raporu yazıldı | 🟡 Operatör checklist'i (tüzel kişilik, deploy kaynağı) + Railway env placeholder eksik | env placeholder eklenecek, 2 operatör kararı bekliyor |
| **C** P-001 T-002/T-003 devamı | T-002 ✅ DONE (G-T2 PASS), T-003 R1+R3 patch'leri senkron | T-003 R1+R3 + çoklu-sembol gate re-run sırasında (sprint kapsamı dışı — gelir kritik yolu) | sprint dışı, ayrı track |
| **D** prod↔master reconcile | Runbook DRAFT | ✅ **KAPANDI** (13 Jun VPS master 1bf59c8'e senkron, BOT CANLI) | karar belgesi (bu dosya §1) |
| **E** Status page sağlayıcı | UptimeRobot Free kararı + JSON-parse stratejisi | 🟡 Monitör tanımı eksik (5dk operatör iş) | bugün 5dk iş |
| **F** Backup hedef + T-020 drill | T-020 scriptleri PR'da (e47a2bf) | 🟡 **CRITICAL**: Storage Box provision edilmedi, **encryption key ESCROW yapılmadı**, drill yapılmadı → **G-P3-6 blokerli** | bugün operatör: 2 adım + drill |

---

## GÖREV F (EN KRİTİK) — T-020 Backup Drill (G-P3-6 gate blokeri)

**Neden en başta?** T-020 kodları merge edildi (`e47a2bf`), backup cron kuruldu (15 3 * * *), 5 ardışık gün backup alındı. Ama **3-KİLİT eksik** → G-P3-6 (public proof yayını) kapalı, T-022 SLA belgesindeki RPO/RTO taahhütleri kanıtsız.

### Mevcut state (15 Jun 06:30)
- ✅ `/root/.efloud_backup.key` (64 byte base64, chmod 600) — **üretildi ama ESCROW YAPILMADI**
- ✅ `/etc/efloud-backup.env` (BACKUP_REMOTE=`<REDACTED>` placeholder) — **Hetzner Storage Box URL'si BOŞ**
- ✅ Cron: `15 3 * * * bash /opt/efloud-bot/deploy/backup/backup_state.sh >> /var/log/efloud-backup.log 2>&1`
- ✅ 5 ardışık backup `/var/backups/efloud/`'da (son: 15 Jun 03:15, 128KB şifreli)
- ✅ Runbook: `docs/runbooks/backup-restore.md` (5 bölüm: kurulum → restore drill → restore-to-LIVE → VPS total-loss → sınırlar)
- ❌ rclone remote: `storagebox:` configured (rclone listremotes çıktısı) ama **target path'i test edilmemiş** (off-VPS upload doğrulanmamış)
- ❌ Drill (restore_state.sh) hiç çalıştırılmadı
- ❌ Anahtar password manager'a kopyalanmadı → VPS total-loss senaryosu = **kilitli backup**

### Operatör aksiyonu (sırasıyla — 30dk iş)

#### Adım 1 — Encryption key ESCROW (5dk, KRİTİK)
```bash
# VPS terminalde (root@efloud-bot-prod):
cat /root/.efloud_backup.key
# → Çıktıyı password manager'a "efloud-bot / backup encryption key (v1, 2026-06-11)" olarak yapıştır
# → Terminali temizle: history -c && history -w
```
> ⚠️ UR-003 niti: VPS total-loss senaryosunda (2026-05-15 rebuild emsali) anahtar veriyle yok olursa **tüm şifreli backup'lar erişilemez**. Bu adım 5 dakika, drill'i açar.

#### Adım 2 — Hetzner Storage Box provizyonu (10dk)
1. Hetzner Cloud Console → Storage Boxes → **Create**:
   - Name: `efloud-backup-sbox`
   - Location: **Falkenstein/FSN1** (VPS ile aynı DC → hızlı + ucuz iç trafik)
   - Plan: **BX11** (1 TB) — backup büyümesine göre BX21'e upgrade
   - Snapshot access: **YES** (off-VPS read yetkisi)
2. Storage Box detaylarında:
   - **SSH host**: `uXXXXX.your-storagebox.de`
   - **Username**: `uXXXXX`
   - **Password**: ilk giriş sonrası reset istenir → **password manager'a kaydet** (Storage Box root şifresi, backup key'den AYRI)
3. rclone remote yapılandır (zaten `storagebox:` adıyla var, **host/credential güncelle**):
   ```bash
   rclone config show storagebox    # mevcut ayarı gör
   # Eğer type sftp değilse veya host yanlışsa:
   rclone config update storagebox host uXXXXX.your-storagebox.de
   rclone config update storagebox user uXXXXX
   rclone config update storagebox pass $(rclone obscure <PASSWORD>)
   ```
4. Test (yazma + okuma + silme):
   ```bash
   echo "drill-$(date +%s)" > /tmp/efloud-drill.txt
   rclone copy /tmp/efloud-drill.txt storagebox:efloud-backups/
   rclone ls storagebox:efloud-backups/efloud-drill.txt
   rclone delete storagebox:efloud-backups/efloud-drill.txt
   ```
5. `/etc/efloud-backup.env` güncelle (BACKUP_REMOTE'i gerçek path ile):
   ```bash
   sed -i 's|^BACKUP_REMOTE=.*|BACKUP_REMOTE=storagebox:efloud-backups|' /etc/efloud-backup.env
   cat /etc/efloud-backup.env | sed 's/=.*/=***/'    # sadece anahtar adları görünsün
   ```

#### Adım 3 — İlk off-VPS backup (5dk)
```bash
# Manuel tetikle
bash /opt/efloud-bot/deploy/backup/backup_state.sh
# Remote'a gitti mi kontrol
rclone ls storagebox:efloud-backups/ | tail -5
```

#### Adım 4 — Restore DRILL (10dk, G-P3-6 açar)
```bash
# En güncel backup'ı bul
ENC_FILE=$(ls -t /var/backups/efloud/*.enc | head -1)
echo "Restoring from: $ENC_FILE"

# SCRATCH volume'a restore (canlıya DOKUNMAZ)
bash /opt/efloud-bot/deploy/backup/restore_state.sh "$ENC_FILE"

# Doğrulama (script checklist'i doldurur):
#  - positions.json parse OK?
#  - breaker.json parse OK?
#  - journal satır sayısı > 0?
#  - sha256 doğrulandı?

# Temizlik
docker volume rm efloud_restore_drill_<ts>

# Drill sonucunu bu dosyanın §6'sına işle (PASS/FAIL)
```

#### Adım 5 — Raporlama (2dk)
Drill PASS ise:
- `docs/runbooks/backup-restore.md` §3'ün sonuna drill tarihi + PASS işareti
- `LLTODO/tasks/IN_PROGRESS/T-020-backup-restore.md` → `DONE/`'ya taşı
- SCOREBOARD: T-020 → ✅ DONE
- STATE.md: T-020 heartbeat (drill PASS) + G-P3-6 → AÇIK

Drill FAIL ise:
- Hata mesajını Claude'a gönder (log + script çıktısı)
- Restore script'inde düzeltme → T-020 kartı IN_PROGRESS'te kalır

### Acceptance
- [ ] Encryption key password manager'da (offline)
- [ ] Storage Box provision + rclone test PASS (write/read/delete)
- [ ] İlk off-VPS backup remote'a gitti
- [ ] Restore drill PASS (positions.json + breaker.json + journal doğrulandı)
- [ ] T-020 → DONE, G-P3-6 → AÇIK

---

## GÖREV A — Supabase Entitlements Şema PR

**Mevcut:** 2 SQL dosyası branch'te (c20cb05):
- `u2algo-site/supabase/entitlements.sql` (40 satır, UR-003 eki `expires_at` dahil)
- `u2algo-site/supabase/002_waitlist_consent.sql` (10 satır, KVKK/GDPR consent alanları)

**Eksik:** master'a PR AÇILMADI → W2'de (T-015) Supabase'de uygulanamaz.

### Yapılacak (bu sabah — 15dk iş)

#### 1) Branch + format-patch (Hermes — VPS'te)
```bash
cd /opt/efloud-bot
git status                            # 2 dosya untracked olmalı
git checkout -b feat/p003-w2-entitlements-schema
git add u2algo-site/supabase/entitlements.sql u2algo-site/supabase/002_waitlist_consent.sql
git commit -m "feat(p003-w2): Supabase entitlements + waitlist consent schema

- entitlements: u2algo paid-access tracking (T-015)
  - UR-003 eki: expires_at timestamptz NULL (abonelik/sepet opsiyonelliği)
  - service-role-only RLS
  - email/product/status index
- waitlist_leads consent: KVKK/GDPR uyumu (T-011)
  - consent boolean + consent_at timestamptz
  - mevcut satırlar NULL (retroaktif varsayım yok)

Refs: P-003 W2/T-015, P-003 W0/T-011, UR-003 niti #2/3"

# Format-patch + SHA256
git format-patch origin/master --stdout > /tmp/p003-w2-entitlements.patch
sha256sum /tmp/p003-w2-entitlements.patch
```

#### 2) Transfer (operatör)
- SCP ile lokal makineye: `C:\tmp\p003-w2-entitlements.patch`
- Lokal repo'da (efloud-bot veya ayrı u2algo-site — GÖREV B md.8 cevabına göre):
  ```bash
  git am /path/to/p003-w2-entitlements.patch
  git push -u origin feat/p003-w2-entitlements-schema
  # PR aç → master'a merge
  ```

#### 3) Acceptance
- PR merged
- Supabase SQL Editor'da `entitlements.sql` + `002_waitlist_consent.sql` çalıştırıldı (canlıya uygulanmadan önce staging'de dene)
- T-015 task → `DONE/`

### Açık soru (operatör kararı)
- **u2algo-site ayrı repo mu?** GÖREV B md.8 → bu PR nereye açılacak?

---

## GÖREV B — Railway Env + Operatör Checklist (LS Fizibilite)

**Mevcut:** `docs/audit/2026-06-11-lemonsqueezy-feasibility.md` (5 madde analiz, 4 ✅, 2 ⚠️/❓ operatör).

### Yapılacak

#### 1) Railway env placeholder (5dk, Hermes)
`u2algo-site/` reposunda (veya bu repoda — md.8 cevabına göre):
- `LEMONSQUEEZY_WEBHOOK_SECRET` placeholder env değişkeni eklenecek
- `.env.example`'a dokümantasyon yorumu

**Önemli:** Değer ASLA repo'ya girmez. Railway dashboard'dan manuel eklenir.

#### 2) Operatör checklist'i (zamanlama gerektirir)
| # | Karar | Sahip | Zaman |
|---|---|---|---|
| B.1 | **Tüzel kişilik**: Şahıs şirketi mi, ltd şirket mi? (düşük ciroda şahıs yeterli; vergi levhası LS identity verification ister) | Operatör | 1 hafta |
| B.2 | **TR satıcı payout**: Wise Business hesabı aç (USD/TRY, düşük kur farkı) | Operatör | 1 hafta |
| B.3 | **LS ürün taslağı**: Hesap + ilk ücretsiz ürün (TradingView indicator) oluştur; "yazılım aracı, yatırım tavsiyesi değildir" disclaimer | Operatör | 1 gün |
| B.4 | **Domain + e-posta**: Resend için domain kararı (M12'ye bağlı); SPF/DKIM/DMARC kurulumu | Operatör | Domain kararı sonrası |
| B.5 | **Deploy kaynağı teyidi**: u2algo-site bu repoda mı (vendored), ayrı repo mu? PR'lar nereye? | Operatör | 1 gün (kritik — A/B/E PR hedefi) |

#### 3) Acceptance
- Railway env placeholder PR merged
- B.1-B.5 checklist'i operatör tarafından dolduruldu
- LS ürün taslağı hazır (henüz YAYINLANMAZ — G-P3-B2 operatör onayı bekler)

### ⚠️ W2'ye GİRME GATE'İ
UR-003 eki: Aşağıdaki OLMADAN T-016 (LS webhook implementasyonu) BAŞLATILAMAZ:
- B.3 (LS ürün taslağı) ✅
- B.1 (tüzel kişilik kararı) ✅
- TR payout rayı teyidi ✅

---

## GÖREV E — UptimeRobot Free Monitör (5dk, operatör)

**Karar (zaten verilmiş):** UptimeRobot Free — keyword monitoring ile `/api/healthz` JSON `status` field parse. HTTP 200 + `status:"suspended"` = breaker tetiklendi → monitör DOWN sayar.

### Kurulum (5dk, operatör)

1. https://uptimerobot.com → **Register for FREE**
2. **+ Add New Monitor**:
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `efloud-bot healthz`
   - URL: `https://bot.ualgotrade.com/api/healthz`
   - Monitoring Interval: **5 minutes** (free tier minimum)
3. **Keyword** sekmesi (Authentication yerine):
   - ✅ "Monitor keyword" → **contains**
   - Value: `"status":"ok"`
   - Case sensitive: NO
4. **Alert Contacts** → Add → **Telegram**:
   - Bot token: operatör Telegram bot token'ı (EFLOUD_TELEGRAM_TOKEN ile aynı olabilir veya ayrı bir UptimeRobot botu)
   - Chat ID: operatör chat ID
5. **Status Page** sekmesi → Add → Public:
   - Subdomain: `efloud-bot` (→ `efloud-bot.statuspage.com`)
   - Title: `efloud-bot Status`
   - Monitör olarak `efloud-bot healthz`'yi seç
6. Save → **URL'yi** STATE.md'ye heartbeat olarak ekle

### Doğrulama
- 5dk sonra monitör "Up" göstermeli (keyword match)
- Manuel test: breaker tetikle → 5dk içinde "Down" olmalı
  - ⚠️ Canlı mainnet'te test etme — staging'de veya `force_suspended` query param ile dene (varsa)

### Acceptance
- Monitör URL'si STATE.md'ye işlendi
- Status page public URL'si operatöre teslim edildi
- T-021 task BACKLOG → IN_PROGRESS (@claude veya @hermes claim eder)

---

## GÖREV D — Prod↔Master Reconciliation KARAR BELGESİ ✅ KAPANDI

**Tarih:** 2026-06-13
**Runbook:** `docs/runbooks/2026-06-10-prod-master-reconciliation.md`

### Karar
- Prod VPS `feat/pr1-identity-tokens` @ `ca92ce7` → **master `1bf59c8`'e senkron edildi** (stash+checkout+pull+stash pop)
- Diff: master'da 11 commit (PR #172-#177) prod'a alındı + prod'daki `bebcc8c` u2algo token-sync master'da zaten merge edilmiş (PR #179)
- Push YOK: operatör `git push origin master` kendisi yapacak (VPS deploy key read-only)
- **Sonuç:** BOT CANLI + STABIL (3 gün healthy, healthz 200 OK)

### Risk kapatma
- ✅ State backup'lar `/var/backups/efloud/`'da 5 ardışık gün alınmış (cron kuruldu)
- ⚠️ Off-VPS backup hâlâ BEKLEMede (GÖREV F'in Adım 2-3'ü ile çözülecek)
- ✅ Breaker pre-existing HALTED durumu hâlâ operatör kararında (runbook §5)

### Acceptance
- VPS master HEAD = GitHub origin/master HEAD
- Container recreate + healthz 200
- Runbook "✅ DONE" olarak işaretlendi (13 Jun heartbeat, STATE.md)

---

## Özet Tablo — Operatör Aksiyonları (bugün, ~1 saat)

| Öncelik | Görev | Süre | Çıktı |
|---|---|---|---|
| 🟥 1 | GÖREV F (encryption key ESCROW) | 5dk | Password manager güncellendi |
| 🟥 1 | GÖREV F (Storage Box provizyon + drill) | 25dk | Off-VPS backup PASS + drill PASS |
| 🟧 2 | GÖREV A (Supabase PR push) | 5dk | `feat/p003-w2-entitlements-schema` PR açıldı |
| 🟨 3 | GÖREV E (UptimeRobot monitör) | 5dk | Status page public URL hazır |
| 🟨 3 | GÖREV B (B.5 deploy kaynağı cevabı) | 5dk | u2algo-site repo konumu net |

**Bugün bitince:** F + A + E + D = %100 kapalı. B operatör kararlarına bağlı (B.1-B.4 = 1 hafta). P-003 FAZ 3 başlangıcı için tek gerçek bloker **GÖREV F (drill PASS)**.

---

## Handoff Workflow (kural — 11 Jun GAP9 dersi)

Tüm dosya transferleri `git format-patch` + `sha256` + `git am` kalıbıyla. Telegram'a dosya içeriği YAPIŞTIRILMAZ.

```bash
# Hermes (VPS):
git format-patch origin/master --stdout > /tmp/X.patch
sha256sum /tmp/X.patch

# Operatör (Windows):
scp root@178.104.122.91:/tmp/X.patch C:\tmp\
git am C:\tmp\X.patch
git push -u origin feat/<branch>

# Claude (review):
sha256sum <indirilen-patch>   # Hermes'in sha256'sıyla karşılaştır
```
