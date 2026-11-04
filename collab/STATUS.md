# STATUS — pano

> **Sistem** satırlarını son gözlemleyen model yazar (kaynak + UTC zaman zorunlu).
> **Model durumu** satırını yalnız o model, **Açık demolar** satırını demoyu açan model günceller.
> Hepsi PR ile (bkz. `README.md` §2). Kaynaksız değer yazma.

## Sistem

| Alan | Değer | Kaynak / zaman (UTC) | Gözlemleyen |
| --- | --- | --- | --- |
| GitHub master | `68fdc9a` (#266 karantina, #268 collab protokolü, #269 STATUS takibi merge edildi) | `git fetch` 2026-11-04 18:37 | claude-code |
| VPS `/opt/efloud-bot` HEAD | `b6c6bd1` (master'ın 4 commit gerisi; fark: `skills/` → `collab/` taşıma, `collab/**`, `tests/collab/**`, `.dockerignore`, `AGENTS.md`, `HERMES.md` — engine/exchange/config/runtime kodu yok → deploy gerekmiyor) | `ssh efloud-bot git rev-parse` 2026-11-04 18:37 | claude-code |
| VPS container'lar | Hepsi Up/healthy (efloud-bot, -scalp, -long, overseer, alerter, routines). ⚠️ 14:35 restart sonrası `EFLOUD_AUTOSTART=0`: yalnız **mid** (`efloud-bot`) 14:38'de başlatıldı; **scalp ve long idle** (tarama döngüsü yok) → T-20261104-07 | `docker ps` + `docker logs` 2026-11-04 19:15 | claude-code |
| Canlı config (mid) | `configs/config.phase2_1k.yaml` — MAINNET, `smc_version: v2`, **`smc_v2.luxalgo.enabled: true`** (`:182-183`, 2026-11-01; "NET-cost backtest yapılmadı" notu `:180-181`), `min_confluence: 50`, daily %10 / weekly %25 | repo @ `71dfff5` | claude-code |
| Canlı config (scalp) | `configs/config.phase2_scalp_1k.yaml` — `profile: scalp` (5m entry / 1h / 4h) | repo @ `645a5dc` | claude-code |
| master branch koruması | **YOK** (`protected: false`) — kural yalnız protokolle; karar T-20261104-04 | `gh api …/branches/master` 2026-11-04 | claude-code |

## Model durumu

| Model | Şu an üzerinde | Son log girişi | Bekleyen isteği |
| --- | --- | --- | --- |
| claude-code | OB/BB giriş açığı teşhisi (`outputs/claude-code/2026-11-04-ob-entry-gap.md`) | 2026-11-04 | operator → T-20261104-04, T-20261104-07 |
| hermes | — (onboarding bekliyor) → T-20261104-05 | — | — |
| abacus | — (onboarding bekliyor) → T-20261104-02, T-20261104-01 | — | — |

## Açık demolar (NOT-DEPLOYED: DEMO)

| Branch / PR | Sahibi | Ne | Kim test etsin | Durum |
| --- | --- | --- | --- | --- |
| — | | | | |
