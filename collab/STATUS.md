# STATUS — pano

> **Sistem** satırlarını son gözlemleyen model yazar (kaynak + UTC zaman zorunlu).
> **Model durumu** satırını yalnız o model, **Açık demolar** satırını demoyu açan model günceller.
> Hepsi PR ile (bkz. `README.md` §2). Kaynaksız değer yazma.

## Sistem

| Alan | Değer | Kaynak / zaman (UTC) | Gözlemleyen |
| --- | --- | --- | --- |
| GitHub master | `71dfff5` (#266 karantina `7b2940f` + #268 collab protokolü merge edildi) | `git fetch` 2026-11-04 18:05 | claude-code |
| VPS `/opt/efloud-bot` HEAD | `b6c6bd1` (master'ın 1 gerisi; fark yalnız `skills/` dokümanı → runtime etkisi yok) | `ssh efloud-bot git rev-parse` 2026-11-04 17:18 | claude-code |
| VPS container'lar | efloud-bot (healthy), efloud-bot-scalp (healthy), efloud-overseer, efloud-alerter, efloud-routines — hepsi Up | `docker ps` 2026-11-04 17:18 | claude-code |
| Canlı config (mid) | `configs/config.phase2_1k.yaml` — MAINNET, `smc_version: v2`, **`smc_v2.luxalgo.enabled: true`** (`:182-183`, 2026-11-01; "NET-cost backtest yapılmadı" notu `:180-181`), `min_confluence: 50`, daily %10 / weekly %25 | repo @ `71dfff5` | claude-code |
| Canlı config (scalp) | `configs/config.phase2_scalp_1k.yaml` — `profile: scalp` (5m entry / 1h / 4h) | repo @ `645a5dc` | claude-code |
| master branch koruması | **YOK** (`protected: false`) — kural yalnız protokolle; karar T-20261104-04 | `gh api …/branches/master` 2026-11-04 | claude-code |

## Model durumu

| Model | Şu an üzerinde | Son log girişi | Bekleyen isteği |
| --- | --- | --- | --- |
| claude-code | collab/ kurulumu (karantina PR + protokol PR) | 2026-11-04 | operator → T-20261104-04 |
| hermes | — (onboarding bekliyor) → T-20261104-05 | — | — |
| abacus | — (onboarding bekliyor) → T-20261104-02, T-20261104-01 | — | — |

## Açık demolar (NOT-DEPLOYED: DEMO)

| Branch / PR | Sahibi | Ne | Kim test etsin | Durum |
| --- | --- | --- | --- | --- |
| — | | | | |
