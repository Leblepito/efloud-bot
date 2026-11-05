# STATUS — pano

> **Sistem** satırlarını son gözlemleyen model yazar (kaynak + UTC zaman zorunlu).
> **Model durumu** satırını yalnız o model, **Açık demolar** satırını demoyu açan model günceller.
> Hepsi PR ile (bkz. `README.md` §2). Kaynaksız değer yazma.

## Sistem

| Alan | Değer | Kaynak / zaman (UTC) | Gözlemleyen |
| --- | --- | --- | --- |
| GitHub master | `b39751a` (#285 entegrasyon: #272/#276/#279/#280/#284; öncesinde #283 WS Faz 1, #275 uyarılar) | `git fetch` 2026-11-05 06:05 | claude-code |
| VPS `/opt/efloud-bot` HEAD | `042c3a3` = master, temiz — **DEPLOYED** (EF-20261105-02/03). Açık: WS gölge (`data_feed.ws.enabled`, `event_scan: false`), `touch_entry: shadow`, `near_alert_atr: 1.0`, alerter `EFLOUD_ALERTER_LUX_ALERTS=1` — hepsi yalnız log/bildirim | `ssh efloud-bot git rev-parse` 2026-11-05 06:06 | claude-code |
| VPS container'lar | Hepsi yeniden oluşturuldu + Up (efloud-bot, -scalp, -long, overseer, alerter, routines). `EFLOUD_AUTOSTART=0`: yalnız **mid** 06:06 UTC'de API ile başlatıldı (healthz ok, breaker OPEN, 0 pozisyon); **scalp/long idle** (T-20261104-07; Binance key'leri mainnet'te geçersiz `-2008`) | `docker ps` + `/api/status` + `/healthz` 2026-11-05 06:07 | claude-code |
| Canlı config (mid) | `configs/config.phase2_1k.yaml` — MAINNET, `smc_version: v2`, **`smc_v2.luxalgo.enabled: true`** (`:182-183`, 2026-11-01; "NET-cost backtest yapılmadı" notu `:180-181`), `min_confluence: 50`, daily %10 / weekly %25 | repo @ `71dfff5` | claude-code |
| Canlı config (scalp) | `configs/config.phase2_scalp_1k.yaml` — `profile: scalp` (5m entry / 1h / 4h) | repo @ `645a5dc` | claude-code |
| Alerter (Telegram) | **Aktif** — 2026-11-04 19:59 UTC'den beri gönderiyor (öncesinde env adı uyuşmazlığıyla dry-run idi, T-20261104-10). Yalnız mid bot logunu okur. | `docker logs efloud-alerter` 2026-11-04 ~20:45 | claude-code |
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
