# DECISIONS — algoritma / setup karar kronolojisi (append-only)

> **Rol:** history. Append-only: mevcut satır düzeltilmez; düzeltme veya yeni ölçüm **yeni satır** olarak eklenir
> ("Düzeltme: <tarih> satırı …"). Kaynak: `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §3 (soyağacı) +
> `docs/audit/2026-11-14-ecc/04-edge-research.md` §5.1 (GO/NO-GO kronolojisi), 2026-11-14'te birleştirildi.
> Yeni kayıtlar ADR-0011 rapor biçimine uyar (pencere ucu, git SHA, maliyet satırı, denenen varyant sayısı).
>
> Kısaltmalar: `config` = `configs/config.phase2_1k.yaml`; `cf` = `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md`;
> `parity` = `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md`. NET = komisyon + funding (+ slipaj)
> düşülmüş; "brüt" = maliyetsiz. "yalnız lokal branch `<ad>`, master'da yok" = rapor operatörün makinesindeki
> lokal branch'te, origin'de değil (kaybolma riski; `git show <sha>:<path>` ile okunur).

| Tarih | Karar / düğüm | PR / SHA | Metrik (PF, NET R, n, OOS) | Sonuç | Kanıt yolu |
|---|---|---|---|---|---|
| ≤2026-05 | v1 confluence motoru (`engine/signals.py`): CHoCH/BOS anında MARKET, 0-100 skor | — | Bkz. 06-17 satırı | Hesaplanır, girişi 10-01'den beri susturulmuş | `engine/safe_orchestrator.py:1486-1495` |
| 2026-05-14 | Reverse-on-profit guard | `0622849` | — (edge konusu değil) | v1-only; canlı v2'de karşı yön RED | memory `reverse_position_guard_policy.md` |
| 2026-05-23/24 | SMC v2 efloud triggers: CHoCH → FVG/OB/OTE → pullback → engulfing; yapısal SL | 15 PR, `3fa88b8` | BT-sweep v2 R/trade −0.257 | ÇÜRÜTÜLMÜŞ; lux açıkken bypass | `config:412` yorumu |
| 2026-06-02 → 06-04 | `min_confluence` 50→80→50 ("daha çok işlem") | `6f1231f`, `38ec7cc` | conf=50 PF 1.35 vs conf=80 PF 2.34 (**fee'siz**; kaynak silinmiş) | Operatör GO; v1'de, canlıda inert | `config:282-286` |
| 2026-06-13 | Pine strateji ürünü (Wave-1 T-003) | ADR-0005 | round-6b PF 0.66-0.84; 5 sembol TV; OOS yok | NO-GO → indicator-only | `docs/adr/0005-pine-indicator-only-product.md`; `pine/u2algo/WAVE1_SPEC.md` |
| 2026-06-15 | Teyitsiz MARKET (`require_confirmation: false`) | ADR-0009, #205 (`e303e49`) | Mode A PF 1.41 (n=685) vs Mode B PF 0.62 (n=26); maliyet tabanı doğrulanmadı | NO-GO; teyit zorunlu | `docs/adr/0009-entry-confirmation-required.md:9-16` |
| 2026-06-17 | Wave-2 premium redesign (Python motor falsifikasyonu) | #220 (`b8d3181`) | OOS pooled PF 1.165 (IS 1.193), NET+ 2/5 OOS; n=664 (IS 392 / OOS 272); yalnız komisyon %0.04 | NO-GO / DROP (< 1.30) | `git show f96b7d8^:docs/handoff/2026-06-17-claude-wave2-review-nogo.md` |
| 2026-06-18 | Edge Measurement Core (signal ledger) | #227 | — | Altyapı GO; canlıda veri yok (flag kapalı, hook v1 dalında) | `config:467-468`; `engine/safe_orchestrator.py:1497`, `:1567` |
| 2026-06-19/20 | SL/TP redesign (`sl_structural_swing`, `tp_intermediate`) | `073a485` | BTC baz NET PF 1.23 (IS 1.29 / OOS 1.11), n=233; DOGE SL-ON +0.11 PF, TP-ON −0.27 PF (n~29) | DIRECTIONAL NO-GO; flag'ler master'a girmedi | `git show 073a485:docs/handoff/2026-06-18-smc-sl-tp-backtest-report.md` — yalnız lokal branch `feat/smc-sl-tp-redesign`, master'da yok |
| 2026-07-06/07 | TF merdiveni (mid 15m/4h/12h); v2 canlı (`smc_v2_shadow: false`) | `3c96029`, `444cd11` | — | CANLI temel | `data/timeframes.py:24-28`; `config:90-95` |
| 2026-07-18/25 | C1 `anchor_time_axis`, C2 `confirm_last_bar_only` | — | brüt +0.045 R → NET −0.015 R (1000-bar A/B; n doğrulanmadı) | NO-GO; default OFF | `config:110-118`, `:476-479` |
| 2026-07-24 | Sizing: fixed $50 × 10x | `1c20e22` | — (risk kararı) | CANLI | `config:71`, `:297-299` |
| 2026-07-26 | BT-22 gerçek Wilder ATR (5 ATR tavanı bağlar); `min_sl_atr` 0.5→2.0 | `3d4370f` (BT-22 kodu, default OFF); `2d0b960` (`min_sl_atr` 0.5→2.0) | BT-22: 336 canlı işlemde süzme PnL +403.74→+595.66 (in-sample); `min_sl_atr`: R/trade −0.363→−0.257 | BT-22 GO ama KANITSIZ (look-ahead süzme); 2.0 taban KANITLI (göreli) | `config:102-108`, `:412` |
| 2026-07-26 | BT-23 `max_entry_dist_atr` = 6.0 | — | 30g/10 sembol replay: CONFIRMED 594→597, ölü setup −%50 (PnL değil) | GO (yaşam döngüsü ölçümü) | `config:133-141` |
| 2026-09-30 | OB/BB'den giriş + Po3 kapısı | `242cef3`, `a2f7890` | Po3 hiç NET A/B yok | CANLI (mid); KANITSIZ | `config:119-131` |
| 2026-10-01 | v1 MARKET susturuldu; acil bakiye halt = 0; volatil girişler açık; overshoot 0.5→2.0 | `b2154c5`, `228382d` | Ölçümsüz | Operatör GO | `config:385`, `:424` |
| 2026-10-02/03 | BOS setup'ları; dedup + cap 6 + timeout 12; recency 40→168; overshoot 6.0; entry dist 8.0; zone pad 0.5 ATR | `658a905`, `4417e90`, `ad41004`, `2b5ca9a` | Ölçümsüz (backtest kullanılmıyordu) | Operatör GO; KANITSIZ | `config:168`, `:287-293` |
| 2026-10-31 | Backtest modülü silindi | `562a6a3` | — | Ölçüm kör dönemi; 11-07'de geri geldi | `git show 562a6a3 --stat` |
| 2026-11-01/02 | **LuxAlgo modu canlı**; SL yalnız OB ucu; `max_entry_dist_atr` 8→12 | `38508f7`, `6a8c0cf`, `eb01f40` | Sonradan ölçüldü: NET −0.30 R, PF 0.65, n=217, 60g (IS −0.48 / OOS +0.03, 3/10 sembol+); brüt PF 0.69; NET −$181.9 (−%0.91), n=137, 41g | Operatör GO (ölçümsüz) → **ÇÜRÜTÜLMÜŞ** | `cf:42`; `parity:21-24`; `config:133-141`, `:187-188` |
| 2026-11-04 | Lux kapılarını gevşetme (12h trend, P/D, recency, confluence) — T-09 | #277 | Her kategori NET −0.17…−0.32 R (n 29-472) | NO-GO; kapılar KANITSIZ — gevşetme NET negatif (−0.17…−0.32 R); koruyucu etkisi ölçülmedi (elenen ≈ baz) | `cf:44-51`; `collab/tasks/done/T-20261104-09-lux-gate-counterfactual-netcost.md` |
| 2026-11-04 | Mitige-OB / breaker retest | #277 | +0.24 R, PF 1.42, IS +0.23 / OOS +0.25, 5/10 sembol, n=30, tek 60g pencere | Takip adayı (KANITSIZ, sınırda) | `cf:52` |
| 2026-11-04 | Teyitsiz limit, "dokundu, engulfing gelmedi" (P2) | #277 | Baz P2 −0.75 R, PF 0.27, n=232; dokundu-teyitsiz −0.04 R, PF 0.95, n=407 | Teyit TARTIŞMALI — baz P1 −0.30 vs P2 −0.75 lehine; ancak teyit almayan dokunuşlarda limit P2 −0.04 R, PF 0.95 (n=407); kaynak: 'değer kattığına dair kanıt da yok' (`cf:22`); baz akışta teyitsiz giriş ÇÜRÜTÜLMÜŞ | `cf:43`, `:54` |
| 2026-11-04 | TV LuxAlgo kutuları motora girdi (b) / salt-okunur bölge uyarısı (a) | #274, #275 | 664 dokunuş / 14g replay | (b) NO-GO, (a) GO (emir yolu yok) | `collab/outputs/claude-code/2026-11-04-ob-entry-gap.md`; `config:201-203` |
| 2026-11-05 | `touch_entry: shadow` | #280 | Ölçüm yok | SHADOW | `config:211`; `collab/tasks/open/T-20261105-04-ws-shadow-flags.md` |
| 2026-11-06 | Pine Lab baseline parity | `f583e86` | BTC PF 0.73 (TV, 128g); BTC 91 / ETH 71 / SOL 104 işlem | GATE FAIL ×3 | `docs/pine-lab/2026-11-06-ilk-tur.md` |
| 2026-11-07 | Backtest geri yükleme + canlı parity | #335 (`aace1fa`; `da675dc`, `435df23`) | 8/10 LuxAlgo-dönemi canlı giriş eşleşti; NET −%0.91 | Araç GO (KANITLI) | `parity:12-24` |
| 2026-11-07 | Sentiment telemetriye; yapı doğrulama kapalı | #332, #334 | — (byte-identical) | GO | `docs/superpowers/specs/2026-11-07-operator-decisions-and-backtest-restore-design.md` |
| 2026-11-07/08 | ICT Kılçık (wick 4h); Sweep CHoCH 4h/1h; all-15m Sweep CHoCH (SL %0.2); Pin→sweep→5m CHoCH→FVG | `ee1dd9e`, `d538c34`, `4b626ff` | Kılçık NET −0.089 R (n=70); Sweep 4h/1h −0.276 / −0.094 R (n=117/256); all-15m −0.218…−0.333 R (n 166-698); Pin→FVG −0.319 / −0.203 R (n=27/35) | ÇÜRÜTÜLMÜŞ; merge edilmedi | `git show 4b626ff:docs/superpowers/reports/2026-11-08-ict-sweep-eval.md`, `…-ict-sweep-eval-15m.md`, `…-pin-sweep-fvg-eval.md` — yalnız lokal branch `feat/pine-lab-mpa-wick-setup`, master'da yok |
| 2026-11-08 | `max_holding_hours` 36→0 | #339 (`59c32f3`, `518f118`) | A/B NET −46.05 → −12.02 $, işlem sayısı aynı; 41g × 4 sembol; OOS yok; iki kol negatif | CANLI; göreli KANITLI (zayıf) | `collab/log/claude-code.md:317-320`; `config:407` |
| 2026-11-09 → 13 | `pin_fvg_touch` ± Kronos forward A/B (u2Algo-Trade) | ayrı repo | validation n=28 −0.313 R; holdout #1 NET −0.50, #2 n=19 NET −0.85; forward 0 kapanış | Forward test (testnet/paper); holdout ÇÜRÜTÜLMÜŞ | Repo dışı: `u2Algo-Trade:docs/superpowers/specs/2026-11-13-forward-kronos-ab-design.md`; holdout değerleri memory `u2algo_forward_ab.md` (repo dışı, doğrulanmadı) |
| 2026-11-14 | Operatör FVG pullback setup'ı gölgesi | #343 (`c05260c`, `bf464d0`) | Offline replay 45g / 10 sembol: 85 kapanış, WR %30.6, NET ort ≈ +0.00 R (RT %0.07; harness git dışında) | SHADOW; KANITSIZ | `collab/log/claude-code.md:329`; `config:216`; `engine/smc_v2/fvg_entry.py` |
| 2026-11-14 | ECC revizyon kararları K1–K9 (operatör onaylı) | bu PR | — | K1 uygulandı 12:30 UTC; K6 → ADR-0011; K1/K7/K8 → ADR-0012; K2–K5 → `docs/STRATEGY_INTENT.md` | `docs/superpowers/specs/2026-11-14-ecc-revision-and-target-model-design.md` §2 |
| 2026-06-05 → 2026-11-14 | Kronos danışmanlığı (efloud-bot) | — | Trade'e hiç girdi olmadı; edge ölçümü yok | KAPALI | `config:352-353` |
| 2026-11-14 | FVG hedef modeli — ADR-0011 offline kapısı (15m/4h, A ve B SL) | #348, #349 (`08b0469`) | A n=595 NET −0.26 R OOS PF 0.71; B n=588 NET −0.20 R OOS PF 0.74; brüt ≈ 0 | FAIL — canlı FVG yolu (Ö9) açılmaz | `docs/research/2026-11-14-fvg-offline-gate.md` §1 |
| 2026-11-14 | Araştırma R1: aynı model 1h/8h (maliyet/R düşük) | #349 | A n=142 brüt −0.15 R NET −0.30 R; B n=153 brüt −0.20 R NET −0.35 R | Brüt ön kapı (≥ +0.25 R) geçilmedi | `docs/research/2026-11-14-fvg-offline-gate.md` §2 |

**Okuma:** her düğüm bir öncekinin şikâyetine yanıt; BT-23 = 6.0 ve `min_sl_atr` 2.0 dışında hiçbiri NET-cost
kapısını geçerek canlıya girmedi. Negatiflik motor değiştikçe sürdü → ortak etken maliyet/R oranı ve giriş
kalitesi (`cf:15-17`).
