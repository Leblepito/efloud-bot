# GÖREV E: Status Page Sağlayıcı Değerlendirmesi (2026-06-11)

> **Görev:** P-003 W-R T-021 için public status page + harici uptime monitör sağlayıcı seçimi.
> **Kritik kısıt:** Probe, `/healthz` JSON `status` alanını parse edebilmeli.

---

## Değerlendirme

### 1. UptimeRobot Free — ✅ ÖNERİLEN (MVP)

| Özellik | Değer |
|---|---|
| Fiyat | **$0/ay** |
| Monitör sayısı | 50 |
| Kontrol aralığı | 5 dakika |
| Status page | Basic (markalı) |
| HTTP monitoring | ✅ |
| Keyword monitoring | ✅ (response body içerik kontrolü) |
| Alert kanalları | Email, Slack, Telegram, Webhook |

**JSON parse stratejisi:** Keyword monitoring ile `/healthz` response body'sinde `"status":"ok"` varlığı kontrol edilir. Breaker tetiklendiğinde `"status":"suspended"` döner → keyword eşleşmez → alert ateşlenir. HTTP 200 + suspended durumunu ayırt eder.

**Kurulum (5 dakika):**
1. UptimeRobot'a kaydol (ücretsiz)
2. HTTP(s) monitör ekle: `https://bot.ualgotrade.com/api/healthz`
3. Keyword filter: "contains" → `"status":"ok"`
4. Alert contact tanımla (Telegram, email)
5. Status page aktifleştir

**MVP sonrası upgrade:** Solo plan $9/ay → 60-sn interval, full-featured status pages.

---

### 2. BetterStack — ⚠️ MVP için pahalı

| Özellik | Değer |
|---|---|
| Fiyat | **$29/ay** (1 responder) |
| JSON path assert | ✅ native |
| Status page | ✅ premium |
| Kontrol aralığı | 30 saniye |
| Slack/Teams entegrasyonu | ✅ |

JSON path assertion native destekler (`$.status == "ok"`). Status page'leri daha şık. Ancak MVP için $29/ay gereksiz yüksek.

---

### 3. Gatus (self-hosted) — ❌ Efor yüksek

Açık kaynak, Docker'da çalışır, JSON path assertion yapabilir. Ancak:
- Self-hosted → ayrı container + monitoring zinciri
- Status page hosting gerekir
- MVP için ek operasyon yükü

---

## Karar: UptimeRobot Free

**Gerekçe:**
- JSON `status` alanını **keyword monitoring ile ayırt edebiliyor** (temel kısıt karşılanıyor)
- Ücretsiz, 5 dakikada kurulur
- MVP sonrası $9/ay'a upgrade path'i var
- Telegram alert entegrasyonu var (mevcut alert kanalıyla birleşir)

**Operatör aksiyonu:** UptimeRobot hesabı aç, monitör tanımla, status page URL'ini bildir.
