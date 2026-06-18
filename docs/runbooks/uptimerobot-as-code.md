# Runbook: UptimeRobot Monitör + Status Page — As-Code (T-021 / P-003 W-R)

> **Amaç:** Public uptime monitörü + status page'i tek komutla, idempotent şekilde
> kurmak. Monitör tanımı dashboard'da elle değil, repo'da kod olarak yaşar
> (`ops/uptimerobot/monitors.yaml`) → dashboard asla "drift" etmez.
>
> **Sağlayıcı kararı:** UptimeRobot Free — `docs/audit/2026-06-11-status-page-provider-eval.md`
> **Healthz kontratı (neden keyword monitör):** `docs/runbooks/healthz-contract.md`
> **Elle kurulum (alternatif/eski):** `docs/audit/2026-06-15-uptimerobot-monitor-setup.md`

---

## Bileşenler

| Dosya | Rol |
|---|---|
| `ops/uptimerobot/monitors.yaml` | Monitör + status page tanımı (source of truth) |
| `scripts/setup_uptimerobot.py` | Idempotent uygulayıcı (create-or-update) |
| `tests/scripts/test_setup_uptimerobot.py` | Birim testler (API mock'lu, ağ erişimi YOK) |

Script ne yapar: `friendly_name`'e göre eşler → varsa **editMonitor**, yoksa
**newMonitor**. Tekrar çalıştırmak duplicate üretmez, mevcut tanımı config'e
yakınsatır.

---

## KRİTİK KISIT (neden keyword monitör, düz HTTP değil)

`/api/healthz` İKİ farklı 200 durumu döner:

| Durum | HTTP | `status` | Monitör |
|---|---|---|---|
| Bot çalışıyor, trade aktif | 200 | `"ok"` | **UP** ✅ |
| Bot ayakta, breaker HALTED | 200 | `"suspended"` | **DOWN** ⚠️ (trade durdu) |
| Container down | 503 | (yok) | **DOWN** ✅ |

Config `keyword: '"status":"ok"'` + `keyword_alert_when: absent` →
UptimeRobot `keyword_type=2` ("keyword yoksa DOWN"). Böylece HALT iken
müşteriye "operational" yalanı söylenmez. (HTTP koduna bakan monitör bunu
ayırt EDEMEZ.)

---

## Operatör Adımları

### Adım 0 — Dry-run ile planı gör (key gerektirmez)

```bash
python scripts/setup_uptimerobot.py --dry-run
```

Uygulanacak monitör + status page planını yazdırır, sıfır API çağrısı yapar.
Config'i değiştirip tekrar çalıştırarak doğrula.

### Adım 1 — Hesap (1 dk) — SADECE OPERATÖR

1. https://uptimerobot.com → **Register for FREE**
2. E-posta doğrula

### Adım 2 — API key al (30 sn)

1. **My Settings** → **API Settings**
2. **Main API Key** → **Create** (yoksa) → kopyala (`u123456-...`)

> ⚠️ Key bir sırdır. Repo'ya / config'e / commit'e **YAZMA**. Yalnız ortam
> değişkenine koy. (Bkz. secret-handling kuralı.)

### Adım 3 — (Opsiyonel ama önerilen) Telegram alert contact

Alert routing'i as-code yapamıyoruz çünkü Telegram contact bot token'ı (sır)
ister. Bir kereye mahsus dashboard'dan:

1. **My Settings** → **Alert Contacts** → **Add Alert Contact** → **Telegram**
2. Bağla, **Test** ile mesaj geldiğini doğrula.
3. Contact'ın **numeric ID**'sini al: `getAlertContacts` API'siyle veya
   contact URL'inden.
4. ID'yi `ops/uptimerobot/monitors.yaml` → `defaults.alert_contact_ids`'e ekle:
   ```yaml
   defaults:
     alert_contact_ids: [123456]   # Telegram contact ID
   ```
5. Script'i tekrar çalıştır (Adım 4) → monitör artık o contact'a alarm yollar.

Boş bırakırsan monitör kurulur ama alarm rotası olmaz (script uyarır).

### Adım 4 — Uygula (10 sn)

```bash
export UPTIMEROBOT_API_KEY='u123456-...'        # bash
# PowerShell:  $env:UPTIMEROBOT_API_KEY = 'u123456-...'

python scripts/setup_uptimerobot.py
```

Çıktı her monitör/status page için `created` veya `updated` + ID gösterir.

> Status page'i atlamak istersen: `--skip-status-pages`.
> Farklı config: `--config path/to/monitors.yaml`.

### Adım 5 — Doğrulama

1. UptimeRobot dashboard → `efloud-bot healthz` → bir interval (5 dk) sonra
   **Up** (yeşil) olmalı.
2. Status page public URL'ini dashboard'dan al (**Status Pages** → ilgili sayfa).
3. Telegram contact bağladıysan: monitör listesinde alarm rotasının atandığını gör.
4. URL'i STATE.md heartbeat'ine ekle:
   ```
   <tarih>  T-021 LIVE  @operator  UptimeRobot Free monitör + status page -> <public-url>
   ```

### Suspended senaryosu testi — ⚠️ CANLI MAINNET'TE YAPMA

Breaker'ı canlıda kasıtlı tetikleme. Staging varsa orada; yoksa healthz
kontratını (yukarıdaki tablo) referans göstererek dokümante et. Detay:
`docs/audit/2026-06-15-uptimerobot-monitor-setup.md` "Doğrulama" bölümü.

---

## Yükseltme yolu

| İhtiyaç | Çözüm | Maliyet |
|---|---|---|
| 60 sn interval | UptimeRobot Solo | $9/ay |
| Native JSON path assert + şık status page | BetterStack | $29/ay |
| Custom domain (`status.ualgotrade.com`) | UptimeRobot Pro | $9/ay |

Config'de `interval_seconds` ve `custom_domain` parametrik — plan yükseltince
sadece YAML'i değiştir + script'i tekrar çalıştır.
