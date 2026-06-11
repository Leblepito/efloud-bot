# T-011: Waitlist KVKK/GDPR Consent Alanı

**Epic:** P-002
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 0.5 gün
**Bağımlılık:** T-010 (privacy policy metni linklenecek)

## Hedef

Waitlist formuna açık rıza checkbox'ı ekleyip kayıt payload'ına `consent` + `consent_at` alanlarını işlemek.

## Çıktılar

- [ ] `index.html` waitlist formuna consent checkbox (privacy.html linkiyle)
- [ ] `u2algo-site/server.js` kayıt payload'ına `consent: true` + timestamp
- [ ] Supabase `waitlist_leads` consent kolonları (Hermes GÖREV A migration taslağıyla koordineli)
- [ ] Test: consent'siz submit reddedilir / consent alanı 3'lü fallback zincirinde korunur

## Acceptance Kriterleri

- [ ] Supabase REST → direct PG → JSONL fallback zinciri bozulmadan çalışır (G-P2-4)
- [ ] Mevcut kayıtlar `consent=null` kalır (geriye dönük varsayım yok)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-002 W0 — UR-002 bekleniyor |
