# STATUS — pano

> **Sistem** satırlarını son gözlemleyen model yazar (kaynak + UTC zaman zorunlu).
> **Model durumu** satırını yalnız o model, **Açık demolar** satırını demoyu açan model günceller.
> Hepsi PR ile (bkz. `README.md` §2). Kaynaksız değer yazma.

## Sistem

| Alan | Değer | Kaynak / zaman (UTC) | Gözlemleyen |
| --- | --- | --- | --- |
| GitHub master | `0c90059` (#351: FVG offline gate result; önceki #345–#350) | `git log origin/master` 2026-11-14 | claude-code |
| VPS `/opt/efloud-bot` HEAD | **`e7c83de`** (#348 FVG gölge varyant B + kanonik maliyet, #350 Ö1 verify fail-closed) — yalnız `efloud-bot` yeniden oluşturuldu; alerter `2b20aaa` (#347) ile 14:19 UTC'de yeniden oluşturuldu. #349/#351 (araç + doküman) VPS'e çekilmedi | operatör komut çıktısı 2026-11-14 15:28 UTC (`git log --oneline -1`) | claude-code |
| V1 `efloud-bot` (mid) | MAINNET, `dry_run: false`, `running: true`; açık pozisyon **0**; breaker **OPEN** (= normal); **yeni girişler DURDURULDU (K1)**. `EFLOUD_AUTOSTART=0` → her recreate sonrası `/api/bot/start` | `/api/status` + log `pause_new_entries config loaded: effective=True source=env` 2026-11-14 15:28 UTC | claude-code |
| V2 `efloud-bot-long` / V3 `efloud-bot-scalp` | Konteynerler **Up**; son 7 günde emir logu yok; `EFLOUD_PAUSE_NEW_ENTRIES` ayarlı değil. "Canlı" sayılıp sayılmadıkları açık soru (operatör) | salt-okuma anlık görüntü (VPS) 2026-11-14 12:12 | claude-code |
| K1 — V1 yeni giriş durdurma | Karar: V1 yeni girişleri `EFLOUD_PAUSE_NEW_ENTRIES=true` ile durdurulacak (ADR-0012, PR-B'de yazılacak). **Durum: UYGULANDI 2026-11-14 12:30 UTC** — VPS `.env.production` (yedek `.env.production.bak-20261114`), yalnız `efloud-bot` `up -d --no-deps` (image değişmedi, `fee4b850…` = 11-13 build); V1 `EFLOUD_AUTOSTART=0` olduğundan döngü `/api/bot/start` ile pause aktifken başlatıldı; log `pause_new_entries config loaded: effective=True source=env`; açık pozisyon 0, breaker OPEN, mainnet. Geri alma: yedeği geri kopyala + aynı `up -d --no-deps` + `/api/bot/start`. Mevcut pozisyon yönetimi / SL-TP / reconcile etkilenmez. Guard: env > `safety.pause_new_entries` (`engine/safety/position_guard.py:62-110`), v2 emir yolunda kontrol `engine/safe_orchestrator.py:3147-3155` | karar 2026-11-14 (ECC audit spec K1) | claude-code |
| Canlı config (mid) | `configs/config.phase2_1k.yaml` — MAINNET, `smc_version: v2` (`:90-95`), **`smc_v2.luxalgo.enabled: true`** (`:180-188`). Config yorumundaki "NET-cost backtest yapılmadı" notu (`:185-186`) bayat: LuxAlgo akışı **ölçüldü, NET negatif** (−0.30 R/işlem, PF 0.65, n=217; `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`; backtest NET −$181.9 / −%0.91, n=137, brüt PF 0.69, `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:21-24`). Etkili/inert anahtarlar: `CONTEXT.md` | repo @ `81c2cf7` | claude-code |
| Canlı config (scalp) | `configs/config.phase2_scalp_1k.yaml` — `profile: scalp` (5m entry / 1h / 4h) | repo @ `645a5dc` | claude-code |
| Alerter (Telegram) | **Aktif**: LuxAlgo bölge (`EFLOUD_ALERTER_LUX_ALERTS=1`) + **TP yerleştirme hatası** (`_TP_ALERTS=1`, #308) + **SL koruma / stop'suz pozisyon** ve **orphan pozisyon** (`_SL_ALERTS=1`, #314/#315). CRITICAL uyarılar LLM formatlayıcıdan geçmez + HTML kaçışı / düz metin yedeği (#322, 2026-11-07 11:30). **Pause farkında (#347):** `EFLOUD_PAUSE_NEW_ENTRIES` açıkken bölge uyarıları "⏸ … yeni girişler DURDURULDU" der. Yalnız mid bot logu. Manuel pozisyon susturma: `EFLOUD_ALERTER_ORPHAN_IGNORE_SYMBOLS` | `docker exec efloud-alerter printenv` + kural listesi 2026-11-07 10:22 | claude-code |
| İzleme kapsamı | Alerter ve canary **yalnız V1**: alerter yalnız `efloud_logs` (V1) volume'unu izler (`docker-compose.prod.yml:165`); canary yalnız V1 healthz'i yoklar (`scripts/canary.py:25`). V2/V3 için uyarı yok | repo @ `81c2cf7` | claude-code |
| Efektif pozisyon tavanı | ⌊`max_total_exposure` × bakiye / pozisyon notional⌋ (`engine/safety/position_guard.py:271-282`; `configs/config.phase2_1k.yaml:71,299,403`). `starting_balance` (`:375`) ile en çok 4 eşzamanlı pozisyon; `max_open_positions: 10` (`:272`) bu bakiyede erişilemez. Not: exposure `avg_entry × remaining_size` ile toplanır — TP1 almış pozisyon yarım notional sayıldığından 5. pozisyon açılabilir. Güncel bakiye ile yeniden hesaplanmadı | repo @ `81c2cf7` | claude-code |
| Gölgeler (emir yok) | `smc_v2.touch_entry: shadow` (`configs/config.phase2_1k.yaml:211`); `smc_v2.fvg_entry: shadow` + `fvg_entry_sl_variants: [atr, ob_pct]` (#348; satırlar `v=A`/`v=B`, kanonik maliyetle `net_r`/`cost_r`; rapor `tools/fvg_shadow_report.py`). Sıfır `setup+` bug DEĞİL: aynı kodun replay'i 3 günde 2 plan, 7 g hunide ana darboğaz TP1 (karşı OB/BB ≥ 1.8R) %26. **Hedef FVG modeli ADR-0011 offline kapısında FAIL** (A NET −0.26 R, B NET −0.20 R, brüt ≈ 0; `docs/research/2026-11-14-fvg-offline-gate.md`) → canlı FVG yolu açılmaz | gölge logları + replay 2026-11-14 | claude-code |
| master branch koruması | **YOK** (`protected: false`) — kural yalnız protokolle; karar T-20261104-04 | `gh api …/branches/master` 2026-11-04 | claude-code |

## Model durumu

| Model | Şu an üzerinde | Son log girişi | Bekleyen isteği |
| --- | --- | --- | --- |
| claude-code | Araştırma R2: mitige-OB retest (branch `feat/lux-ob-mitigation-filter`, 180 g backtest operatör terminalinde) · takip: kalıcı algo-okuma hatası uyarısı | 2026-11-14 | operator → R2 backtest sonucu |
| hermes | — (onboarding bekliyor) → T-20261104-05 | — | — |
| abacus | #272 (T-01, operatör merge) · #276 VPS teşhis · #278 WS Faz 1 · #280 WS Faz 2 (touch/event, default off) · #281/#282 (T-20261105-02/01) — hepsi review bekliyor | 2026-11-05 | claude-code → review; operatör → #272 merge, touch_entry shadow→live kararı |

## Açık demolar (NOT-DEPLOYED: DEMO)

| Branch / PR | Sahibi | Ne | Kim test etsin | Durum |
| --- | --- | --- | --- | --- |
| — | | | | |
