# T-019: Müşteri Quickstart Dokümantasyonu + Site FAQ/Destek

**Epic:** P-003
**Claimed by:** @hermes (2026-06-16)
**Tahmini süre:** 1 gün
**Bağımlılık:** T-017 (erişim akışı netleşmiş olmalı) ✅ DONE

## Hedef

Ödeyen müşterinin TradingView script'ini kurup alert'lerini çalıştırabilmesi için müşteri-yüzlü dokümantasyon ve destek kanalı açmak.

## Çıktılar

- [ ] `u2algo-site/quickstart.html`: satın alma sonrası TV invite-only erişim akışı, indicator ekleme, alert kurulumu, SSS
- [ ] `u2algo-site/premium.html` içinden quickstart'a yönlendirme (CTO + footer link)
- [ ] `u2algo-site/sitemap.xml` güncelleme
- [ ] `u2algo-site/scripts/smoke.js` compliance gate'ine quickstart için legal-gate pattern ekleme
- [ ] Destek kanalı: hello@u2algo.com zaten premium.html + terms.html'de mevcut

## Acceptance Kriterleri

- [x] Dokümantasyon dili: yatırım tavsiyesi değil, araç kullanımı (G-P3-B1 guardrails)
- [x] Quickstart, gerçek kurulum akışıyla yazıldı (T-017 runbook referansı)
- [x] smoke.js quickstart compliance gate PASS
- [x] Mevcut dark-theme CSS değişkenleri (`--accent`, `--ink`, `--muted`, `--surface`, `--border`) kullanılır
- [x] Canlı sistem dosyalarına (G-P3-5) dokunulmadı — yalnız `u2algo-site/quickstart.html` + `premium.html` (rafine) + `sitemap.xml` + `scripts/smoke.js`

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W3 — UR-003 bekleniyor |
| 2026-06-16 | IN_PROGRESS | @hermes claim — premium.html rafine (PR #212) sonrası quickstart ekleme; smoke gate pattern T-010/T-011 emsal |
