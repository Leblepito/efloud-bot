# 🟦 Gemini — Açık Görevler (2026-06-10)

> Hazırlayan: Claude (Architect/Review). Bu dosya senin elindeki açık işleri
> bitirmen için. Bitince Claude review edecek. Kurallar: canlı mainnet bot →
> feature-branch + PR, atomic commit, secrets sadece VPS `.env.production`,
> destructive-op yok, deploy öncesi flat-book + operatör onayı.

Bağlam: efloud-bot canlı mainnet, sorunsuz çalışıyor. Strateji "bir süre açık
işleri bitirip master'a deploy etmek". master tip = `1f38998` (PR #174 frontend
fix + PR #175 entry-slippage atomic merged).

---

## GÖREV 1 (ÖNCELİK) — Entry-slippage rollout: backtest gate
**Durum:** PR split BİTTİ → #175 master'da (default-safe, `require_confirmation:true`).
Sıradaki adım backtest gate. Kod zaten master'da; sen sadece deneyi koştur + raporla.

**Yapılacak:**
1. master'dan `experiment/entry-slippage-backtest` branch aç.
2. SMC v2 backtest'i **iki modda** koştur, ≥6 ay, 10 sembol (experiment config'deki whitelist):
   - Mode A: `require_confirmation: true` (mevcut davranış, baseline)
   - Mode B: `require_confirmation: false` (zone-touch immediate)
3. Metrikler: ortalama **adverse slippage_pct** (yeni telemetri alanı, `engine/journal.py`),
   **PF**, win-rate, max-DD. Regime ayır (trend/range/volatile), regime başına ≥100 trade.
4. **Geçiş eşiği (gate):** Mode B, Mode A'ya kıyasla ortalama adverse slippage'ı
   ölçülebilir şekilde DÜŞÜRMELİ **VE** PF'i Mode A'nın ~%5'i içinde tutmalı.
   PF >%5 düşerse veya WR anlamlı düşerse → flag flip REDDEDİLİR.
5. `comparison.json` + `docs/handoff/2026-06-10-entry-slippage-backtest-results.md`
   üret. `backtest/evaluate_backtest_gates.py` benzeri verdict aracını kullan.

**Acceptance:** branch + comparison.json + rapor (gate PASS/FAIL net), inverted
SL/TP veya sub-min-RR satırı YOK. → Claude review.

**NOT:** Mainnet flag-flip (`require_confirmation:false` canlıda) bu görevde DEĞİL.
Backtest PASS olsa bile sıradaki kapı testnet shadow ≥2hf + operatör sign-off.

**Ref:** quant review validation plan (bu oturum), `configs/config.zone_touch_experiment.yaml`,
`docs/handoff/2026-06-08-entry-slippage-gemini-rollout-tasking.md`.

---

## GÖREV 2 — Entry-slippage testnet shadow (GÖREV 1 PASS sonrası)
1. `config.zone_touch_experiment.yaml`'i testnet'e deploy (Binance **testnet** key,
   sadece VPS `.env.production` / Railway env — repo'ya ASLA).
2. ≥2 hafta shadow çalıştır. `trade_journal.jsonl` doğrula: her entry'de
   `slippage_pct` dolu, inverted SL/TP yok, realized RR < min_rr yok,
   EXPIRED adaylar > stuck/never-resolved (state-machine liveness).
3. Haftalık özet → `docs/handoff/`.

**Acceptance:** 2hf testnet logu + doğrulama raporu. → Claude review → sonra
operatör mainnet kararı.

---

## GÖREV 3 — Frontend dashboard PR #170 (DRAFT, CONFLICTING)
**Durum:** master'a göre conflicting + #3 görsel onay bekliyor.
1. #170'i güncel master'a (`1f38998`) **rebase** et, conflict'leri çöz.
   ⚠️ NUMERIC alanları `Number()` ile sarmalı kuralını koru (PR #174 fix'i ezme).
2. `npm run build` yeşil + localhost:3000 preview ekran görüntüleri → görsel onay için hazırla.
3. CI py3.11 yeşile dönsün.

**Acceptance:** #170 rebased, build yeşil, preview screenshot'lar. → operatör görsel onay → Claude merge review.

---

## GÖREV 4 (İKİNCİL) — Kronos advisory Phase 6/7
Memory: Claude Phase 0-5'i hardened etti (working-tree, commit edilmemiş).
Phase 6 (Binance feed) + Phase 7 (frontend) sende. **ÖN-KOŞUL:** Phase 0-5
working-tree'sinin commit'lenip branch'e push'lanması gerekiyor — Claude'dan
o branch'i iste, üstüne Phase 6/7 ekle. Branch yoksa bu görevi GÖREV 1-3'ten
sonraya bırak.

---

### Bitince
Her görev için: branch + PR (master base) + test/rapor. Claude'a "review" sinyali
ver. Açık iş kalmayınca scoreboard'a (LLTODO) kaydet.
