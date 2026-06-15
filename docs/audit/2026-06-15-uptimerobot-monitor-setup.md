# UptimeRobot Free Monitör Kurulum — Operatör Spec (5dk iş)

> **Amaç:** Public status page + harici uptime monitör (T-021 / P-003 W-R).
> **Karar:** UptimeRobot Free — keyword monitoring ile `/api/healthz` JSON `status` parse.
> **Neden Free:** $0/ay, 5dk kurulum, kritik kısıt (JSON parse) karşılanıyor.
> **Alternatif (ileride):** BetterStack $29/ay (native JSON path) — MVP sonrası.

---

## KRİTİK KISIT (Neden BetterStack Değil)

> ⚠️ **Yalnız HTTP koduna bakan monitör YANLIŞ "operational" gösterir!**

Efloud-bot `/api/healthz` iki farklı 200 durumu döner:

| Durum | HTTP | `status` field | Bot | Monitör göstermesi |
|---|---|---|---|---|
| Bot çalışıyor, trade aktif | 200 | `"ok"` | ✅ trading | **Up** ✅ |
| Bot çalışıyor ama breaker HALTED | 200 | `"suspended"` | ⛔ trade yok (günlük limit) | **Down** ⚠️ |
| Bot çalışmıyor (container down) | 503 | (yok) | ❌ kapalı | **Down** ✅ |

**Yanlış yaklaşım:** HTTP 200 → "operational" diyen monitör → breaker HALT iken müşteriye "her şey çalışıyor" yalan söyler.

**Doğru yaklaşım:** Response body'de `"status":"ok"` keyword araması → HALT durumunda keyword bulamaz → alarm.

---

## Kurulum Adımları (5dk)

### Adım 1 — Hesap (1dk)
1. https://uptimerobot.com → **Register for FREE**
2. Email doğrula

### Adım 2 — Monitör (2dk)
1. Dashboard → **+ Add New Monitor**
2. Form:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `efloud-bot healthz`
   - **URL (or IP)**: `https://bot.ualgotrade.com/api/healthz`
   - **Monitoring Interval**: `5 minutes` (free tier minimum)
3. **Advanced Settings**:
   - **Monitor Keyword**: ✅ (Authentication DEĞİL)
   - **Keyword Type**: `contains`
   - **Keyword Value**: `"status":"ok"`
   - **Keyword Case Sensitive**: ❌
4. **Save**

### Adım 3 — Telegram Alert (1dk)
1. **My Settings** → **Alert Contacts** → **Add Alert Contact**
2. Type: **Telegram** (ücretsiz)
3. Form:
   - **Telegram Bot Token**: EFLOUD_TELEGRAM_TOKEN (env'den al, veya ayrı bir UptimeRobot botu oluştur)
   - **Telegram Chat ID**: operatör chat ID (EFLOUD_TELEGRAM_CHAT_ID)
4. ✅ Test — Telegram'a "UptimeRobot test" mesajı gelmeli

### Adım 4 — Monitöre Alert ata (30sn)
1. Monitör listesinde `efloud-bot healthz` → **Alert Contacts** sütunu
2. **× → Add** → Telegram contact'ı seç

### Adım 5 — Public Status Page (1dk)
1. **Status Pages** (sol menü) → **+ Add Status Page**
2. Form:
   - **Subdomain**: `efloud-bot` (→ `efloud-bot.statuspage.com`)
   - **Name**: `efloud-bot Status`
   - **Monitörler**: `efloud-bot healthz`'yi seç
   - **Branding**: Logo yoksa skip
   - **Custom domain** (opsiyonel): ileride `status.ualgotrade.com` bağlanabilir
3. **Save** → public URL'yi kopyala

---

## Doğrulama

### İlk monitör check'i (5dk bekle)
- UptimeRobot dashboard'da `efloud-bot healthz` → **Up** (yeşil)
- Response time grafik dolmaya başlar

### Suspended durumu testi (Opsiyonel — CANLI MAINNET'TE YAPMA)
- `/api/healthz?force_suspended=true` varsa dene (varsa — bot source'unu kontrol et)
- Yoksa: **staging'de** dene veya sadece "HTTP 200 ama suspended" senaryosunu dokümante et, canlıda test etme
- 5dk içinde monitör **Down** (kırmızı) olmalı + Telegram'a "Monitor is down" mesajı gelmeli
- ✅ **Breaker'ı resetle** → 5dk sonra **Up** olmalı

### False-positive kontrol
- Telegram alert'leri geliyor mu? İlk hafta her alarmı kaydet, gerçek downtime mı yoksa keyword mismatch mi ayırt et.

---

## Kabul Kriterleri (T-021 → IN_PROGRESS)

- [ ] Monitör tanımlı, "Up" gösteriyor
- [ ] Telegram alert çalışıyor (test mesajı geldi)
- [ ] Status page public URL'si oluşturuldu
- [ ] URL STATE.md heartbeat'ine eklendi:
  ```
  2026-06-15  T-021 IMPL  @hermes  UptimeRobot Free monitör + status page → https://efloud-bot.statuspage.com
  ```
- [ ] `LLTODO/tasks/BACKLOG/T-021-status-page.md` → `IN_PROGRESS/`

---

## Yükseltme Yol Haritası (İleride)

| İhtiyaç | Çözüm | Maliyet |
|---|---|---|
| 1dk kontrol aralığı | Solo plan | $9/ay |
| 30sn kontrol aralığı + native JSON path | BetterStack | $29/ay |
| Birden fazla servis (alerter, overseer, dashboard) | UptimeRobot Pro (5 monitör) veya BetterStack | $29/ay |
| Custom domain (`status.ualgotrade.com`) | UptimeRobot Pro | $9/ay |
| Incident yönetimi (postmortem template) | BetterStack / Instatus | $29+/ay |

**MVP kararı:** UptimeRobot Free yeterli; ihtiyaç büyürse $9/ay Solo upgrade.

---

## Uptime Metriği (T-014 ile koordinasyon)

> T-014 (proof_export.py + public CHANGELOG) içindeki uptime bloğu:
> `service_uptime_pct = (ok_count + suspended_count) / total_count`
> `trading_active_pct = ok_count / total_count`

**Bu iki metriği KARIŞTIRMA:**
- Status page'te gösterilen: **service_uptime_pct** (bot ayakta mı?)
- Internal trading metriği: **trading_active_pct** (bot trade ediyor mu?)

Monitör `keyword: "ok"` → yalnız `ok_count`'u sayar → **trading_active_pct** ile uyumlu.
**Service_uptime_pct** için: heartbeat job'u (T-014'in önerdiği şekilde) suspended sample'larını da saymalı — bu monitör DEĞİL, ayrı bir internal sampling job'udur (`/app/state/uptime_samples.jsonl`).

---

## İlgili Dosyalar
- T-014 heartbeat task: `LLTODO/tasks/DONE/T-014-uptime-changelog.md`
- Healthz kontratı: `docs/runbooks/healthz-contract.md`
- T-021 task: `LLTODO/tasks/BACKLOG/T-021-status-page.md` (claim et, IN_PROGRESS'e taşı)
