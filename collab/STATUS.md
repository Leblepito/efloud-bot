# STATUS — pano

> **Sistem** satırlarını son gözlemleyen model yazar (kaynak + UTC zaman zorunlu).
> **Model durumu** satırını yalnız o model, **Açık demolar** satırını demoyu açan model günceller.
> Hepsi PR ile (bkz. `README.md` §2). Kaynaksız değer yazma.

## Sistem

| Alan | Değer | Kaynak / zaman (UTC) | Gözlemleyen |
| --- | --- | --- | --- |
| GitHub master | `81c2cf7` (#344: EF-20261114-01 deploy log; önceki #343 FVG giriş gölgesi) | `git log origin/master` 2026-11-14 | claude-code |
| VPS `/opt/efloud-bot` HEAD | Son DEPLOYED kaydı `bf464d0` (#343, EF-20261114-01). VPS'te `git log` ile yeniden doğrulanmadı — kaynak deploy logu | `collab/log/claude-code.md` (EF-20261114-01) | claude-code |
| V1 `efloud-bot` (mid) | MAINNET, `dry_run: false`; açık pozisyon **0**; breaker **OPEN** (= normal, işlem serbest) | salt-okuma anlık görüntü (VPS) 2026-11-14 12:12 | claude-code |
| V2 `efloud-bot-long` / V3 `efloud-bot-scalp` | Konteynerler **Up**; son 7 günde emir logu yok; `EFLOUD_PAUSE_NEW_ENTRIES` ayarlı değil. "Canlı" sayılıp sayılmadıkları açık soru (operatör) | salt-okuma anlık görüntü (VPS) 2026-11-14 12:12 | claude-code |
| K1 — V1 yeni giriş durdurma | Karar: V1 yeni girişleri `EFLOUD_PAUSE_NEW_ENTRIES=true` ile durdurulacak (ADR-0012, PR-B'de yazılacak). **Durum: operatör uygulaması bekleniyor.** Mevcut pozisyon yönetimi / SL-TP / reconcile etkilenmez. Guard: env > `safety.pause_new_entries` (`engine/safety/position_guard.py:62-110`), v2 emir yolunda kontrol `engine/safe_orchestrator.py:3147-3155` | karar 2026-11-14 (ECC audit spec K1) | claude-code |
| Canlı config (mid) | `configs/config.phase2_1k.yaml` — MAINNET, `smc_version: v2` (`:90-95`), **`smc_v2.luxalgo.enabled: true`** (`:180-188`). Config yorumundaki "NET-cost backtest yapılmadı" notu (`:185-186`) bayat: LuxAlgo akışı **ölçüldü, NET negatif** (−0.30 R/işlem, PF 0.65, n=217; `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`; backtest PF 0.69, `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:21-24`). Etkili/inert anahtarlar: `CONTEXT.md` | repo @ `81c2cf7` | claude-code |
| Canlı config (scalp) | `configs/config.phase2_scalp_1k.yaml` — `profile: scalp` (5m entry / 1h / 4h) | repo @ `645a5dc` | claude-code |
| Alerter (Telegram) | **Aktif**: LuxAlgo bölge (`EFLOUD_ALERTER_LUX_ALERTS=1`) + **TP yerleştirme hatası** (`_TP_ALERTS=1`, #308) + **SL koruma / stop'suz pozisyon** ve **orphan pozisyon** (`_SL_ALERTS=1`, #314/#315). CRITICAL uyarılar LLM formatlayıcıdan geçmez + HTML kaçışı / düz metin yedeği (#322, 2026-11-07 11:30). Yalnız mid bot logu. Manuel pozisyon susturma: `EFLOUD_ALERTER_ORPHAN_IGNORE_SYMBOLS` | `docker exec efloud-alerter printenv` + kural listesi 2026-11-07 10:22 | claude-code |
| İzleme kapsamı | Alerter ve canary **yalnız V1**: alerter yalnız `efloud_logs` (V1) volume'unu izler (`docker-compose.prod.yml:165`); canary yalnız V1 healthz'i yoklar (`scripts/canary.py:25`). V2/V3 için uyarı yok | repo @ `81c2cf7` | claude-code |
| Efektif pozisyon tavanı | ⌊`max_total_exposure` × bakiye / pozisyon notional⌋ (`engine/safety/position_guard.py:271-282`; `configs/config.phase2_1k.yaml:71,299,403`). `starting_balance` (`:375`) ile en çok 4 eşzamanlı pozisyon; `max_open_positions: 10` (`:272`) bu bakiyede erişilemez. Güncel bakiye ile yeniden hesaplanmadı | repo @ `81c2cf7` | claude-code |
| Gölgeler (emir yok) | `smc_v2.touch_entry: shadow` (`configs/config.phase2_1k.yaml:211`), `smc_v2.fvg_entry: shadow` (`:216`, #343; rapor `tools/fvg_shadow_report.py`). Kodda `live` değeri yok; go-live barı kod docstring'inde (`engine/safe_orchestrator.py:2333-2340`), kanonik GO kriteri ADR-0011 (PR-B'de yazılacak) | repo @ `81c2cf7` | claude-code |
| master branch koruması | **YOK** (`protected: false`) — kural yalnız protokolle; karar T-20261104-04 | `gh api …/branches/master` 2026-11-04 | claude-code |

## Model durumu

| Model | Şu an üzerinde | Son log girişi | Bekleyen isteği |
| --- | --- | --- | --- |
| claude-code | ECC audit 2026-11-14 doküman düzeltmeleri (PR-A, branch `docs/ecc-audit-2026-11-14`) | 2026-11-14 | operator → K1 uygulaması, T-20261104-04, T-20261104-07 |
| hermes | — (onboarding bekliyor) → T-20261104-05 | — | — |
| abacus | #272 (T-01, operatör merge) · #276 VPS teşhis · #278 WS Faz 1 · #280 WS Faz 2 (touch/event, default off) · #281/#282 (T-20261105-02/01) — hepsi review bekliyor | 2026-11-05 | claude-code → review; operatör → #272 merge, touch_entry shadow→live kararı |

## Açık demolar (NOT-DEPLOYED: DEMO)

| Branch / PR | Sahibi | Ne | Kim test etsin | Durum |
| --- | --- | --- | --- | --- |
| — | | | | |
