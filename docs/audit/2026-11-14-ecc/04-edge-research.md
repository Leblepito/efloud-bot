# 04 — Backtest, Edge ve Araştırma Kararları İnceleme Raporu (2026-11-14)

> Kök: `C:/tmp/wt-ecc-audit` @ `81c2cf7` (origin/master). Salt okuma; backtest KOŞULMADI.
> Bakış: backtest-runner + quant analyst. Etiketler: **KANITLI** (NET-cost ölçümü var, işaret
> tutarlı), **KANITSIZ** (ölçüm yok / n<30 / tek pencere / outcome-filtreli), **ÇÜRÜTÜLMÜŞ**
> (NET-cost ölçümü negatif ya da gate'i geçemedi). Secret içeren dosya: `.env.production`
> (değeri okunmadı; `EFLOUD_CONFIG_PATH` ve `EFLOUD_SIGNAL_LEDGER_ENABLED` orada set edilebilir).

---

## 1. Envanter (ne var, ne işe yarıyor, canlı mı/ölü mü/shadow mu)

| Bileşen | Ne işe yarar | Durum | Kanıt |
|---|---|---|---|
| `backtest/engine.py` | Gerçek `SafeOrchestrator.run_cycle()` ile bar-bar replay; TP1 %50→BE→TP2; NET maliyet config'ten; LLM/agent/Kronos kapalı; `fvg_entry` zorla `off` | **Canlı araç** (2026-10-31'de silindi `562a6a3`, 2026-11-07 geri geldi PR #335) | `backtest/engine.py:124-134`, `:171-172`, `:382-383`, `:418-445` |
| `backtest/cli.py` | `single` / `portfolio` / `grid` / `compare` (v1↔v2) | Canlı; pencere sonu = `time.time()` (sabit uç yok) | `backtest/cli.py:34`, `:286-312` |
| `backtest/grid.py` | Parametre ızgarası | Varsayılan **seri** (`--workers 1`); ProcessPool Win/py3.14'te kilitleniyor | `backtest/cli.py:304-305`, `backtest/grid.py:108-119` |
| `backtest/memo.py` | HTF/günlük analiz memo'su (yalnız backtest), 2.1× hız | Canlı (#336), byte-identical kapısı | `TESTS.md:171` |
| `backtest/slippage.py` | Bacak başı ters fill: giriş 5bp, SL 10bp, TP 5bp | Canlı | `backtest/slippage.py:8-10` |
| `backtest/compare_live.py` | Canlı journal ↔ backtest eşleştirme (bilgi amaçlı, gate değil) | Canlı | parity raporu `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:41-45` |
| `backtest/comparison.py` `DEFAULT_GATES` + `scripts/evaluate_backtest_gates.py` | v1↔v2 göreli kapı (WR, avg RR, DD, stop-hunt, sharpe) → exit 0/1/2 | Kod canlı, **içerik bayat** (v1 canlı sembollerde susturulmuş; NET PF/OOS kapısı yok) | `backtest/comparison.py:26-32`, `scripts/evaluate_backtest_gates.py:2-12` |
| `backtest/montecarlo.py` `walk_forward_split` | IS/OOS bar-aralığı | Var, CLI'ye bağlı değil (DOĞRULANMADI: hiçbir CLI alt komutu çağırmıyor) | `backtest/montecarlo.py:78-82` |
| `engine/signal_ledger.py` + `edge_costs.py` + `edge_metrics.py` + `scripts/routines/{resolve_signals,edge_report}.py` | Edge Measurement Core (PR #227): her sinyali kaydet → shadow-resolve → NET R, Wilson CI | **Ölü**: `signal_ledger.enabled: false`; üstelik hook v1 yolunda → 10 v2 sembolünde hiç tetiklenmez (bkz. §2) | `configs/config.phase2_1k.yaml:467-468`, `engine/safe_orchestrator.py:1486-1497` vs `:1567` |
| `engine/report.py` | Efloud tarzı doğal dil piyasa raporu şablonu | Edge ile ilgisi yok (raporlama) | `engine/report.py:1-25` |
| `engine/smc_v2/fvg_entry.py` + `tools/fvg_shadow_report.py` | Operatör FVG setup'ı gölgesi, `[fvg shadow]` log | **SHADOW** (2026-11-14, #343 `bf464d0`) | `configs/config.phase2_1k.yaml:212-216`, `engine/safe_orchestrator.py:2333-2347` |
| `touch_entry` gölgesi | `[touch shadow] would-enter` log | **SHADOW** (T-20261105-04), ölçüm raporu yok | `configs/config.phase2_1k.yaml:209-211`, `collab/tasks/open/T-20261105-04-ws-shadow-flags.md:20-21` |
| `scripts/pine_lab_parity.py` / `pine_lab_variant.py` / `build_pine_lab.py` | Pine Lab: Python replay ↔ TV strateji karşılaştırma + NET skor | Araştırma aracı; ilk tur GATE FAIL | `docs/pine-lab/2026-11-06-ilk-tur.md:1-4`, `:136-158` |
| `scripts/analyze_entry_slippage.py` | journal'dan imzalı slippage ölçümü | Araç (kapalı inisiyatif) | ADR-0009 |
| `scripts/desk/research_cycle.py` (+ `deploy/research-cycle.*`) | TradingAgents + LuxAlgo MTF brief'i | **Advisory only**, emir/config girdisi değil | `docs/runbooks/research-cycle.md:1-10` |
| `kronos:` (efloud-bot) | Kronos tahmin danışmanlığı | **Kapalı** (`enabled: false`); `kronos-runner` yalnız sosyal içerik için | `configs/config.phase2_1k.yaml:352-353`, `docker-compose.prod.yml:318-341` |
| `scripts/wave2_falsification.py` | Wave-2 walk-forward falsifikasyonu | Master'dan silindi (`562a6a3`); geçmişte `b8d3181` (#220) | `git show 562a6a3 --stat` |
| SL/TP redesign raporu + flag'ler | `sl_structural_swing`, `tp_intermediate` | **Master'da YOK**; yalnız lokal branch `feat/smc-sl-tp-redesign` (`91fcb19`, `073a485`), origin'e itilmemiş | `git branch -r --contains 073a485` → boş |
| `reports/` | Backtest çıktıları | Worktree'de yok (gitignore/ana checkout'ta) | `ls reports` → yok |
| `docs/superpowers/specs|plans` (5+3 dosya) | pine-lab, lab visuals, backtest restore, FVG shadow | Güncel | dizin listesi |
| Eski kanıt dokümanları | Wave-2 NO-GO, Kronos, EMC handoff, entry-slippage | `f96b7d8`'de silindi; `git show f96b7d8^:docs/handoff/...` ile okunur | `git ls-tree f96b7d8^` |

---

## 2. Canlı gerçek (şu an prod'da fiilen çalışan davranış, kanıtlı)

**Config seçimi.** Bot `EFLOUD_CONFIG_PATH` yoksa `configs/config.phase2_1k.yaml` kullanır
(`backend/bot_runner.py:47`, `:189`); prod env `.env.production` (secret var — okunmadı).
Kök `config.yaml` testnet/inert (`smc_version: v1`, `luxalgo.enabled: false`, `config.yaml:26`, `:63`) ve
**`backtest:` bloğu yok** → onunla koşulan backtest sessizce BRÜT olur (`backtest/engine.py:424-425`, `:442-443`).

**Canlı giriş yolu (mid, MAINNET):**
1. `engine.smc_version: v2`, 10 sembol whitelist, `smc_v2_shadow: false` (`config.phase2_1k.yaml:90-95`).
2. v1 sinyalleri bu 10 sembolde **susturulur** (`engine/safe_orchestrator.py:1486-1495`, `b2154c5`) →
   `risk.min_confluence: 50` (`:282`) canlı giriş kararını **belirlemiyor**.
3. LuxAlgo modu açık (`:187-188`, `38508f7` 2026-11-01): 15m CHoCH+BOS (`:200`, `658a905`), 12h swing
   bias, premium/discount zorunlu, `luxalgo.min_confluence: 1`, TP `tp_mode: luxalgo`, `pullback_timeout_bars: 48`
   (`:187-208`). Efloud trigger yolu (OB/BB/OTE/origin) `precomputed_candidates` ile by-pass edilir
   (`engine/safe_orchestrator.py:1253-1278`) → `ob_bb_entry`, `ob_bb_zone_atr_pad`, `ote_zone_entry`,
   `origin_swing_lookback` (`:124`, `:176-178`) LuxAlgo modunda fiilen etkisiz (yorum `:182-183` ile tutarlı).
4. Bölge içinde 15m engulfing teyidi (`require_confirmation` config'te yok → kod default `true`, ADR-0009),
   sonra **MARKET** giriş (`exchange/__init__.py:1151-1152`).
5. SL `calc_sl` (OB uç ± 0.5 ATR, min 2 / max 5 ATR, gerçek Wilder ATR `v2_use_real_atr: true` `:108`);
   TP1 ≥ `risk.min_rr` 1.8 R (`engine/safe_orchestrator.py:3058-3069`, `engine/smc_v2/luxalgo.py:576-586`);
   TP1 %50 → BE → TP2.
6. Kapılar: `po3_gate: true` (`:131`), `max_entry_dist_atr: 12.0` (`:141`), `max_zone_overshoot_atr: 6.0`
   (`:168`), `recency_bars: 168` (`:293`), `allow_volatile_entries: true` (`:385`),
   `max_holding_hours: 0` (`:407`, #339), `emergency_balance_threshold: 0` (`:424`).
7. Gölgeler (emir yok): `touch_entry: shadow` (`:211`), `fvg_entry: shadow` (`:216`).
8. Ölçüm altyapısı: `signal_ledger.enabled: false` (`:468`); env override mümkün
   (`engine/signal_ledger.py:146-156`) — **DOĞRULANMADI** (env değeri okunmadı). Açık olsa bile kayıt
   noktası v1 dalında (`safe_orchestrator.py:1497`→`:1567`), v2 sembollerde hiç çalışmaz.
9. `kronos.enabled: false` (`:353`); `agent_team.enabled: true` yalnız gözlem (`:341-342`, ADR-0002);
   `structure_validation.enabled: false` (`:99-100`).
10. Son deploy: `bf464d0` (2026-11-14, `collab/log/claude-code.md:327-330`). VPS durumu repo'dan
    bağımsız doğrulanamadı — **DOĞRULANMADI**.

**Canlı mantığın ölçülmüş edge'i: NEGATİF.**
- 60g karşı-olgu (2026-08-28→11-04, 10 sembol): baz akış **217 işlem, NET −0.30 R/işlem, PF 0.65**, brüt
  −0.03 R; fark maliyet (~0.27 R, medyan SL %0.72) (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:14-17`, `:42`).
- Backtest parity 41g × 10 sembol (2026-09-27→11-07): **137 işlem, WR %33.6, brüt PF 0.69, NET −%0.91**,
  8/10 sembolde PF<1 (`...2026-11-07-backtest-live-parity.md:21-24`, `:83-94`).
- Pine Lab baseline (2026-07-01→11-06, 128g): BTC **PF 0.73** (91 trade) (`docs/pine-lab/2026-11-06-ilk-tur.md:142`, `:156`).
- Parity geçerliliği: LuxAlgo döneminde 10 canlı girişin 8'i aynı yön/sonuçla yeniden üretildi
  (`...parity.md:12-17`, `:103-112`) → backtest canlıyı temsil ediyor.

---

## 3. Çelişkiler

| # | Çelişki | Kanıt A | Kanıt B | Etki | Önerilen çözüm |
|---|---|---|---|---|---|
| 1 | LuxAlgo için "NET-cost backtest YAPILMADI, modül kaldırıldı" notu | `configs/config.phase2_1k.yaml:185-186`; `collab/STATUS.md` Canlı config satırı | Backtest #335 ile döndü; parity NET −%0.91 (`...parity.md:21-24`); T-09 −0.30 R | Okuyan LuxAlgo'nun ölçülmediğini sanar; aslında ölçüldü ve **negatif** | Yorumu ölçüm sonucuyla değiştir (config yorumu = kod; öneri listesine) + STATUS satırını güncelle (doküman PR) |
| 2 | "Backtest modülü kaldırıldı / offline runner yok" | `AGENTS.md:75`; `agents/strategist.md:34-35` | `backtest/` mevcut; `CLAUDE.md:49`; `TESTS.md:22`, `:163-171` | Strategist ajanı backtest'i kullanmaz, yalnız ölü EMC'ye yönelir | AGENTS.md + strategist.md düzelt |
| 3 | v2 girişi "limit emir" | `AGENTS.md:13-15`; `safe_orchestrator.py:1491` yorumu "→ limit" | Kod MARKET: `exchange/__init__.py:1151-1152`; FVG spec "then MARKET" (`docs/superpowers/specs/2026-11-14-fvg-entry-shadow-design.md:34`) | Maliyet modeli seçimi (maker vs taker) yanlış yapılır | AGENTS.md'yi "engulfing teyidi → MARKET" yap |
| 4 | Overshoot toleransı | `AGENTS.md:21` = 2.0 (ayrıca kök CLAUDE.md eski blurb'ü `228382d`) | Config 6.0 (`config.phase2_1k.yaml:168`) | Bayat parametre | AGENTS.md güncelle |
| 5 | `risk.min_rr` "legacy, kullanılmaz" | `config.phase2_1k.yaml:273` yorumu | LuxAlgo TP1 kapısı min_rr kullanıyor: `safe_orchestrator.py:3058-3069`, `luxalgo.py:576-586`; FVG shadow da (`fvg_entry.py:68-78`) | min_rr değişikliği "zararsız" sanılıp canlı TP kapısı değişebilir | Yorumu düzelt (öneri; config dosyası) |
| 6 | "NET-cost backtest gate (Edge Measurement Core, PR #227)" | `CLAUDE.md:40` | EMC ileri-yönlü ledger'dır, backtest değil; flag kapalı + hook v1 dalında (`safe_orchestrator.py:1486-1497`, `:1567`); gerçek gate `backtest.cli` (`CLAUDE.md:49`) | İki farklı ölçüm aracı tek isimde; EMC'nin canlıda veri ürettiği sanılıyor | Principle 4'ü "backtest gate = `backtest.cli` (offline) / forward = shadow log + (onarılınca) ledger" diye ayır |
| 7 | Çekirdek parametreler v1'i anlatıyor | `CLAUDE.md:63-67` (conf 55/50, SL 20 mum, TP1 min R:R 1.5) | Canlı LuxAlgo: `luxalgo.min_confluence: 1`, SL `calc_sl` 0.5 ATR min2/max5, min_rr 1.8 (`config:205`, `:273`; FVG spec `fvg-entry-shadow-design.md:31-37`) | Pine port ve yeni modeller yanlış referansla çalışır | "SMC v1 referansı (canlı sembollerde susturulmuş)" etiketi + LuxAlgo v2 canlı parametre özeti |
| 8 | Setup→emir zinciri `confluence ≥ min_confluence` ile başlar | `CONTEXT.md:36` | v2 LuxAlgo yolu `risk.min_confluence` kullanmaz, `luxalgo.min_confluence` (sayı) kullanır (`safe_orchestrator.py:1269`) | Alan dili yanlış | CONTEXT.md'ye "v1: skor ≥50 / v2-Lux: ek konsept sayısı ≥1" ayrımı |
| 9 | Maliyet modelleri 4 farklı | Backtest: %0.04/taraf + funding %0.01/8h + slip 5/10/5bp (`config:481-482`, `slippage.py:8-10`) | `edge_costs.py:4-14` taker 0.04%+0.05R; FVG shadow RT %0.07 maker+taker, funding/slip yok (`fvg_entry.py:25-27`); T-09 %0.05+%0.02 slip (`...counterfactual.md:34`); plan-replay `--fee-pct 0.04` | FVG go-live kıyası ("canlı v2'den iyi") farklı maliyet tabanlarını kıyaslar → FVG lehine yanlılık | Tek `costs` kaynağı (öneri, ölçüm aracı kodu); o zamana dek raporlarda maliyet varsayımı zorunlu satır |
| 10 | Kararlarda kullanılan GO eşiği koda yazılı değil | Wave-2: OOS PF≥1.30 + ≥4/5 sembol (`git show f96b7d8^:docs/handoff/2026-06-17-claude-wave2-review-nogo.md` §6c); SL/TP: ΔPF>0 OOS + PF≥1.30; T-09/FVG: n≥30, IS+OOS NET>0, bazdan iyi | `DEFAULT_GATES` yalnız v1↔v2 göreli (`comparison.py:26-32`); `evaluate_backtest_gates.py:2` "HERMES.md §6 Adım 3"e atıf, HERMES §6 = deploy (`HERMES.md:138`) | Her inisiyatif kendi eşiğini yazıyor; makine-denetimli NET/OOS kapısı yok | ADR-0011 "Edge GO kriteri" (doküman) + ileride gate script'i (öneri) |
| 11 | Spec CLI'ye `--gross`/maliyet bayrağı vaat ediyor | `docs/superpowers/specs/2026-11-07-operator-decisions-and-backtest-restore-design.md:51` | `backtest/cli.py:286-305` bu bayrakları içermiyor; pencere sonu `time.time()` (`:34`) | A/B tekrar üretilemez (memory notu "time.time patch'le"); brüt kıyas yapılamaz | Spec'e "uygulanmadı" notu; runbook'a sabit-uç yöntemi |
| 12 | ADR-0009 "strateji gerçekte sahip olduğu edge'i korur" | `docs/adr/0009-entry-confirmation-required.md:28` | Teyitli baz akış NET −0.30 R (`...counterfactual.md:42`); teyit göreli olarak iyi (P2 baz −0.75 R) ama pozitif edge yok | ADR pozitif edge ima ediyor | ADR-0009 Consequences: "göreli zarar azaltır; mutlak edge negatif (2026-11-04)" |
| 13 | STATUS panosu bayat | `collab/STATUS.md` master/VPS `3acea5c`, LuxAlgo "NET ölçülmedi" | master `81c2cf7`, deploy `bf464d0` (`collab/log/claude-code.md:327-330`) | "Canlı durum kaynağı" (CLAUDE.md:3) yanlış bilgi veriyor | STATUS satırlarını güncelle (doküman PR) |
| 14 | `min_confluence` gerekçesi silinmiş dokümana atıf | `config.phase2_1k.yaml:283-286` → `docs/audit/03_strategy_review.md` (fee'siz PF 1.35 vs 2.34) | Dosya `f96b7d8`'de silindi; `TESTS.md:78` TEST-AUDIT-C4 "unverified" | Kanıt zinciri kopuk; ayrıca v1 susturulduğu için konu canlıda geçersiz | Yorumu `git show f96b7d8^:` yoluna çevir (öneri) |
| 15 | FVG spec iç tutarsızlığı | `fvg-entry-shadow-design.md:90` "ayrı invalidated state yok" | Aynı dosya `:128` testlerde "invalidation" | Küçük; test adı yanıltıcı | Spec'te "invalidation = fill+stop" notu |
| 16 | `edge_metrics` confluence bantları | `engine/edge_metrics.py:70-71` "55-65/65-75/75+" | Canlı eşik 50 (conf 50-54 "55-65"e düşer); Lux confluence 1-5 sayısı | Ledger açılıp v2'ye taşınırsa kırılım tabloları anlamsız | Ledger v2'ye taşınırken bant tanımı (öneri) |
| 17 | Acil halt eşiği | `config.phase2_1k.yaml:13`, `:50`, `:56` "$360 halt" | `:424` = 0 (kaldırıldı, `b2154c5`) | Bayat başlık yorumu (risk kategorisiyle ortak) | Başlık yorumunu düzelt (öneri) |
| 18 | SL/TP redesign NO-GO kanıtı | Memory/CLAUDE.md akışı "rapor commit `91fcb19`" | Commit yalnız lokal branch'te; `git merge-base --is-ancestor 073a485 HEAD` → NOT_IN_MASTER, origin'de yok | Kanıt kaybolma riski (makine/worktree silinirse) | Raporu master'a doküman olarak taşı (doküman PR'a uygun) |

---

## 4. Bayat / yanlış dokümantasyon

- `CLAUDE.md:17` — "hem INDIKATÖR hem de STRATEGY (backtest) versiyonu" → ADR-0005 strateji ürününü rafa kaldırdı (`CLAUDE.md:3` zaten söylüyor; satır 17 çelişiyor).
- `CLAUDE.md:40` — EMC'yi backtest gate olarak adlandırıyor (Çelişki #6).
- `CLAUDE.md:63-67` — çekirdek parametreler v1 (Çelişki #7). "Confluence 55/50" canlı giriş kararını yönetmiyor.
- `AGENTS.md:10-21` "Güncel Algoritma Durumu (2026-10-02)" — limit emir (yanlış), overshoot 2.0 (bayat), LuxAlgo/FVG/touch gölgeleri yok; `AGENTS.md:75` backtest kaldırıldı (bayat).
- `agents/strategist.md:3`, `:23-27`, `:34-36` — ölçüm aracı olarak yalnız EMC; "offline runner yok" (bayat). Backtest + Pine Lab + gölge loglar anılmıyor.
- `CONTEXT.md:30` — "NET-cost backtest gate: fees and slippage" doğru; ama `:36` zinciri v1 (Çelişki #8).
- `collab/STATUS.md` — master/VPS SHA ve LuxAlgo "NET ölçülmedi" bayat (Çelişki #13); `touch_entry`/`fvg_entry` gölgeleri yok.
- `docs/adr/0009-entry-confirmation-required.md:28` — pozitif edge imasında bayat (Çelişki #12); ayrıca PF 1.41/0.62'nin NET mi brüt mü olduğu yazmıyor — **DOĞRULANMADI** (sonuç dokümanı repoda yok; memory'ye göre Gemini branch'inde commit'lenmemiş).
- `docs/adr/0005-pine-indicator-only-product.md:27` — "even the Python engine's edge is modest" → 2026-11 ölçümleriyle "canlı motorun NET edge'i negatif" demeli; Wave-2 PF 1.165 haziran motoruna (LuxAlgo öncesi) ait.
- `docs/adr/0003-risk-fixes-default-off-behind-gates.md:38-39` H7/M1 "config'ten bağlı değil" — doğru, ama "Known gap" bölümü backtest'in döndüğünü söylüyor; NET/OOS kapı eşiğinin hâlâ kodlanmadığını söylemiyor.
- `scripts/evaluate_backtest_gates.py:2-12` — HERMES §6 Adım 3 atfı kırık; v1↔v2 kıyası artık anlamlı değil.
- `docs/superpowers/specs/2026-11-07-...:51` — `--gross`/override bayrakları uygulanmadı.
- `configs/config.phase2_1k.yaml` yorumları (kod dosyası, yalnız öneri): `:185-186` (ölçülmedi), `:273` (min_rr legacy), `:283-286` (silinmiş audit), `:13/:50/:56` ($360 halt), `:141` (12.0 "çok SL olursa geri düşür" — parity'de 8/10 sembol PF<1, tetik koşulu sayısallaştırılmamış).
- `HERMES.md:102` — "backtest harness" v2 pipeline'ın parçası olarak anılıyor; arada silinip geri geldiği yazmıyor (küçük).

---

## 5. Trade mantığı / setup modelleri

### 5.1 GO/NO-GO karar kronolojisi

| # | Tarih | Karar konusu | Sonuç | Metrik (maliyet tabanı) | Örneklem / OOS | Kanıt |
|---|---|---|---|---|---|---|
| D1 | 2026-06-13 | Pine strateji ürünü (Wave-1 T-003 GATE_RUN_2/3/4) | **NO-GO** → indicator-only | "yeterli trade olduğunda edge negatif"; round-6b PF 0.66-0.84 | 5 sembol TV; OOS yok | `docs/adr/0005-...:9-11`; `pine/u2algo/WAVE1_SPEC.md:205`, `:238`; Wave-2 handoff `:43` |
| D2 | 2026-06-17 | Wave-2 premium redesign (Python motor falsifikasyonu) | **NO-GO / DROP** | OOS pooled **PF 1.165**, IS 1.193; net+ 2/5 (OOS) — yalnız komisyon %0.04, funding/slip 0 | 664 trade (IS 392 / OOS 272), 5 sembol, 6+6 ay WF; BNB IS 1.71→OOS 0.55, XRP 0.85→1.45 (rejim inversiyonu) | `git show f96b7d8^:docs/handoff/2026-06-17-claude-wave2-review-nogo.md` §6b-6d; `b8d3181` (#220); ADR-0005 |
| D3 | 2026-06-15 | `require_confirmation: false` (teyitsiz MARKET) | **NO-GO** | Mode A PF 1.41 vs Mode B PF 0.62 (maliyet tabanı DOĞRULANMADI) | 685 vs 26 trade, 180g×10 sembol; slippage backtest'te yapısal ölçülemez | `docs/adr/0009-entry-confirmation-required.md:9-16`; salvage `e303e49` (#205); sonuç dosyası repoda yok |
| D4 | 2026-06-19/20 | SL/TP redesign (`sl_structural_swing`, `tp_intermediate`) | **DIRECTIONAL NO-GO** (flag'ler master'a girmedi) | BTC OFF/OFF baz **net PF 1.23** (IS 1.29 / OOS 1.11); DOGE SL-ON 1.79 (+0.11), TP-ON 1.41 (−0.27); Gemini ON/ON brüt 1.37 → net ~1.25 | BTC 233 trade; DOGE n~29; 6-sembol grid tamamlanamadı (Win standby + MP hang) | `git show 073a485:docs/handoff/2026-06-18-smc-sl-tp-backtest-report.md:3`, `:42-58` (yalnız lokal branch) |
| D5 | 2026-06-18 | Edge Measurement Core (PR #227) | **Altyapı GO, canlı ölçüm AKTİF DEĞİL** | — | — | `config.phase2_1k.yaml:467-474`; hook `safe_orchestrator.py:1567` (v1 dalı) |
| D6 | 2026-07-18/25 | W2 C1 `anchor_time_axis` / C2 `confirm_last_bar_only` | **NO-GO** (default OFF kalır) | brüt +0.045 R → **NET −0.015 R** | 1000-bar A/B (n DOĞRULANMADI) | `config.phase2_1k.yaml:110-118`, `:476-479` |
| D7 | 2026-07-26 | BT-22 gerçek Wilder ATR (5 ATR tavanı bağlar) | **GO** (canlı) | 336 canlı işlemde süzme: PnL +403.74→+595.66, WR %66.7→%85.2 | In-sample, gerçekleşmiş sonuca göre filtre (ileri test yok) | `config.phase2_1k.yaml:102-108`; `3d4370f` |
| D8 | 2026-07-26 → 11-01 | BT-23 `max_entry_dist_atr` | 6.0 ölçülerek GO; **11-01'de ölçümsüz 12.0** | 30g/10 sembol replay: CONFIRMED 594→597, ölü setup −%50 | replay (PnL değil, yaşam döngüsü sayımı) | `config.phase2_1k.yaml:133-141` |
| D9 | 2026-10-01/03 | Overshoot 0.5→2.0 (→ şimdi 6.0), volatil girişler, BOS setup'ları (`658a905`), recency 40→168, zone pad 0.5 ATR | **Operatör GO, ölçümsüz** (backtest o tarihte kullanılmıyordu / 10-31'de silindi) | — | — | `228382d`, `b2154c5`, `658a905`; `config.phase2_1k.yaml:168`, `:287-293`, `:380-385` |
| D10 | 2026-11-01 | LuxAlgo modu canlı (`38508f7`) | **Operatör GO, ölçümsüz**; sonradan ölçüldü → **negatif** | T-09 baz NET −0.30 R, PF 0.65; parity NET −%0.91, PF 0.69 | 217 trade/60g (IS −0.48, OOS +0.03, 3/10 sembol+); 137 trade/41g | `...counterfactual.md:42`; `...parity.md:21-24` |
| D11 | 2026-11-04 | Lux kapılarını gevşetme (12h trend, P/D, recency, confluence) | **NO-GO** | her kategori NET −0.17…−0.32 R (P1) | 29-472 trade/kategori, IS/OOS 2/3-1/3 | `...counterfactual.md:11-13`, `:44-51` |
| D12 | 2026-11-04 | TV LuxAlgo kutularını motora girdi yapma (b) / salt-okunur bölge uyarısı (a) | (b) **NO-GO**, (a) **GO** (emir yolu yok) | — | 664 dokunuş/14g replay | `collab/outputs/claude-code/2026-11-04-ob-entry-gap.md:23-24`; `config:201-203` |
| D13 | 2026-11-04 | Mitige OB retest (BB benzeri) | **Takip adayı** (karar yok) | P1 **+0.24 R, PF 1.42**, IS +0.23 / OOS +0.25, 5/10 sembol | n=30 (eşik sınırı), tek 60g pencere | `...counterfactual.md:18-20`, `:52`, `:86` |
| D14 | 2026-11-05 | `touch_entry: shadow` | **SHADOW**, ölçüm yok | — | go-live barı n≥30, IS+OOS NET>0, bazdan iyi | `T-20261105-04-ws-shadow-flags.md:20-21` |
| D15 | 2026-11-06 | Pine Lab baseline parity | **GATE FAIL** (harness sayım sorunları); toggle turu koşulmadı | BTC PF 0.73 (TV), 128g | BTC 91 / ETH 71 / SOL 104 trade | `docs/pine-lab/2026-11-06-ilk-tur.md:1-4`, `:140-158` |
| D16 | 2026-11-07 | Backtest geri yükleme + parity | **GO (araç)** | 8/10 LuxAlgo-dönemi canlı giriş eşleşti; NET −%0.91 | 41g×10 sembol | `...parity.md:12-24`; #335 (`da675dc`, `435df23`) |
| D17 | 2026-11-07 | Sentiment ±5 → telemetri; structure validation kapalı | **GO** (davranış değişmez, byte-identical) | — | — | spec `2026-11-07-operator-decisions...:11-12`; #332/#334 |
| D18 | 2026-11-08 | `max_holding_hours` 36→0 (zorla kapatma kaldırıldı) | **GO** (canlı, `518f118` #339) | A/B NET **−46.05 → −12.02 $**, trade sayısı aynı | 41g × 4 sembol; tek pencere, OOS yok; iki kol da negatif | `collab/log/claude-code.md:317-320` |
| D19 | 2026-11-14 | Operatör FVG pullback setup'ı | **SHADOW** (`bf464d0` #343), `live` değeri kodda yok | offline replay **WR %30.6, NET ort ≈ +0.00 R** (RT %0.07 maliyet) | 85 kapanış / 45g / 10 sembol; harness git dışında (DOĞRULANMADI) | `collab/log/claude-code.md:329`; spec `fvg-entry-shadow-design.md:99-109` |
| D20 | 2026-11-13 | pin_fvg_touch ± Kronos forward A/B (**ayrı repo** `Leblepito/u2Algo-Trade`) | **FORWARD TEST** (testnet/paper), mainnet kilitli | search n=87 +0.065 R; validation n=28 **−0.313 R**; holdout #1 net −0.50, #2 n=19 net −0.85 | 11-14 itibarıyla 0 forward kapanış; başarı: Kronos kolu ≥30 kapanış, NET>0, kontrolden iyi | `C:/tmp/u2Algo-Trade/docs/superpowers/specs/2026-11-13-forward-kronos-ab-design.md` ("Past numbers"); holdout değerleri yalnız oturum belleğinde — DOĞRULANMADI |
| D21 | 2026-06-05 → bugün | Kronos danışmanlığı (efloud-bot) | **KAPALI**; trade'e hiç girdi olmadı; edge ölçümü yok | — | — | `config.phase2_1k.yaml:352-353`; `docker-compose.prod.yml:318-341` (yalnız sosyal) |
| D22 | 2026-06 | `min_confluence` 80→50 | Operatör GO (frekans için) | yorum: conf=50 PF 1.35 vs conf=80 PF 2.34, **fee'siz** | kaynak silinmiş | `config.phase2_1k.yaml:282-286`; `TESTS.md:78` (unverified); v1 susturulduğu için canlıda etkisiz |

### 5.2 Bileşen etiket tablosu (Fable filtresi)

| Bileşen | Etiket | Gerekçe (NET, n, OOS) | Kanıt |
|---|---|---|---|
| Canlı LuxAlgo v2 baz akışı (12h bias + CHoCH/BOS + OB + engulfing + MARKET) — pozitif edge olarak | **ÇÜRÜTÜLMÜŞ** | NET −0.30 R/PF 0.65 (n=217, 60g); NET −%0.91/PF 0.69 (n=137, 41g); Pine PF 0.73 | D10, D15, D16 |
| Lux kapıları (12h trend, premium/discount, recency 168, confluence≥1) — zarar sınırlayıcı olarak | **KANITLI (göreli)** | Kaldırılınca NET −0.17…−0.32 R; baz kadar ya da daha kötü | D11 |
| Lux kapılarını gevşetmek | **ÇÜRÜTÜLMÜŞ** | Aynı tablo | D11 |
| 15m engulfing teyidi (teyitsiz limit/market'e karşı) | **KANITLI (göreli)** | Baz P1 −0.30 vs P2 −0.75 R (n 217/232); Haziran PF 1.41 vs 0.62 | D3, D11 |
| Teyitsiz MARKET / bölge kenarından teyitsiz limit (baz) | **ÇÜRÜTÜLMÜŞ** | P2 baz −0.75 R, 0/10 sembol+; Mode B PF 0.62 | D3, D11 |
| "Dokundu, engulfing gelmedi" vakalarında limit | **KANITSIZ** | −0.04 R, PF 0.95, n=407 — başa baş | `...counterfactual.md:54` |
| Mitige OB / breaker retest | **KANITSIZ (umut verici)** | +0.24 R, IS/OOS ikisi +, n=30, tek pencere | D13 |
| Operatör FVG pullback (4h bias, FVG limit, OB SL, OB/BB TP1, likidite TP2) | **KANITSIZ** | ≈0 R, n=85, OOS yok, maliyet tabanı farklı | D19 |
| pin_fvg_touch (u2Algo) | **KANITSIZ → eğilim ÇÜRÜTÜCÜ** | validation −0.313 R (n=28), iki holdout negatif | D20 |
| Kronos yön teyidi | **KANITSIZ** | 0 forward kapanış; efloud'da hiç ölçülmedi | D20, D21 |
| `tp_intermediate` (ara TP1 / yapısal TP2 swap) | **ÇÜRÜTÜLMÜŞ (yönsel)** | DOGE −0.27 PF; n~29 | D4 |
| `sl_structural_swing` | **KANITSIZ** | DOGE +0.11 PF, n~29; çok-sembol koşu tamamlanmadı | D4 |
| C1 `anchor_time_axis` / C2 `confirm_last_bar_only` | **ÇÜRÜTÜLMÜŞ** | NET −0.015 R | D6 |
| Gerçek Wilder ATR + 5 ATR SL tavanı (BT-22) | **KANITSIZ** | Gerçekleşmiş sonuca göre süzme (look-ahead), ileri ölçüm yok | D7 |
| `max_entry_dist_atr` 12.0 | **KANITSIZ** | 6.0 yaşam-döngüsü ölçümüydü; 12.0 ölçümsüz | D8 |
| `max_zone_overshoot_atr` 6.0, `allow_volatile_entries`, BOS continuation, `recency_bars` 168, `ob_bb_zone_atr_pad` | **KANITSIZ** | Ölçümsüz operatör değişiklikleri; pad LuxAlgo'da etkisiz | D9 |
| `po3_gate` | **KANITSIZ** | Hiç NET A/B yok; 5 günde 25 blok (`fvg-entry-shadow-design.md:23`) | — |
| `max_holding_hours: 0` | **KANITLI (göreli, zayıf)** | −46 → −12 $, n aynı, tek pencere 4 sembol | D18 |
| `min_confluence` 50 (v1) | **KANITSIZ / canlıda ilgisiz** | fee'siz kanıt, kaynak silindi, v1 susturuldu | D22 |
| Python motor tavanı "PF ~1.17" (Haziran) | **Eskimiş** | LuxAlgo öncesi motora ait; bugünkü motor daha düşük (PF 0.65-0.69) | D2 vs D10 |
| Backtest aracı canlıyı temsil eder | **KANITLI** | 8/10 eşleşme, aynı sonuç işareti; kayıplar backtest'te %7-130 büyük (pesimist fill) | D16 |
| Maliyet = edge katili (dar SL, medyan %0.72) | **KANITLI** | Brüt −0.03 R → NET −0.30 R | `...counterfactual.md:15-17` |

---

## 6. ECC revizyon adayları

1. **CLAUDE.md principle 4 (doküman PR'ına uygun):** "NET-cost backtest gate (EMC, #227)" ifadesini ikiye böl:
   *offline gate* = `python -m backtest.cli single` (canlı config, NET, TP1→BE→TP2) + *forward kanıt* =
   `[fvg shadow]` / `[touch shadow]` log raporları. EMC'yi "flag kapalı, hook v1 dalında — v2'de veri üretmez" diye işaretle.
2. **Tek GO kriteri (ADR-0011 önerisi, doküman):** Şimdiye dek kullanılan eşikleri tek yerde birleştir:
   NET (komisyon+funding+slippage açıkça yazılı), n≥30/kol, IS ve OOS NET>0, ≥X sembol pozitif, bazdan ΔNET>0
   aynı pencerede, sabit pencere ucu + git SHA. Kanıt satırları: Wave-2 §6c, SL/TP rapor `:35-36`, T-09 `:36`, FVG spec `fvg-entry-shadow-design.md:106-109`.
3. **Edge karar defteri (doküman):** §5.1 tablosunu `docs/adr/` altında ya da `docs/research/DECISIONS.md`
   olarak kalıcılaştır; her satırda `git show <sha>:<path>` kanıt yolu. Silinmiş/lokal kanıtları (Wave-2 handoff,
   SL/TP raporu `073a485`) master'a doküman olarak taşı.
4. **AGENTS.md "Güncel Algoritma Durumu":** tarihi 2026-11-14'e çek; LuxAlgo modu, MARKET giriş, overshoot 6.0,
   `max_holding_hours: 0`, `touch_entry`/`fvg_entry` gölgeleri, "backtest geri döndü (#335)", "ölçülmüş baz NET negatif" satırları.
5. **`agents/strategist.md`:** ölçüm araçları listesine `backtest.cli`, `scripts/pine_lab_parity.py score`,
   `tools/fvg_shadow_report.py` ekle; "offline runner yok" cümlesini sil; kanıt satırı formatına "maliyet varsayımı" alanı ekle.
6. **`CONTEXT.md`:** "Confluence" satırına v1 (0-100 skor) / Lux v2 (ek konsept sayısı) ayrımı; zincir (`:36`) iki yola ayrılsın; "Shadow (gölge)" terimi (log-only, `live` değeri kodda yok) eklensin.
7. **ADR-0009 + ADR-0005 notları:** "teyit göreli olarak iyi, mutlak edge negatif (2026-11-04/07 ölçümleri)"; Wave-2 PF'nin LuxAlgo öncesi motora ait olduğu.
8. **`collab/STATUS.md`:** master/VPS SHA, LuxAlgo satırı (ölçüldü, negatif), gölgeler ve go-live barları.
9. **Yeni runbook `docs/runbooks/backtest-gate.md` (doküman):** sembol başı paralel `single`, sabit pencere ucu (`backtest.cli.time.time` patch), `grid` seri default, Windows standby (`powercfg`), maliyet bloğu olmayan config'in BRÜT koşması uyarısı, sonuçların `reports/backtests/` altında kalıcı olmaması.
10. **`TESTS.md`:** yeni "missing" satırları — (a) "signal ledger hook v2 sembollerde erişilebilir" (bugün değil), (b) "backtest config'inde `backtest:` bloğu yoksa uyarı", (c) GO-kriter script'i.
11. **Skill önerisi:** `skills/edge-gate/SKILL.md` — kararı tek tabloya (n, NET ort R, PF, IS/OOS, sembol+, maliyet) zorlayan rapor şablonu; `skills/plan-replay` ve `pine_lab_parity score` maliyetleriyle aynı sabitleri kullanmalı.
12. **Kod/config önerileri (bu turda canlıya GİTMEZ; backtest-gate + operatör onayı):** tek maliyet kaynağı;
    `DEFAULT_GATES`'e NET PF/OOS kapısı; CLI `--end`/`--gross`; ledger hook'unu v2 `_place_v2_entry_order`
    öncesine taşıma; config yorumlarını düzeltme (#1, #5, #14, #17).

---

## 7. Riskler ve açık sorular

- **R1 — Canlı strateji ölçülmüş NET negatif ve hâlâ MAINNET'te.** Üç bağımsız ölçüm (T-09, parity, Pine Lab) aynı yönde.
  Bu rapor karar önermez; LuxAlgo modunun devamı operatör/risk-ops kararıdır (`...counterfactual.md:84-85`).
- **R2 — Forward kanıt birikimi kırılgan:** `FvgShadowBook` bellekte, restart'ta kaybolur (`fvg-entry-shadow-design.md:97`); rapor komutu
  `docker logs --since 168h` container yeniden oluşturulunca sıfırlanır (son 7 günde 4 deploy: `collab/log/claude-code.md:313-330`).
  Kalıcı `EFLOUD_LOG_FILE=/app/logs/efloud_bot.log` (`docker-compose.prod.yml:17`) okunmalı — JSON satırlarda regex'in
  çalıştığı **DOĞRULANMADI** (`tools/fvg_shadow_report.py:17-18`).
- **R3 — Kıyas yanlılığı:** FVG gölgesi maker giriş + %0.07 RT, funding/slippage yok; canlı v2 taker MARKET + slippage.
  "Canlı v2'den iyi" kıyası FVG lehine eğik (Çelişki #9).
- **R4 — Edge Measurement Core canlıda fiilen ölü** (flag + v1 dalı). CLAUDE.md'nin "gate" dediği şey veri üretmiyor.
- **R5 — Kanıt kaybı:** SL/TP raporu yalnız lokal branch'te; Wave-2/entry-slippage/EMC dokümanları yalnız `f96b7d8^`'de;
  backtest çıktıları (`reports/backtests/...`) ana checkout'ta, git dışında.
- **R6 — Tekrar üretilebilirlik:** CLI pencere ucu "şimdi"; A/B'lerde `time.time` patch'i belgelenmemiş (yalnız oturum belleği).
- **R7 — Çoklu bakış (multiple testing):** EMC `"BH-FDR NOT YET APPLIED"` (`engine/edge_metrics.py:87`); u2Algo'da holdout
  q-düzeltmesi var, efloud'da yok. Mitige-OB +0.24 R bulgusu 12+ kategoriden biri — şans payı yüksek.
- **R8 — Ölçümsüz gevşetmeler birikiyor** (D8, D9): her biri tek başına küçük, birlikte trade evrenini değiştiriyor; parity'deki
  NET negatifliğin hangi kısmının bunlardan geldiği bilinmiyor.
- **Açık sorular:** (a) `EFLOUD_SIGNAL_LEDGER_ENABLED` prod'da set mi? (b) Haziran Mode A PF 1.41 NET mi? (c) FVG offline replay
  harness'i nerede, hangi SHA? (d) scalp/long botları (LuxAlgo `38508f7` ile açıldı) şu an çalışıyor mu, ölçüldü mü?
  (e) u2Algo forward kolları imaj yeniden derlendi mi (memory: 11-14 itibarıyla hayır)?

---

## 8. Fable'a özet (en önemli maddeler)

1. **Canlı LuxAlgo v2 akışının NET edge'i negatif** — T-09: n=217, −0.30 R, PF 0.65; parity: n=137, PF 0.69, NET −%0.91; Pine Lab BTC PF 0.73. Maliyet (dar SL) brüt ≈0'ı negatife çeviriyor. → ÇÜRÜTÜLMÜŞ.
2. **Kapılar ve engulfing teyidi göreli olarak koruyucu** (gevşetince −0.17…−0.32 R; teyitsiz −0.75 R) → KANITLI (göreli), ama mutlak edge üretmiyor.
3. **Pozitif edge adayı yalnız biri:** mitige OB/breaker retest +0.24 R (n=30, IS/OOS +, tek pencere) → KANITSIZ (umut verici). ≥180 gün yeniden ölçülmeli.
4. **Operatör FVG setup'ı ve pin_fvg_touch başa baş/negatif** (FVG ≈0 R n=85; pin_fvg_touch validation −0.31 R, iki holdout negatif); Kronos teyidi için 0 forward kapanış → KANITSIZ.
5. **Haziran kararları (Wave-2 PF 1.165 OOS, SL/TP baz 1.23/OOS 1.11, teyitsiz giriş PF 0.62) LuxAlgo öncesi motora ait;** bugünkü motor daha zayıf. "Tavan PF ~1.17" ifadesi eskidi.
6. **"NET-cost gate = Edge Measurement Core" (CLAUDE.md:40) yanlış:** EMC flag'i kapalı ve hook v1 dalında → v2 sembollerde hiç kayıt yok. Gerçek gate `backtest.cli`; GO eşiği (NET, n≥30, IS+OOS>0, bazdan iyi) koda yazılı değil, `DEFAULT_GATES` bayat v1↔v2 kıyası.
7. **Dört farklı maliyet modeli** (backtest, edge_costs, FVG shadow, T-09) → go-live kıyasları tutarsız; tek maliyet kaynağı + raporda zorunlu maliyet satırı önerilir.
8. **Bayat doküman yoğunluğu:** AGENTS.md (backtest kaldırıldı, limit emir, overshoot 2.0), strategist.md (offline runner yok), STATUS.md (SHA'lar, "NET ölçülmedi"), config yorumları (`:185-186`, `:273`), CLAUDE.md çekirdek parametreleri (v1).
9. **Kanıt kırılganlığı:** SL/TP NO-GO raporu yalnız lokal branch'te; gölge örneklemi restart/deploy ile sıfırlanıyor; A/B'ler sabit pencere ucu olmadan tekrar üretilemiyor.
10. **Bu turda yapılabilecek doküman PR'ı:** CLAUDE.md p4 ayrımı, AGENTS/strategist/CONTEXT/STATUS düzeltmeleri, ADR-0009/0005 notları, edge karar defteri + GO kriteri ADR'si, backtest-gate runbook'u. Kod/config değişiklikleri yalnız öneri listesinde.
