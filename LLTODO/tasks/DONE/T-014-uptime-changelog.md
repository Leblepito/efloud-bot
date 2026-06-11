# T-014: Uptime Alanı + Public CHANGELOG + Site Updates Bölümü

**Epic:** P-003
**Claimed by:** @claude (2026-06-11)
**Tahmini süre:** 1 gün
**Bağımlılık:** T-012 (snapshot şemasına alan ekler)

## Hedef

Proof snapshot'a alerter heartbeat'ten türetilen uptime % alanı eklemek; müşteri-yüzlü CHANGELOG.md ve site updates bölümü açmak.

## Çıktılar

- [x] `proof_export.py`'a uptime alanı — healthz-türevi sampling uygulandı (T-024
      kontratı §3): `uptime` bloğu = `{window_days, sample_count, service_uptime_pct,
      trading_active_pct}`; service=(ok+suspended)/n ayrı, trading=ok/n ayrı;
      0 örnek → None (sahte %100 yok). Whitelist'e `uptime` + alt-key seti eklendi,
      schema 1.0.0→1.1.0.
- [x] Repo köküne public `CHANGELOG.md` (Keep-a-Changelog formatı, müşteri diliyle)
- [x] u2algo-site "updates" bölümü — `scripts/changelog-to-updates.js` (sıfır bağımlılık)
      → `updates.json` (statik, commit'li) → `#guncellemeler` section (fetch-fail-safe:
      yüklenemezse bölüm gizli kalır). Nav linki eklendi.

## Acceptance Kriterleri

- [x] Ayrı status-page servisi KURULMAZ (MVP'de snapshot alanı yeter) — kurulmadı
- [x] Changelog'da iç operasyon detayı / güvenlik hassas bilgi yok (smoke compliance gate PASS)

## T-012 Devir Notları (2026-06-11)

- PF gösterimi: all-win kayıtta `profit_factor = 0.0` döner (journal.stats() paritesi) —
  public sayfada "0.0" felaket gibi okunur; display katmanında n/a sentinel'i kullan.
- Equity eğrisi anchor noktası ilk trade gününden BİR GÜN ÖNCEDİR (tarih çakışması yok).
- `uptime_samples.jsonl` birikimi T-012 cron'uyla başladı; alan tasarımı
  healthz-contract §3 (service_uptime_pct ≠ trading_active_pct — KARIŞTIRMA).

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W1 — UR-003 bekleniyor |
| 2026-06-11 | DONE ✅ | uptime bloğu (service_uptime ≠ trading_active, healthz-contract §3 pinli tasarım) + CHANGELOG.md + site #guncellemeler (changelog→updates.json statik besleme). proof_export 30/30 test (8 yeni), site smoke compliance PASS. T-012 devir notları uygulandı (PF n/a sentinel'i site render'ına kalan iş — proof sayfası yayını hâlâ G-P3-B4 operatör onayında). @claude |
