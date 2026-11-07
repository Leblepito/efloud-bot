# STATUS — pano

> **Sistem** satırlarını son gözlemleyen model yazar (kaynak + UTC zaman zorunlu).
> **Model durumu** satırını yalnız o model, **Açık demolar** satırını demoyu açan model günceller.
> Hepsi PR ile (bkz. `README.md` §2). Kaynaksız değer yazma.

## Sistem

| Alan | Değer | Kaynak / zaman (UTC) | Gözlemleyen |
| --- | --- | --- | --- |
| GitHub master | `05c1e92` (#302–#315 ECC backlog + güvenlik denetimi düzeltmeleri + TP/SL/orphan Telegram uyarıları; 14 PR merged) | `git fetch` 2026-11-07 10:20 | claude-code |
| VPS `/opt/efloud-bot` HEAD | `05c1e92` = master (EF-20261107-01). Çalışma ağacında Hermes'in commit edilmemiş `collab/STATUS.md` + `collab/log/hermes.md` değişiklikleri korundu; yedek private store `vps-wip-backup-20261107T101847Z/` | `ssh efloud-bot git rev-parse` 2026-11-07 10:21 | claude-code |
| VPS container'lar | Yalnız **alerter** yeniden oluşturuldu (yeni image `71b15a1`); efloud-bot / -long / -scalp, overseer, routines **dokunulmadı** (Up 42h, eski image `2a8fd64`, healthz `ok`) | `docker ps` + `docker inspect` 2026-11-07 10:21 | claude-code |
| Canlı config (mid) | `configs/config.phase2_1k.yaml` — MAINNET, `smc_version: v2`, **`smc_v2.luxalgo.enabled: true`** (`:182-183`, 2026-11-01; "NET-cost backtest yapılmadı" notu `:180-181`), `min_confluence: 50`, daily %10 / weekly %25 | repo @ `71dfff5` | claude-code |
| Canlı config (scalp) | `configs/config.phase2_scalp_1k.yaml` — `profile: scalp` (5m entry / 1h / 4h) | repo @ `645a5dc` | claude-code |
| Alerter (Telegram) | **Aktif**: LuxAlgo bölge (`EFLOUD_ALERTER_LUX_ALERTS=1`) + **TP yerleştirme hatası** (`_TP_ALERTS=1`, #308) + **SL koruma / stop'suz pozisyon** ve **orphan pozisyon** (`_SL_ALERTS=1`, #314/#315). Yalnız mid bot logu. Manuel pozisyon susturma: `EFLOUD_ALERTER_ORPHAN_IGNORE_SYMBOLS` | `docker exec efloud-alerter printenv` + kural listesi 2026-11-07 10:22 | claude-code |
| master branch koruması | **YOK** (`protected: false`) — kural yalnız protokolle; karar T-20261104-04 | `gh api …/branches/master` 2026-11-04 | claude-code |

## Model durumu

| Model | Şu an üzerinde | Son log girişi | Bekleyen isteği |
| --- | --- | --- | --- |
| claude-code | OB/BB giriş açığı teşhisi (`outputs/claude-code/2026-11-04-ob-entry-gap.md`) | 2026-11-04 | operator → T-20261104-04, T-20261104-07 |
| hermes | — (onboarding bekliyor) → T-20261104-05 | — | — |
| abacus | #272 (T-01, operatör merge) · #276 VPS teşhis · #278 WS Faz 1 · #280 WS Faz 2 (touch/event, default off) · #281/#282 (T-20261105-02/01) — hepsi review bekliyor | 2026-11-05 | claude-code → review; operatör → #272 merge, touch_entry shadow→live kararı |

## Açık demolar (NOT-DEPLOYED: DEMO)

| Branch / PR | Sahibi | Ne | Kim test etsin | Durum |
| --- | --- | --- | --- | --- |
| — | | | | |
