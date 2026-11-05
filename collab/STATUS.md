# STATUS — pano

> **Sistem** satırlarını son gözlemleyen model yazar (kaynak + UTC zaman zorunlu).
> **Model durumu** satırını yalnız o model, **Açık demolar** satırını demoyu açan model günceller.
> Hepsi PR ile (bkz. `README.md` §2). Kaynaksız değer yazma.

## Sistem

| Alan | Değer | Kaynak / zaman (UTC) | Gözlemleyen |
| --- | --- | --- | --- |
| GitHub master | `6d70ae0` (#290 WS `/market/stream` düzeltmesi; öncesi #286 deploy kaydı, #287/#289 bayraklar) | `git fetch` 2026-11-05 17:05 | claude-code |
| VPS `/opt/efloud-bot` HEAD | `6d70ae0` = master = laptop ana klon, çalışma ağaçları temiz — **DEPLOYED** (EF-20261105-04, `deploy/deploy.sh`) | `ssh efloud-bot git rev-parse` + laptop `git rev-parse` 2026-11-05 17:05 | claude-code |
| VPS container'lar | Hepsi yeniden oluşturuldu + Up. `EFLOUD_AUTOSTART=0`: yalnız **mid** 16:47 UTC'de API ile başlatıldı (healthz 200, breaker OPEN, 0 pozisyon). WS gölge akışı veri alıyor: 17:00 UTC 10/10 `parity=OK`, 0 MISMATCH. **scalp/long idle** (T-20261104-07; Binance key'leri mainnet'te geçersiz `-2008`) | `docker logs efloud-bot` + `/healthz` 2026-11-05 17:01 | claude-code |
| Canlı config (mid) | `configs/config.phase2_1k.yaml` — MAINNET, `smc_version: v2`, **`smc_v2.luxalgo.enabled: true`** (`:182-183`, 2026-11-01; "NET-cost backtest yapılmadı" notu `:180-181`), `min_confluence: 50`, daily %10 / weekly %25 | repo @ `71dfff5` | claude-code |
| Canlı config (scalp) | `configs/config.phase2_scalp_1k.yaml` — `profile: scalp` (5m entry / 1h / 4h) | repo @ `645a5dc` | claude-code |
| Alerter (Telegram) | **Aktif** + LuxAlgo bölge uyarıları **açık** (`EFLOUD_ALERTER_LUX_ALERTS=1`, `near_alert_atr: 1.0`; ilk `[lux] near`/`touch` satırları 16:00 UTC). Yalnız mid bot logunu okur. | `docker exec efloud-alerter printenv` + `docker logs efloud-bot` 2026-11-05 16:15 | claude-code |
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
