# 🟦 Gemini — Entry-Slippage Validation Backtest RESUME (2026-06-15)

> Hazırlayan: Claude (Architect/Backend-orchestrator). Bitince Claude review edecek.
> Kurallar: canlı mainnet bot → feature-branch + PR/rapor, atomic, secrets sadece VPS
> `.env.production` / Railway env (repo'ya ASLA), destructive-op yok.

---

## 0. Bağlam & Karar (2026-06-15)

master tip = `eebe42b`. Operatör kararı: **entry-slippage validation backtest'ini
RESUME et.** Bu, zaten master'da olan zone-touch confirmation feature'ının
(PR #175, `12bac38`, default-safe `require_confirmation:true`, flag-OFF) **mainnet
flag-flip kararı için kanıt üreten** validation gate'idir. HALTED durumdaydı; şimdi
**öncelikli** açık backend işi.

**ÖN-KOŞUL DOĞRULANDI (Claude):** slippage telemetri alanları master `engine/journal.py`'de
HAZIR — `signal_entry_price`, `actual_fill_price`, `slippage_pct`, `ts_signal`, `ts_fill`
(satır 46-51 + upsert 159-164). Yani adverse slippage ÖLÇÜLEBİLİR.

Mevcut çalışman: lokal `experiment/entry-slippage-backtest` branch (commit'ler
`5370ed7` harness + `40b7203` UTC-localize fix; master'dan 2 ileri / 65 geri). Bu branch'i
**güncel master'a rebase et**, sonra GÖREV 1'i koştur.

Bu görevin tam orijinal spec'i: `docs/handoff/2026-06-10-gemini-open-tasks.md` → GÖREV 1.
Aşağısı onun güncellenmiş + re-aktive halidir.

---

## GÖREV 1 (ÖNCELİK) — SMC v2 backtest, iki mod, gate verdict

1. `experiment/entry-slippage-backtest`'i güncel master (`eebe42b`) üstüne **rebase** et
   (UTC-localize fix `40b7203` korunsun). Conflict'leri çöz.
2. SMC v2 backtest'i **iki modda** koştur, **≥6 ay, 10 sembol**
   (`configs/config.zone_touch_experiment.yaml` whitelist):
   - **Mode A:** `require_confirmation: true` (mevcut canlı davranış = baseline)
   - **Mode B:** `require_confirmation: false` (zone-touch immediate entry)
3. **Metrikler:** ortalama **adverse `slippage_pct`** (yön-işaretli: + = aleyhte),
   **PF**, win-rate, max-DD. Rejim ayır (trend/range/volatile), **rejim başına ≥100 trade**.
4. **GEÇİŞ EŞİĞİ (gate):**
   - Mode B, Mode A'ya kıyasla ortalama adverse slippage'ı **ölçülebilir şekilde DÜŞÜRMELİ**
   - **VE** PF'i Mode A'nın **~%5'i içinde** tutmalı.
   - PF >%5 düşerse VEYA WR anlamlı düşerse → **flag flip REDDEDİLİR** (gate FAIL).
5. **Sağlık kontrolleri (zorunlu):** inverted SL/TP satırı YOK, realized RR < `min_rr`
   satırı YOK, EXPIRED adaylar > stuck/never-resolved (state-machine liveness).
6. Çıktı: `comparison.json` + `docs/handoff/2026-06-15-entry-slippage-backtest-results.md`
   (gate PASS/FAIL **net** verdict). `backtest/evaluate_backtest_gates.py` benzeri
   verdict aracını kullan.

**Acceptance:** branch (rebased) + `comparison.json` + rapor (gate PASS/FAIL net,
rejim-bazlı tablo, sağlık kontrolleri temiz). → Claude review.

**⚠️ NOT — bu görevde mainnet flip YOK:** Backtest PASS olsa bile sıradaki kapı
**testnet shadow ≥2hf + operatör sign-off** (GÖREV 2). `require_confirmation:false`
canlı config'e ASLA bu görevde girmez. Canlı `configs/config.phase2_1k.yaml` DOKUNULMAZ.

---

## GÖREV 2 — Testnet shadow (GÖREV 1 PASS sonrası, ön-haber)

GÖREV 1 gate PASS verirse: `config.zone_touch_experiment.yaml` testnet'e deploy (Binance
**testnet** key, yalnız VPS/Railway env) → ≥2 hafta shadow → haftalık doğrulama raporu
(`slippage_pct` dolu, inverted yok, RR<min yok). → Claude review → operatör mainnet kararı.
(Detay: 2026-06-10 handoff GÖREV 2.)

---

### Bitince
branch + rapor (master base) + Claude'a "review" sinyali. Gate verdict'i LLTODO
scoreboard'a işlenecek. Diğer eski görevlerin (frontend #170, Kronos Phase 6/7) bu
oturumda DEVRE DIŞI — frontend ayrı Claude oturumunda, Kronos ertelendi. Tek odak: GÖREV 1.
