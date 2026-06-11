# T-012: Public Proof Snapshot Export (proof_export.py)

**Epic:** P-003
**Claimed by:** @claude (2026-06-11, T-023/T-024 emsali — R2 limiti: IN_PROGRESS'te T-020 var)
**Tahmini süre:** 1-2 gün
**Bağımlılık:** — (UR-003 onayı sonrası başlar)

## Hedef

`state/trade_journal.jsonl`'den yalnız oransal/aggregate metrik üreten, u2algo-site'ın statik servis edeceği `state/proof_snapshot.json` export routine'i yazmak.

## Çıktılar

- [ ] `scripts/routines/proof_export.py` (mevcut `scripts/routines/_base.py` routine kalıbı)
- [ ] Snapshot whitelist şeması: win_rate, profit_factor, max_dd_pct, trade_count, normalize % equity eğrisi, period
- [ ] Privacy testi: snapshot'ta mutlak bakiye / pozisyon büyüklüğü / sembol bazlı USDT alanı YOK
- [ ] Runbook notu: cron kurulumu (`docs/runbooks/routines-cron-setup.md` ek bölüm)

## Acceptance Kriterleri

- [ ] G-P3-1: whitelist dışı alan testi yeşil
- [ ] Bot API'si public'e AÇILMAZ — yayın statik dosya üzerinden
- [ ] Yayın öncesi operatör onayı (G-P3-B4)
- [ ] Cadence/granularity: snapshot ≥ günlük, equity günlük-kapanış, yalnız kapanmış trade'ler (G-P3-1 eki)

## UR-003 Düzeltmesi (2026-06-11)

⚠️ **max_dd_pct + normalize % equity eğrisi journal'dan TEMİZ türetilemez:** TradeSnapshot'ta
hesap bakiyesi alanı yok; DB-less emsal (`backend/api.py /api/equity`) 0-bazlı kümülatif-PnL
kurar — bunun üstünde peak-relative %DD yanıltıcıdır. Çözüm implementasyonda PİNLENMELİ:
(a) operatör-girdili baseline-equity (state dosyası) VEYA (b) R-multiple/return-bazlı eğri.
win_rate/profit_factor/trade_count sorunsuz (`engine/journal.py stats()` hazır).
Not: M11-supersession'daki "DB bağımlılığı çözüldü" iddiası yalnız trade-stats için geçerli.

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W1 — UR-003 bekleniyor |
| 2026-06-11 | IMPL | @claude — `scripts/routines/proof_export.py` (+runner kaydı) + 20 test. **Baseline-equity kararı operatörden alındı:** başlangıç bakiyesi referansı (`state/proof_baseline.json`, snapshot'a ASLA girmez) → gerçek %DD; eğri 1.0-normalize, günlük-kapanış, yalnız kapanmış trade (G-P3-1 cadence sınırı). Healthz sampling yan etkisi (T-024 tasarımı) `uptime_samples.jsonl`'a. Runtime whitelist guard + privacy testleri |
| 2026-06-11 | ✅ DONE | Bu PR merge'üyle. VPS adımları (baseline dosyası + günlük cron) `routines-cron-setup.md` §5 — operatör/Hermes; YAYIN T-014 + G-P3-B4 operatör onayı arkasında |
