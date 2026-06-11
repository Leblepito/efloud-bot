# T-014: Uptime Alanı + Public CHANGELOG + Site Updates Bölümü

**Epic:** P-002
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 1 gün
**Bağımlılık:** T-012 (snapshot şemasına alan ekler)

## Hedef

Proof snapshot'a alerter heartbeat'ten türetilen uptime % alanı eklemek; müşteri-yüzlü CHANGELOG.md ve site updates bölümü açmak.

## Çıktılar

- [ ] `proof_export.py`'a uptime alanı (`state/alerter_heartbeat.json` yaşından türetilir)
- [ ] Repo köküne public `CHANGELOG.md` (Keep-a-Changelog formatı, müşteri diliyle)
- [ ] u2algo-site "updates" bölümü (changelog'dan beslenen statik liste)

## Acceptance Kriterleri

- [ ] Ayrı status-page servisi KURULMAZ (MVP'de snapshot alanı yeter)
- [ ] Changelog'da iç operasyon detayı / güvenlik hassas bilgi yok

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-002 W1 — UR-002 bekleniyor |
