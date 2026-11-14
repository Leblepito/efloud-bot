# 05 — Platform, Deploy ve Sosyal İnceleme Raporu (2026-11-14)

Kök: `C:/tmp/wt-ecc-audit` (origin/master `81c2cf7`, #344). Salt okuma; yalnız bu rapor yazıldı. `.env*` değerleri okunmadı. Canlı sondalar (DNS + `curl` salt-okunur, 2026-11-14) etiketlidir: **[PROBE]**. Gözlenemeyen her şey **DOĞRULANMADI**.

> Kritik meta bulgu: ana checkout 81 commit geride ve oturuma yüklenen `CLAUDE.md` (içinde `2026-10-02 son çalışma`, 3 farklı dashboard URL'i, "Social Publishing Pipeline YENİ", "u2algo-site Next.js 15") worktree'deki güncel `CLAUDE.md`'den (76 satır, anayasa-only, `T-20261107-27`) tamamen farklı. Yani **bayat CLAUDE.md = ana checkout kopyası**; master'daki kopya zaten düzeltilmiş. Fable'ın okuduğu kopya hangisi diye mutlaka doğrulanmalı.

---

## 1. Envanter (ne var, ne işe yarıyor, canlı mı/ölü mü/shadow mu)

### 1.1 Canlı VPS yığını (`docker-compose.prod.yml`, tek Hetzner VPS — ADR-0001 `docs/adr/0001-single-vps-docker-compose-for-bots.md`)

| Servis (container) | Rol | Kanıt | Durum |
|---|---|---|---|
| `efloud-bot` (V1 mid) | Ana mainnet bot + FastAPI dashboard backend (`backend.main:app`), `config.phase2_1k.yaml` | `docker-compose.prod.yml:2-37`, `Dockerfile` CMD (uvicorn `--proxy-headers`) | CANLI. `/healthz` `status:ok`, `failures:[]` **[PROBE]** |
| `efloud-bot-long` (V2 long, 1h/8h/1d) | Paralel long-profil bot | `docker-compose.prod.yml:44-72`; config `configs/config.phase2_long_1k.yaml:105` | AYAKTA ama `status:"suspended"` **[PROBE]** `v2.2-28-139-82.nip.io/healthz` (AUTOSTART=0, STATUS.md "Hazır (beklemede)", `collab/log/claude-code.md:291`) |
| `efloud-bot-scalp` (V3 scalp, 5m/1h/4h) | Paralel scalp bot | `docker-compose.prod.yml:74-102`; `configs/config.phase2_scalp_1k.yaml:106` | AYAKTA (healthz 200 **[PROBE]**); işlem durumu (suspended mı?) DOĞRULANMADI |
| `caddy` | TLS + reverse proxy | `docker-compose.prod.yml:104-128`, `deploy/Caddyfile` | CANLI |
| `autoheal` (willfarrell 1.2.0 pinned) | Unhealthy container restart; `docker.sock` mount | `:130-145` | CANLI (doğrulanmadı, compose'ta tanımlı) |
| `alerter` | Telegram: LuxAlgo bölge, TP/SL hata, orphan; `EFLOUD_ALERTER_{LUX,TP,SL}_ALERTS=1` | `:147-180`, `ops/alerter/` | CANLI; **yalnız mid bot logunu izler** (`collab/STATUS.md` alerter satırı) |
| `overseer` | Heartbeat + LLM kullanım gözlemi; `EFLOUD_OVERSEER_DRY_RUN=1` | `:196-230` | CANLI ama **DRY_RUN=1** (log-only; "Week 1" yorumu hâlâ duruyor) |
| `routines-watcher` | `scripts/routines/*` (breaker_watch, position_audit, edge_report, resolve_signals, social_content, telegram_digest …) | `:259-285`, `scripts/routines/runner.py:46-50,124` | CANLI |
| `daily-report` (profile `scheduled`), `overseer-phase0`, `overseer-daily-report` (profile `overseer-scheduled`), `routines-scheduled`, `kronos-runner` (profile `scheduled`) | Cron ile `docker compose run` | `:182-195,232-257,287-345` | Cron girdisi repoda YOK → çalışıp çalışmadığı DOĞRULANMADI |
| `panel` (`efloud-panel:8090`) | Birleşik çok-bot izleme paneli; 3 botun API'sini server-side aggregate eder, Basic auth | `docker-compose.panel.yml`, `panel/main.py` (483 satır) | **`docker-compose.prod.yml`'de YOK**, ayrı override dosyası. `https://panel.2-28-139-82.nip.io/healthz` → **502 [PROBE]** (container yok/ölü; neden DOĞRULANMADI) |
| `lato-translator`, `lato-line-bot` | Caddy'de route'u var, compose'ta YOK | `deploy/Caddyfile:60-86` | **ÖLÜ route**: `translate.`/`line.2-28-139-82.nip.io` → 502 **[PROBE]**. efloud ile ilgisiz (başka proje kalıntısı) |

Diğer compose dosyaları: `docker-compose.yml` (tek bot, quick-start, `127.0.0.1:8080`), `docker-compose.testnet.yml` (testnet bot + ikinci Caddy, aynı 80/443 portlarını ister → prod ile aynı host'ta çakışır). Prod compose'ta testnet servisi YOK; memory'deki "pin_fvg_touch ± Kronos forward A/B VPS testnet'te canlı" iddiası repodan DOĞRULANMADI.

Volume notu: `efloud_content_jobs` yalnız `efloud-bot`'a mount (`:26`); `routines-*` `efloud_data:/app/data`'yı mount ediyor — farklı volume (bkz. §3 #9).

### 1.2 Platform kodu

- `backend/` (FastAPI): `api.py` 1047 satır, 33 route; hepsi `Depends(require_auth)` (`backend/api.py:69-540`); `auth.py` cookie `samesite=lax`, `SESSION_SECRET` prod'da zorunlu (`backend/auth.py:49-60`); login rate-limit; CORS `ALLOWED_ORIGINS` (`backend/main.py:180`). `backend/social/*` (feeds, doctrine, hypotheses, content_queue, publishing_worker, instagram/youtube/xurl/manus client) — sosyal altyapı. `backend/migrations/`, `backend/audit/`, `backend/notifications/`.
- `frontend/` Next.js static export (Dockerfile stage 1 → `frontend/out`, backend'den servis). `packages/tokens` = `@efloud/tokens` design-token workspace (`package.json` workspaces: `packages/*`, `frontend`). `u2algo-site/web` workspace listesinde YOK (`package.json:8-11`) ama `package.json` açıklaması "PR #6'dan sonra" diyor → ölü/bekleyen niyet.
- `panel/main.py`: Basic auth (`DASHBOARD_PASSWORD`, env her istekte okunur), 15 sn server-side cache (Binance weight koruması), `esc()` XSS koruması, failed-auth limiter (`T-20261107-06`).
- `u2algo-site/` (Railway root `/u2algo-site`): statik HTML + `server.js` (553 satır; `/healthz`, `/api/waitlist`, `/api/waitlist/health`, `/api/purchase-webhook`), `railway.json` (NIXPACKS, healthcheck `/healthz`), Supabase SQL'leri. Canlı: `u2algo.com` → Railway CNAME, `/healthz` 200 **[PROBE]**.
- `ops/`: `alerter/`, `overseer/`, `daily_report/` (CANLI sidecar'lar); `ig_webhook_server.py`, `ig_sandbox_poller.py`, `vps_webhook_forwarder.py`, `sandbox_setup.sh`, `cloudflare_tunnel_setup.sh`, `x_tokens.example.json`, `README_SOCIAL.md` (Manus sandbox + Cloudflare tunnel mimarisi) → bkz. §1.4.
- `deploy/`: `deploy.sh`, `setup-server.sh`, `Caddyfile` (+`.template`), `HETZNER_GUIDE.md`, `.env.production.example`, `rotate-credentials.sh`, `backup/{backup,restore}_state.sh`, `research-cycle.{sh,service,timer}` + `Dockerfile.research` (5 saatte bir advisory research cycle; systemd — VPS'te kurulu mu DOĞRULANMADI).
- `.github/workflows`: `ci.yml` (pytest py3.11, `backtest-slow`, gitleaks `--no-git` v8.18.4, frontend typecheck+vitest+build), `claude-review.yml` (risk/safety + SMC PR review, `ANTHROPIC_API_KEY` secret), `hermes-review.yml` (cron `30 1 * * *`), `scheduled-review.yml` (cron `0 3 * * *`; ruff/npm audit auto-fix PR). **Deploy job YOK** → deploy tamamen manuel SSH (`skills/efloud-deploy/SKILL.md:12`).
- `hooks/live_write_gate.py` + `live-write-gate.json`: desk plugin PreToolUse kapısı (Binance emir/bot control/prod deploy/Supabase apply öncesi sor). Test: `tests/hooks/test_live_write_gate.py`.
- `scripts/`: sosyal hat (§1.3), `canary.py` (post-deploy), `regression_ledger.py`, `prefetch_data.py`, `binance_monitor.py`, `bigquery_archive.py`, `supabase_apply.py`/`supabase_mgmt.py`, `sync_live_stats.py`, `telegram_channel_collector.py`, `lux_monitor.{py,ps1}`, `pine_lab_*`, `build_pine_lab.py`, `release.sh`, `run_tests_docker.ps1`.

### 1.3 Sosyal yayın hattı (`skills/social-publishing/SKILL.md`)

`engine/content_jobs.py` (Lane A, JSONL → `/app/data/content_jobs`) → `scripts/lane_b_consumer.py` → `lane_c_copywriter.py` (+`content_compliance.py`) → `lane_d_visual.py` + `chart_render.py` (matplotlib PNG 1080×1350/1080×1920) → `lane_g_social.py` (platform bundle; `video_render.py` ffmpeg Ken Burns MP4 7-8 sn) → `lane_g_publish.py` (3 kapı: `pending_review` onayı, `--live`, `X_API_ENABLED`/`INSTAGRAM_ENABLED`/`YOUTUBE_ENABLED`) → `scripts/lane_e/publisher.py`. Zincir tek komut: `scripts/daily_social_run.py` (223 sat.). Yan yollar: `scripts/social_from_telegram.py` (topluluk kanalı → içerik), `routines/social_content.py` (14400 sn), `higgsfield_adapter.py` (opt-in, **çürütülmüş**).

### 1.4 Ölü/belirsiz parçalar

- `ops/ig_webhook_server.py`/`ig_sandbox_poller.py`/`vps_webhook_forwarder.py`/`cloudflare_tunnel_setup.sh`: Manus sandbox mimarisi. `ops/README_SOCIAL.md` diyagramdaki `u2algo_publisher.py` repoda yok (kendi notu: `README_SOCIAL.md:20`). Memory'ye göre IG yayını artık Composio MCP üzerinden (skill `producing-trade-explainer-reels`) → Manus yolu muhtemelen ölü; DOĞRULANMADI (VPS'te forwarder/systemd var mı bilinmiyor).
- `skills/efloud-railway-supabase/SKILL.md:7`: Railway proje `u2algo-prod` + hedef servis **`efloud-bot`** — ADR-0001: Railway bot servisleri 2026-11-07'de silindi → skill'in birinci adımı artık boş hedefe bakıyor.
- `docker-compose.testnet.yml` `version: '3.8'` (obsolete key) ve prod ile port çakışması; kullanılmıyor görünüyor.
- `deploy/Caddyfile` içinde silinmiş DNS'li hostlar (§3 #2).

---

## 2. Canlı gerçek (şu an prod'da fiilen çalışan davranış, kanıtlı)

**Hangi URL canlı? (CLAUDE.md'deki 3-4 URL için karar)** DNS + HTTP sondası 2026-11-14:

| URL | DNS | HTTP | Karar |
|---|---|---|---|
| `https://2-28-139-82.nip.io` | → `2.28.139.82` | `/healthz` 200 `status:ok` | **GÜNCEL operatör dashboard'u (V1)**. `scripts/canary.py:25`, `HERMES.md:34,252`, `skills/*` bunu kullanıyor; VPS kurulumu `6e04bcd` (2026-09-25, "sunucu 2.28.139.82") |
| `https://v2.2-28-139-82.nip.io` / `v3.…` | → aynı IP | 200 (v2: `suspended`) | CANLI (long/scalp dashboard) |
| `https://panel.2-28-139-82.nip.io` | → aynı IP | **502** | Panel container düşmüş/hiç başlatılmamış; **şu an erişilemiyor** |
| `https://bot.u2algo.com` | **çözümlenmiyor** (NXDOMAIN-benzeri) | — | **ÖLÜ** (DNS 2026-11-07'de silindi; `canary.py:26` silinmiş kalmasını denetliyor). `deploy/Caddyfile:91` hâlâ bu host'u panel için listeliyor |
| `https://bot.ualgotrade.com` | → **`178.104.122.91`** (ESKİ VPS IP'si) | `/healthz` **timeout** | **ÖLÜ/BAYAT**. A kaydı eski IP'de kalmış; yeni VPS'e taşınmamış. Caddyfile `:13` ve runbook'lar hâlâ bunu "primary" sayıyor |
| `https://178-104-122-91.nip.io` | → eski IP | timeout | ÖLÜ (memory'deki "fallback" yanlış) |
| `https://u2algo.com` | CNAME → Railway | 200, `/healthz` 200 | CANLI (pazarlama sitesi) |
| `u2algo-site-production.up.railway.app` | — | 404 (arşiv: `docs/history/claude-md-status-archive.md:27`) | ÖLÜ (bu turda sondalanmadı) |

Sonuç: **güncel dashboard = `2-28-139-82.nip.io`; güncel panel hostu (çalışırsa) = `panel.2-28-139-82.nip.io`; site = `u2algo.com`.** `bot.u2algo.com` ve `bot.ualgotrade.com`, `178-104-122-91.nip.io` ölü.

**Canlı bot davranışı (platform görünümü):**
- Mid bot MAINNET (`configs/config.phase2_1k.yaml:70` `testnet: false`), `smc_version: v2`, `smc_v2_symbols` dolu, `smc_v2_shadow: false` (`:90-95`, "LIVE operatör onayı 2026-07-07"). Trade mantığı bu raporun kapsamı dışı.
- Bot AUTOSTART=0 duruşu: compose `start_period: 600s` yorumu (`docker-compose.prod.yml:30-33`). Long bot suspended (probe), mid `ok`.
- Healthz sözleşmesi: HTTP 200 tek başına yetmez — `suspended` da 200 döner (**[PROBE]** long bot; `skills/efloud-deploy/SKILL.md` "Doğrulama" bölümü bunu zaten söylüyor). `scripts/canary.py:_bot_status` yalnız `status=="ok"` + `failures` boş ister → long/scalp suspended iken canary onları görmez (yalnız V1 kontrol ediliyor).
- Deploy yolu (kanıtlı): operatör onayı → `ssh root@<vps> "cd /opt/efloud-bot && git pull -q --ff-only && bash deploy/deploy.sh"` (`skills/efloud-deploy/SKILL.md:12`); gerçekte tek-servis deploy kullanılıyor: `up -d --no-deps <svc>` (ADR-0001 "Consequences"; `collab/STATUS.md` VPS container satırı "Yalnız alerter yeniden oluşturuldu"). Panel: `docker compose -f docker-compose.prod.yml -f docker-compose.panel.yml up -d --no-deps panel` + `docker exec efloud-caddy caddy reload` (`docker-compose.panel.yml:5-8`). CI→CD otomasyonu yok; Railway site main'e push'ta otomatik deploy (`collab/log/claude-code.md:291` "Railway otomatik deploy").
- Güvenlik duruşu: yalnız 80/443/22 UFW (`T-20261106-06`); Caddy HSTS/nosniff/X-Frame-Options; `uvicorn --forwarded-allow-ips '*'` (Dockerfile yorumu: container ağı dışından doğrudan erişim yok); panel Basic auth + limiter; `deploy/rotate-credentials.sh` tek şifreyi 3 bot env'ine senkron yazar. `autoheal` `docker.sock` mount ediyor (root-eşdeğeri; sidecar'a güvenmek zorunda).
- Sosyal hat canlı mı? Repoda **zamanlayıcı yok**: compose'ta `daily_social_run` servisi/cron'u yok; `grep` yalnız dokümanlarda cron örneği buluyor (`skills/social-publishing/SKILL.md` "Common cron patterns"). Yani hat: elle/laptop veya ad-hoc çalışıyor; "otomatik" iddiası DOĞRULANMADI. Memory'ye göre 3 IG Reel (2026-11-06) Composio yoluyla yayınlandı (repo dışı kanıt).

---

## 3. Çelişkiler

| # | Çelişki | Kanıt A | Kanıt B | Etki | Önerilen çözüm |
|---|---|---|---|---|---|
| 1 | VPS IP'si iki farklı: Caddyfile "2-28-139-82.nip.io → resolves to 178.104.122.91" | `deploy/Caddyfile:2,29,45` | nip.io DNS: `2-28-139-82` → `2.28.139.82` **[PROBE]**; `HERMES.md:143`, `skills/efloud-deploy/SKILL.md:12`, `6e04bcd` | Yorum yanlış (eski VPS IP'si); kopyala-yapıştır DNS işi yanlış IP'ye gider. `tests/hooks/test_live_write_gate.py:54,98` iki IP'yi de içeriyor (kapı testi eski IP için de kalmalı) | Caddyfile yorumlarını düzelt; eski IP'yi tek yerde "ESKİ VPS (2026-09 öncesi)" olarak tarihle |
| 2 | Caddyfile silinmiş host'ları hâlâ servis ediyor | `deploy/Caddyfile:13` (`bot.ualgotrade.com`), `:30` (`v2.u2algo.com`), `:46` (`scalp.u2algo.com`), `:91` (`bot.u2algo.com`) | `bot.u2algo.com` NXDOMAIN, `bot.ualgotrade.com`→eski IP **[PROBE]**; `scripts/canary.py:26` `DELETED_HOSTS`; ADR-0001 | Caddy her başlangıçta bu host'lar için ACME dener → sürekli başarısız sertifika denemesi/log gürültüsü; panel `bot.u2algo.com` adıyla anılıyor ama yalnız `panel.…nip.io` çalışabilir | Ölü host'ları Caddyfile + `.template`'ten çıkar (deploy PR, operatör onaylı; canlı Caddy reload gerekir) |
| 3 | CLAUDE.md (ana checkout kopyası) "panel: `https://bot.u2algo.com`" / 3 URL; master CLAUDE.md "bot.u2algo.com … silindi" | oturum CLAUDE.md satır 3 | master `CLAUDE.md:3` | Operatör/ajan ölü URL'e gider | Ana checkout'u fast-forward et (operatör işi; worktree'de zaten düzeltilmiş) |
| 4 | Runbook'lar ölü `bot.ualgotrade.com`'u healthz hedefi yapıyor | `docs/runbooks/crash-loop-recovery.md:30,92`, `docs/runbooks/disaster-recovery.md:48` | **[PROBE]** timeout; `canary.py:25` nip.io kullanıyor | Olay anında kopyalanan komut zaman aşımına uğrar | Runbook'larda `2-28-139-82.nip.io` (veya `docker exec … localhost:8080/healthz`) |
| 5 | `docker-compose.prod.yml` yorumları Caddy'nin `bot.u2algo.com`'da V2'yi (long) servis ettiğini söylüyor | `docker-compose.prod.yml:45,55` ("Caddy bot.u2algo.com'da servis eder") ; `scalp.u2algo.com` `:75,85` ; `configs/config.phase2_long_1k.yaml:6`, `phase2_scalp_1k.yaml:6` | Caddyfile'da `bot.u2algo.com` = panel (`:91`), `v2.u2algo.com` = long (`:30`) | Üç farklı doküman üç farklı host atıyor | Yorumları `v2.2-28-139-82.nip.io`/`v3.…` ile hizala |
| 6 | Panel "birleşik" ama prod compose'ta yok; deploy.sh panel'i ne kurar ne reload eder | `docker-compose.panel.yml:1-8` ("prod.yml'de commit'lenmemiş değişiklikler var" gerekçesi — artık geçersiz, `git status` temiz) ; `deploy/deploy.sh:25` (`up -d` yalnız prod) | panel **502 [PROBE]** | Panel yeniden oluşturulmazsa/override'sız `up -d` panelin orphan kalmasına yol açar; bugün 502 | Panel'i prod compose'a taşı veya deploy.sh'ye `-f docker-compose.panel.yml` + `caddy reload` ekle; panel 502 nedenini operatörle doğrula (DOĞRULANMADI) |
| 7 | `deploy/deploy.sh` tüm prod stack'i `build` + `up -d` yapar (3 canlı bot + sidecar'lar yeniden oluşur) | `deploy/deploy.sh:21-25` | Fiili uygulama tek-servis `--no-deps` (ADR-0001; STATUS) ; `skills/efloud-deploy/SKILL.md:12` yine de `deploy.sh`'yi tarif ediyor | Skill'i harfiyen izleyen ajan image değişince 3 mainnet bot container'ını aynı anda yeniden oluşturur; sağlık beklemesi yalnız `efloud-bot` için (`:28-33`); `.env.production.long/.scalp` hiç kontrol edilmez | `deploy.sh`'ye servis argümanı + bot'lar için "pozisyon/flat" ön-kontrolü; skill'i `--no-deps` akışıyla güncelle (risk-ops review) |
| 8 | Sidecar'lar yalnız V1'i izliyor, panel/canary 3 botu gösteriyor | `docker-compose.prod.yml:154-156,209-214` (alerter/overseer: `efloud-bot:8080`, `state_1k`) ; `collab/STATUS.md` ("Yalnız mid bot logu") | `scripts/canary.py:25` (yalnız V1 healthz); long/scalp `AUTOSTART=0` | V2/V3 breaker/SL/TP/orphan alarmı yok — V3 scalp/V2 long açılırsa körlük | Operatör kararı: V2/V3 aktifleşmeden alerter/canary kapsamı |
| 9 | Sosyal cron örneği host'ta `python -m scripts.daily_social_run` der; varsayılan jobs yolu container yolu | `skills/social-publishing/SKILL.md` "Common cron patterns" (`cd /opt/efloud-bot && python -m …`, log `/app/logs/…`) ; `scripts/daily_social_run.py:~57-60` `jobs_path="/app/data/content_jobs"` | compose: `efloud_content_jobs` yalnız `efloud-bot`'a mount (`:26`), hiçbir sidecar'a değil; host'ta `/app/data` yok | Cron örneği olduğu gibi çalışmaz: ya yanlış yol ya boş jobs | Ephemeral `docker compose run --rm -v efloud_content_jobs:/app/data/content_jobs …` servisi tanımla veya `--jobs`/`EFLOUD_CONTENT_JOBS_PATH` doküman |
| 10 | SKILL.md "229 test" | `skills/social-publishing/SKILL.md` "Testing" | 3 dosyada `def test_` sayısı 46+25+25 = 96 (parametrize hesaba katılmadı) | Sayı doğrulanamıyor | Rakamı kaldır veya `pytest --collect-only` çıktısıyla güncelle (DOĞRULANMADI) |
| 11 | `skills/efloud-railway-supabase` Railway'de `efloud-bot` servisi var sayıyor | `skills/efloud-railway-supabase/SKILL.md:7` | ADR-0001 ("services deleted 2026-11-07"); `CLAUDE.md` Kalıcı yapı notları (Railway yalnız site) | Skill boş servisi sorgular, "olası gereksiz" etiketleri yanlış üretir | Skill'i `u2algo-site` servisine daralt |
| 12 | `docker-compose.panel.yml` yorumu `panel.…nip.io` der, Caddyfile + README "bot.u2algo.com" der | `docker-compose.panel.yml:24` | `deploy/Caddyfile:91`, `CLAUDE.md:3` (eski kopya) | Ad karışıklığı | Tek isim: `panel.2-28-139-82.nip.io` |
| 13 | `collab/STATUS.md` 2026-11-07'de kalmış ("master `3acea5c`") ama master `81c2cf7` (#344) ve CLAUDE.md "güncel durum: collab/STATUS.md" diyor | `collab/STATUS.md` satır 9-10 | `git log` (#343 FVG shadow, EF-20261114-01) | "Anlık durum" kaynağı 7 gün+ bayat; ajan yanlış VPS HEAD'i varsayar | STATUS.md'yi her deploy log'unda güncelle; tarih/commit'i otomatik üreten `scripts` düşünülebilir |
| 14 | `CLAUDE.md` ("Kanonik kaynaklar") kısa; README `README.md:188-198` yapı listesi `panel/` + `u2algo-site/` doğru ama Dashboard "Next.js static dashboard" yine doğru; ancak `README.md:112` "Caddy with automatic …" hostları belirtmiyor | `README.md:112,188-198` | — | Çelişki yok, boşluk: hangi host canlı README'de yok | README'ye "Canlı yüzeyler" tablosu (bu rapor §2) |
| 15 | `overseer` "Week 1: DRY_RUN=1" yorumu ay(lar)dır geçerli | `docker-compose.prod.yml:196-200,214` | `EFLOUD_OVERSEER_DRY_RUN=1` hâlâ | Overseer fiilen devre dışı (yalnız log); "Hermes flip eder" planı yürümemiş | Operatör kararı: aç veya yorumu "kalıcı dry-run" yap |
| 16 | `docker-compose.testnet.yml` ikinci Caddy + 80/443 hostu | `docker-compose.testnet.yml:34-49` | prod Caddy aynı portlar | Aynı host'ta birlikte çalıştırılamaz; memory "VPS testnet forward A/B" ile uyumsuz görünüyor | Testnet'in nerede koştuğunu (ayrı VPS/port) operatörden doğrula (DOĞRULANMADI) |

---

## 4. Bayat / yanlış dokümantasyon

- **Oturuma yüklenen CLAUDE.md (ana checkout)**: (a) "Son çalışma 2026-10-02 … BOS … v2 AKTİF" başlığı — master CLAUDE.md `:3` bunu `collab/STATUS.md`/arşive taşıdı; (b) "Dashboard `2-28-139-82.nip.io` / panel `bot.u2algo.com`" — panel hostu ölü; (c) "Son Durum 2026-07-26 Social Publishing … Test: 229 test, sıfır regresyon" (doğrulanamıyor); (d) "u2algo-site … Next.js 15 ve Node.js 20 tabanlı … `u2algo-site-production.up.railway.app`" — **yanlış**: statik HTML + `server.js`, canlı `u2algo.com` (`docs/history/claude-md-status-archive.md:27`, `collab/tasks/open/T-20261107-23-claude-md-stale.md:19`); (e) bölüm numaralaması "2." iki kez; (f) "Supabase tablo henüz hazır değil `PGRST205`" — 2026-11-07'de `ready` (`archive.md:34`); (g) memory index "`bot.ualgotrade.com` primary" → ölü **[PROBE]**.
- Master `CLAUDE.md:3` hâlâ `bot.u2algo.com` silindi diyor ve "Ana iş:" cümlesini taşıyor (ilk satır 400+ karakter kesik görüldü; kalıcı-kural dosyasında durum izi kalmış olabilir — DOĞRULANMADI, tam metin okunmadı).
- `deploy/HETZNER_GUIDE.md:129,178,190`: `<hyphenated_ip>.nip.io` yönergeleri doğru; ama kılavuz 2026-05 VPS rebuild'i + 2026-09 yeni IP'yi içermiyor (DOĞRULANMADI).
- `docs/runbooks/crash-loop-recovery.md:30,92`, `disaster-recovery.md:48`: ölü `bot.ualgotrade.com`.
- `docs/OPERATOR_GUIDE.md:19,76-145`: `<VPS_IP>.nip.io` ile genel — doğru ama V2/V3/panel host'larını anmıyor.
- `HERMES.md:34,143-162,252-254`: `2-28-139-82.nip.io` + `ssh root@2.28.139.82` (doğru, güncel); 381 satırlık operatör kılavuzu → kimlik bilgisi yok, ama IP + root SSH yazılı (kamuya açık repo ise bilgi sızıntısı — repo görünürlüğü DOĞRULANMADI).
- `docker-compose.prod.yml:45,55,75,85`, `configs/config.phase2_long_1k.yaml:6`, `phase2_scalp_1k.yaml:6`: ölü host adları (§3 #5).
- `ops/README_SOCIAL.md`: Manus/Cloudflare tunnel mimarisi; `u2algo_publisher.py` yok; güncel yol `lane_g_publish.py` (not düşülmüş ama diyagram duruyor).
- `skills/social-publishing/SKILL.md`: "229 test", host-cron örnekleri (§3 #9, #10). "Bug fixes applied (2026-07-26)" bölümü tarihsel — arşive taşınabilir.
- `docker-compose.panel.yml` başlığı "prod.yml'de commit'lenmemiş yerel/staged değişiklikler var" — artık yanlış (`git status` temiz, prod.yml son commit `5c49038`).
- `deploy/Caddyfile:11-12` "NOT (2026-07-24): bot.u2algo.com artık BİRLEŞİK PANELE gidiyor" — 2026-11-07'de DNS silindi, not yanıltıcı.
- `collab/STATUS.md` (§3 #13).

---

## 5. Trade mantığı / setup modelleri (bu kategoride)

Platform kategorisi trade kararı üretmez; yalnız **arayüz** noktaları. Trade mantığına girilmedi.

**Platform ↔ trade motoru arayüzü**
1. `backend/api.py` kontrol yüzeyi: `/api/bot/{start,stop,restart}`, `/api/kill-switch`, `/api/breaker/reset` (`backend/api.py:383-443`), hepsi `require_auth`. Panel bu uçları proxy'ler (`panel/main.py:202` `POST /api/bot/{bot_id}/{action}`) → **panel Basic auth ele geçirilirse 3 botun kill-switch/restart/breaker-reset'i** tek noktadan tetiklenir (kasıtlı özellik; risk §7).
2. Breaker reset kuralı: "OPEN = normal"; HALTED'de reset otomatik değil, operatör onayı (`skills/efloud-deploy/SKILL.md` adım 6). Bu risk-ops kuralı platform tarafından değiştirilmez.
3. Gözlem yan yolları (trade'e yazmaz): `alerter` (log tail + healthz), `overseer`, `routines` (`state_1k` okur — `EFLOUD_STATE_DIR=/app/state_1k`), `/api/positions` Binance weight tüketir (panel 15 sn cache).
4. `engine/content_jobs.py` Lane A emitter: bot → JSONL (additive, sosyal hattın girişi).

**Sosyal "algoritma/varyant" listesi** (edge iddiası yok; ürün/pazarlama)

| Bileşen | Tanım | Durum | Kanıt/Edge |
|---|---|---|---|
| ffmpeg Ken Burns video (`video_render.py`) | Grafik PNG'den deterministik MP4, piksel-sadık | CANLI varsayılan (`EFLOUD_VIDEO_BACKEND` default `ffmpeg`) | **KANITLI** (kod: `scripts/video_render.py:61,284`) — fiyat etiketini bozmaz |
| Higgsfield generative video (`higgsfield_adapter.py`) | AI image-to-video | Opt-in (`EFLOUD_VIDEO_BACKEND=higgsfield`), `daily_social_run` bilinçli olarak seçtirmiyor (`daily_social_run.py` docstring) | **ÇÜRÜTÜLMÜŞ** (SKILL.md: 2026-07-26 ölçüm: TP1 64,800→64,400, y-ekseni bozuk, mum uydurma) |
| Compliance kapısı (`content_compliance.py`, Lane C + Lane E çift kontrol) | Yasak vaat, mutlak $, performans %, disclaimer, `[BACKTEST]`/`[SIM]` etiketi | CANLI (kod) | KANITLI (kod+test; kapsam yeterliliği hukuken DOĞRULANMADI) |
| 3 kapılı yayın (`lane_g_publish.py`) | onay + `--live` + platform env bayrağı | Varsayılan kapalı | KANITLI (kod) |
| `social_from_telegram.py` | Topluluk kanalı → içerik | Kısmen; `collab/tasks/open/T-20261106-02` açık görev | DOĞRULANMADI (canlı kullanım yok) |
| `backend/social/*` (feeds/doctrine/hypotheses/research_runs/tv_manifest) | Araştırma→hipotez→içerik kuyruğu | Kod var; `docs/runbooks/social-research-promotion.md` | Sosyal içerik için edge ölçümü **KANITSIZ** (erişim/dönüşüm metriği yok) |
| Composio IG/YT/Telegram yolu | Repo dışı MCP | Memory: 3 IG Reel 2026-11-06 LIVE, YT upload PENDING (kota) | Repo'da kanıt yok → DOĞRULANMADI |
| Manus sandbox + CF tunnel IG yolu (`ops/`) | Eski yayın yolu | Büyük olasılıkla ÖLÜ | DOĞRULANMADI |

Signal ürünü bağlamı (platform sınırı): indicator-only ürün, Wave-2 premium strateji DROPPED (memory: OOS PF 1.165 < 1.30); topluluk Telegram kanalı varsayılan KAPALI, açmadan önce hukuki onay (`deploy/.env.production.example:48-50`, P-003 §2b). `u2algo-site/server.js` `/api/purchase-webhook` + `entitlements.sql` ticari MVP (P-003) altyapısı canlı; "premium tanımsız" (memory) → ürün tarafı KANITSIZ.

---

## 6. ECC revizyon adayları

1. **CLAUDE.md senkronu (acil)**: ana checkout'u `origin/master`'a ff et; yüklenen kopya bayat. Master CLAUDE.md `:3` başlığı çok uzun (≈1k karakter?) — "Dashboard/panel" cümlesini `collab/STATUS.md`'ye taşı, CLAUDE.md'de yalnız "güncel host tablosu: `collab/STATUS.md`" bırak.
2. **Tek "Canlı yüzeyler" tablosu** (`collab/STATUS.md` veya `README.md`): V1/V2/V3 dashboard (`2-28-139-82.nip.io`, `v2.…`, `v3.…`), panel (`panel.2-28-139-82.nip.io`), site (`u2algo.com`), ölü liste; `scripts/canary.py` ile **aynı sabitlerden** beslenmeli (tek doğruluk kaynağı = canary; test: canary `BOT_HEALTHZ` ↔ Caddyfile host eşleşmesi).
3. **`scripts/canary.py` genişlet**: panel `/healthz`, V2/V3 healthz (`suspended`'ı "beklemede = OK, ama açıkça raporla"), ölü `bot.ualgotrade.com` DNS kontrolü (eski IP'ye işaret ediyor). Bugün panel 502'yi yakalayamıyor.
4. **`skills/efloud-deploy/SKILL.md`**: `deploy.sh` yerine `docker compose … up -d --no-deps <svc>` + panel için ayrı override + `caddy reload` adımı; "tüm stack recreate = 3 mainnet bot" uyarısı; V2/V3 pozisyon-flat kontrolü (`state_long`, `state_scalp`) — şu an yalnız `state_1k` okunuyor (`SKILL.md` adım 2).
5. **`skills/efloud-railway-supabase`**: Railway `efloud-bot` hedefini kaldır, `u2algo-site` + Supabase waitlist/entitlements'a daralt.
6. **`skills/social-publishing/SKILL.md`**: cron örneklerini container-gerçekçi yap (`docker compose run`), "229 test" rakamını `--collect-only` ile güncelle, tarihsel "Bug fixes" bölümünü `docs/history`'ye taşı, "otomatik/VPS'te zamanlı değil" durumunu açık yaz. `producing-trade-explainer-reels` skill'iyle ilişkisi (Composio yolu) tek yerde anlatılsın.
7. **Rules**: `.claude/rules/ecc/common/security.md` "Rate limiting on all endpoints" maddesi `panel`/`u2algo-site` için denetlendi — panel limiter var (`T-20261107-06`), site `server.js:317` 429 var; kural uyumlu. `hooks.md`'ye efloud özel notu: `hooks/live_write_gate.py` (plugin) ↔ proje hook'u ayrımı.
8. **Hook önerisi**: PreToolUse "ölü host" uyarısı — `bot.ualgotrade.com`, `178-104-122-91`, `bot.u2algo.com`, `up.railway.app` içeren komutlarda "ölü host" uyarısı (`live_write_gate.py` zaten eski IP'yi tanıyor; yalnız yazma-kapısı, okuma-uyarısı değil).
9. **CI**: `.github/workflows` içine ucuz doc-lint (ölü host grep'i) — `canary.DELETED_HOSTS`'ı kaynak al; ayrıca compose/Caddy sözdizimi doğrulama (`caddy validate`, `docker compose config`) — şu an CI yalnız pytest/frontend/gitleaks. Deploy job eklenmeden önce operatör kararı (mainnet).
10. **`AGENTS.md`/`HERMES.md`**: `HERMES.md` 381 satır, root SSH + IP içeriyor; kimlik bilgisi yok ama operatör kılavuzu ile `docs/OPERATOR_GUIDE.md` çakışıyor → birleştir/çapraz-referans.
11. **Ölü route/dosya temizliği önerisi** (operatör "sil" demeli — yıkıcı işlem kuralı): Caddyfile `lato-*` + 4 ölü host; `docker-compose.testnet.yml` (kullanılıyorsa taşı); `ops/` Manus dosyaları (VPS'te çalıştığı doğrulanmadan silinmemeli).

---

## 7. Riskler ve açık sorular

1. **Panel 502 [PROBE]** — birleşik panel (3 botun kill-switch/restart/breaker-reset proxy'si) şu an erişilemez; operatör izleme tek yüzeyi düşmüş olabilir. Container `efloud-panel` durumu VPS'ten doğrulanmalı (bu inceleme SSH yapmadı).
2. **Panel = tek nokta kontrol yüzeyi**: Basic auth + tek paylaşılan `DASHBOARD_PASSWORD` (3 bot aynı şifre, `rotate-credentials.sh`). Sızarsa 3 bota kill-switch/restart. Limiter var (10/istemci/15 dk, global 50) ama MFA/IP kısıtı yok. Risk-ops incelemesi önerilir.
3. **V2/V3 alarm körlüğü**: alerter/overseer/canary yalnız V1; V2/V3 `AUTOSTART=0` ama açılırsa SL/TP-hata/orphan Telegram uyarısı yok (§3 #8).
4. **`deploy.sh` tam-stack recreate** (§3 #7): operatör skill'i izlerse 3 mainnet container eşzamanlı yeniden oluşur; açık pozisyon varken entry/SL koruması reconcile'a bağlı.
5. **Caddy ACME gürültüsü / rate-limit**: 4 çözümlenemeyen host için sürekli sertifika denemesi → Let's Encrypt failed-validation limitine takılma riski, geçerli host'ları etkilemez ama log'u kirletir.
6. **Eski IP'ye işaret eden `bot.ualgotrade.com` A kaydı**: IP başka bir kiracıya geçerse subdomain-takeover benzeri risk (canary `bot.u2algo.com` için bunu denetliyor, `ualgotrade` için yok). Domain operatörde; DNS kaydı silinmeli veya yeni IP'ye çekilmeli.
7. **`autoheal` + `docker.sock`** root-eşdeğeri; imaj sabitlenmiş (1.2.0) iyi, ama sidecar ele geçirilirse tüm host.
8. **Gizli bilgi**: `.env.production`, `.env.production.long`, `.env.production.scalp` (VPS'te, repoda değil), `.env.railway` (yerel; `skills/efloud-railway-supabase`), `x_tokens.example.json` yalnız şablon. Repoda değer okunmadı. `u2algo-site` Supabase service-role anahtarı Railway env'inde (memory).
9. **Sosyal hat hukuki/ürün**: topluluk Telegram kanalı + IG Reels sinyal paylaşımı "yatırım tavsiyesi değildir" disclaimer'ı kodda zorunlu (compliance kapısı); ancak regülasyon yeterliliği DOĞRULANMADI, `P-003 §2b` operatör/hukuk kararı bekliyor.
10. **Açık sorular (operatör)**: (a) panel neden 502 ve nerede çalışmalı; (b) `bot.ualgotrade.com` kalıcı mı kaldırılacak, yeni IP'ye mi taşınacak; (c) V2/V3 ne zaman aktifleşecek (alarm kapsamı bağlı); (d) sosyal hat zamanlayıcısı nerede (laptop/VPS cron/Composio); (e) `overseer` DRY_RUN ne zaman kapanacak; (f) testnet forward-A/B örneği gerçekte hangi host'ta; (g) 2026-11-14 bu raporda **canlıya yalnız doküman PR'ı** gidecek (operatör kararı 1) — Caddy/compose düzeltmeleri bu yüzden **öneri**, uygulanmadı.

---

## 8. Fable'a özet

1. **Güncel yüzeyler (probe'lu kanıt):** dashboard `https://2-28-139-82.nip.io` (healthz ok), `v2.`/`v3.` alt hostları, site `https://u2algo.com` (Railway). **Ölü:** `bot.u2algo.com` (DNS silindi), `bot.ualgotrade.com` ve `178-104-122-91.nip.io` (eski VPS IP'si, timeout). CLAUDE.md'deki "3 URL" karmaşasının cevabı bu.
2. **Birleşik panel şu an 502** (`panel.2-28-139-82.nip.io`); `docker-compose.panel.yml` prod compose'a dahil değil, deploy.sh bilmiyor → panel orphan.
3. **Oturumdaki CLAUDE.md bayat kopya**: master CLAUDE.md (76 satır, anayasa-only) zaten düzeltilmiş; ana checkout 81 commit geride. İlk iş: ana checkout senkronu — yoksa her ajan ölü URL/"Next.js 15"/"229 test" bilgisiyle çalışır.
4. **`deploy/Caddyfile`**: 4 ölü host (`bot.ualgotrade.com`, `v2.u2algo.com`, `scalp.u2algo.com`, `bot.u2algo.com`) + 2 ölü `lato-*` route (502) + IP yorumu yanlış (`178.104.122.91` yazıyor, nip.io `2.28.139.82`'ye çözülüyor). Temizlik = deploy PR'ı, operatör onayı + `caddy reload`.
5. **`deploy/deploy.sh` tam-stack `build+up -d`** (3 mainnet bot'u birlikte yeniden oluşturur) fiili tek-servis `--no-deps` pratiğiyle çelişiyor; `skills/efloud-deploy` hâlâ `deploy.sh`'yi tarif ediyor. Skill ve script güncellenmeli (risk-ops review).
6. **Sidecar/canary kapsamı yalnız V1**: alerter, overseer, canary V2/V3'ü izlemiyor; long suspended, scalp durumu belirsiz. Aktifleşmeden önce kapsam kararı gerek.
7. **Sosyal hat**: kod olgun (3 kapı varsayılan kapalı, ffmpeg varsayılan; Higgsfield ÇÜRÜTÜLMÜŞ — fiyat etiketlerini bozuyor), ama **VPS'te zamanlayıcı yok** ve cron örnekleri container volume/yol gerçeğiyle çelişiyor (`efloud_content_jobs` yalnız `efloud-bot`'ta). "Otomatik" ifadesi KANITSIZ.
8. **Ölü/şüpheli bileşenler**: `ops/` Manus+Cloudflare tunnel IG yolu (Composio'ya geçildi), `skills/efloud-railway-supabase` (Railway bot servisi silindi), `docker-compose.testnet.yml`, overseer `DRY_RUN=1` (Week-1 yorumu aylardır duruyor), `collab/STATUS.md` 7 gün bayat.
9. **CI'da deploy yok, doc/compose lint yok** (pytest, backtest-slow, gitleaks, frontend var). Öneri: canary sabitlerini tek doğruluk kaynağı yapıp doc-lint + `caddy validate`/`compose config` ekle.
10. **Trade mantığı değişikliği önerilmiyor**; platform→motor arayüzü (kill-switch/breaker-reset proxy'si, panel tek şifre) risk-ops incelemesine adaydır, kod değişikliği backtest-gate gerektirmez ama operatör onayı gerekir.
