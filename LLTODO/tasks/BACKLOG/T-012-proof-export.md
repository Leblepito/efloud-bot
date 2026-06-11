# T-012: Public Proof Snapshot Export (proof_export.py)

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
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
