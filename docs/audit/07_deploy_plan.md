# 07 — Deploy Plan / Batch-Merge Runbook (efloud-bot)

> Operatör runbook'u. Audit + 26 atomik PR (#120–#145) master'a karşı hazır, hepsi
> **MERGEABLE + CI yeşil**. ⚠️ **master'a merge = Railway redeploy = canlı bot restart.**
> Tarih: 2026-06-03.

---

## 0. ALTIN KURAL
**Her master-merge Railway redeploy tetikler.** C1 (#127) sinyal-timing'i 1 bar
kaydırır → **flat-book (0 açık pozisyon) penceresi ŞART**. Bu yüzden TÜM batch
**tek bakım penceresinde, kitap flat iken** merge edilir → **tek redeploy**.
Tek tek merge ETME (her biri ayrı restart = gürültü + risk).

---

## 1. PR envanteri (öncelik sırasıyla)

| Grup | PR'lar | Canlı etki |
|---|---|---|
| Audit docs | #118 | yok (docs) |
| CI/infra/offline | #128 H2, #129 H1, #130 S2, #136 S6, #137 S2b, #138 S7, #139 S3, #140 S5, #143 F3.2 | yok (test/offline/opt-in/config-banner) |
| Kod fix (no flat-book) | #120 A1, #121 C2, #122 C4, #123 C9, #124 C6, #125 F3.6, #126 C5, #132 A2, #133 max_sl_atr, #134 A3, #135 A4, #141 C3, #142 C8, #144 C7, #145 F1 | runtime; sinyal-timing değişmez |
| **Flat-book ŞART** | **#127 C1** (forming-bar), **#131 S1** (conf 50→80) | sinyal davranışı değişir |

---

## 2. Aynı-dosya overlap grupları (sıralı merge + `gh pr update-branch`)

İlk merge master'ı değiştirir; aynı dosyaya dokunan sonraki PR'lar `gh pr
update-branch <n>` ile master'ı alır (çoğu **farklı-bölge → auto-merge**; ci.yml
yorumunda 1-satır manuel merge olabilir).

| Dosya | PR'lar | Not |
|---|---|---|
| `.github/workflows/ci.yml` | #128 → #129 | #128 önce; sonra `update-branch #129` (yorum bloğu çakışır, trivial) |
| `engine/agents/gemini_client.py` | #120, #132 | farklı satır (DEFAULT_MODEL vs except) |
| `engine/signals.py` | #120, #142 | farklı bölge (~236 vs ~681) |
| `engine/safe_orchestrator.py` | #122, #134, #135, #144, #145 | farklı bölge (load_ai_sentiment / _htf_slope / agent-ctx / v2 / notional) |
| `exchange/__init__.py` | #127, #141 | farklı bölge (fetch_ohlcv ~75 vs open_position ~1122) |
| `backtest/engine.py` + `metrics.py` | #130, #137 | trade_dicts→aggregate bölgesi; trivial merge |

---

## 3. Merge sırası (önerilen)

Flat-book penceresinde, sırayla:
1. **#118** (audit docs) — base'i tazeler.
2. **CI/infra/offline:** #128 → `update-branch #129` → #129 → #130 → #137 (update-branch if needed) → #136 → #138 → #139 → #140 → #143.
3. **Kod fix:** #120 → #132 (update-branch) → #121 → #122 → #134 (update-branch) → #135 (update-branch) → #144 (update-branch) → #145 (update-branch) → #123 → #124 → #125 → #126 → #133 → #141 (update-branch, exchange) → #142 (update-branch, signals).
4. **Flat-book kalemleri (en son):** #127 (C1) → #131 (S1).
> Sıra esnek (hepsi master-tabanlı, çakışmıyor); kural: aynı-dosya grubunda 2.+ PR'a `update-branch`. Conflict çıkarsa GitHub UI'da 1-satır çöz veya bana söyle.

---

## 4. Deploy sekansı (operatör)

1. **Binance'te 0 açık pozisyon doğrula** (flat-book). Bot'u durdur (idle).
2. Yukarıdaki sırayla tüm PR'ları merge et (tek master tazelemesi).
3. **Tek Railway redeploy** (master push otomatik tetikler) → container restart.
4. **AUTOSTART=0** → restart sonrası idle; **manuel start** et.
5. **Doğrula:** breaker durumu, ISOLATED+one-way+5x, **min_confluence=80** (S1),
   kapalı-bar analizi (C1 → fetch_ohlcv son bar kapalı), advisory WARNING-görünür (A2),
   gemini-2.0-flash (A1). İlk cycle + ilk trade'i izle.

---

## 5. Rollback
- Merge commit'lerini `git revert` + redeploy, **veya** Railway'de önceki imaja dön.
- **S1 hızlı rollback:** `config.phase2_1k.yaml` min_confluence 80→50 + redeploy.
- C1 rollback: #127 revert (forming-bar davranışına döner).

---

## 6. Bu batch'te OLMAYAN (kasıtlı)
- **S3/S5/S7/S2b/S6** canlı-wiring → backtest-validation-gated adoption (saf modüller merge olur ama canlı davranışı DEĞİŞTİRMEZ).
- **F2 gating-enable** → A1 sonrası ≥50-trade canlı shadow gözlemi gerektirir (`06_agent_team.md` ön-koşulları).
- **P3-5 cleanup** → `04_cleanup.md` sil/arşivle önerileri (operatör elle uygular).

---

## 7. Cross-model iş bölümü (referans)
- Claude: mimar + doğrulayıcı + merge-hazırlık (GitHub).
- Gemini (VSCode): Railway + Binance deploy operatörü.
- Operatör: flat-book onayı + bakım penceresi + start.
