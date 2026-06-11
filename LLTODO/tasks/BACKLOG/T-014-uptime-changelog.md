# T-014: Uptime Alanı + Public CHANGELOG + Site Updates Bölümü

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1 gün
**Bağımlılık:** T-012 (snapshot şemasına alan ekler)

## Hedef

Proof snapshot'a alerter heartbeat'ten türetilen uptime % alanı eklemek; müşteri-yüzlü CHANGELOG.md ve site updates bölümü açmak.

## Çıktılar

- [ ] `proof_export.py`'a uptime alanı — **UR-003 düzeltmesi:** tek-timestamp heartbeat'ten
      uptime YÜZDESİ türetilemez (yalnız anlık liveness) ve heartbeat ALERTER sidecar'ının
      canlılığıdır, trading bot'un değil. Kaynak **healthz-türevi sampling**: proof_export cron'u
      her koşuda healthz durumunu örnekleyip kendi birikim geçmişini tutar (T-024 kontratına göre
      `status:"suspended"` ayrı kategori — "servis up / trading suspended"); ya da alan
      "monitoring liveness" olarak adlandırılır. Tasarım T-024 ile birlikte pinlenir
- [ ] Repo köküne public `CHANGELOG.md` (Keep-a-Changelog formatı, müşteri diliyle)
- [ ] u2algo-site "updates" bölümü (changelog'dan beslenen statik liste)

## Acceptance Kriterleri

- [ ] Ayrı status-page servisi KURULMAZ (MVP'de snapshot alanı yeter)
- [ ] Changelog'da iç operasyon detayı / güvenlik hassas bilgi yok

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
