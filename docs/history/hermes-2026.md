# Hermes — tarihçe (2026)

> **TARİHSEL — 2026-11-14'te HERMES.md'den taşındı** (kaynak: `git show 688d128:HERMES.md`).
> Aşağıdaki bölümler orijinal metnin **aynısıdır**; düzeltilmez (append-only). Güncel bilgi:
> anlık durum → `collab/STATUS.md` · operatör komutları → `docs/runbooks/operator-runbook.md` ·
> Hermes ajanının güncel rolü → `collab/models/hermes.md` (tek tanım) · canlı giriş akışı → `CONTEXT.md`.
>
> Bilinen bayatlıklar (ECC audit 2026-11-14, `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md`):
> §3 ve §14'teki Hermes tanımları `collab/models/hermes.md` ile çelişir; `agents/tasks/` ve
> `agents/TASKBOARD.md` yoktur (X26). §5b'deki "limit emir" / OB-BB akışı LuxAlgo modu öncesidir;
> canlı giriş MARKET emirdir (X2). Sayılar ve SHA'lar 2026-10-02 anlık görüntüsüdür.
> Daha eski "§6 Deploy Senaryosu — Adım 1–4" (zero-risk deploy, shadow aktivasyon, baseline
> backtest, S7 rollout) metni: `git show d137eb6^:HERMES.md`; Adım 3'ün güncel karşılığı
> runbook'taki "§6 Adım 3 (eski HERMES.md)" bölümüdür.

---

## Orijinal başlık (HERMES.md satır 1–8)

### HERMES.md — Efloud-bot Operatör Kılavuzu

> Operatör/insan onay zinciri (Hermes) için. Yönetim kılavuzu.
> **Çok-model ortak çalışma (2026-11-04):** önce `collab/README.md` + `collab/prompts/hermes-onboarding.md`. Çalışma klonu `~/work/efloud-bot` (PROD `/opt/efloud-bot` değil).
> **Güncel durum (master / VPS HEAD / konteynerler / açık sorular): `collab/STATUS.md`.**
> Bu dosyadaki tarihli bloklar (§2, §5b, §5c; 2026-10-02 anlık görüntüsü, `c8dc5c8`) TARİHSEL'dir.
> Canlı giriş akışı ve etkili/inert config anahtarları: `CONTEXT.md`.

---

## 2. Şu An Ne Durumda?

> **TARİHSEL (2026-10-02 anlık görüntüsü).** Güncel değerler için `collab/STATUS.md`'ye bak;
> SHA satırları bayattır.

| Şey | Durum |
|---|---|
| **GitHub master** | `c8dc5c8` — BOS girişleri + acil bakiye HALTI kaldırıldı |
| **VPS HEAD** | `c8dc5c8` (deploy edildi, bot sağlıklı) |
| **Bot container** | Hetzner VPS'te `Up (running)` — v2 ile trade ediyor |
| **Production dry_run** | `false` (CANLI MAINNET) |
| **Mainnet guard** | `EFLOUD_ALLOW_MAINNET=1` (env'de) |
| **AUTOSTART** | `0` — manuel Start gerektirir (incident-recovery posture) |
| **Açık pozisyonlar** | Dashboard'dan kontrol et: `https://2-28-139-82.nip.io` |
| **v2 flag durumu** | `smc_version=v2`, `smc_v2_symbols=[BTC,ETH,XRP,DOGE,SOL,...]`, `smc_v2_shadow=false` → **AKTİF (CANLI EMİR)** |
| **Acil bakiye HALTI** | `emergency_balance_threshold=0` → **KALDIRILDI** (2026-10-01 operatör kararı) |
| **Volatil rejim** | `allow_volatile_entries=true` → volatil piyasada girişler açık |

---

## 3. Hermes Rol Tanımı (CLAUDE.md §3)

**Hermes yapar** (insan):
- VPS SSH, `docker compose up -d`, `backend.migrate up`.
- `configs/config.phase2_1k.yaml` risk/safety/mainnet edit.
- PR sign-off, prod merge onayı.
- Incident response (canlı müdahale).
- Mainnet aç/kapa, leverage/sizing değişim.

**Claude yapar**:
- Kod, test, refactor öneri.
- PR hazırlığı.
- Backtest analizi, log değerlendirme.
- Docs, spec, plan.

**YASAK**:
- `EFLOUD_ALLOW_MAINNET=1` + `dry_run: false` kontrolsüz deploy.
- Compose/env değişiminde sadece `docker restart` (recreate gerekir).
- Risk/safety değişimi test/backtest olmadan mergeleme.
- Çoklu konuyu tek PR'da karıştırma.

---

## 5. SMC v2 Pipeline — Durum

### 5a. Tarihçe (özet)

SMC v2 pipeline 15 PR ile merge edildi (2026-05-23 → 2026-05-24, #63-#77):
pure modules (zones/sl_calc/tp_calc), SetupStateStore, confirm_entry (LTF
engulfing), select_htf_swing_anchor, trigger phase, entry order placement,
backtest harness, config flag + shadow mode.

### 5b. Bugün canlıda (2026-10-02)

> **TARİHSEL.** Aşağıdaki akış LuxAlgo modu öncesi efloud triggers yoludur; LuxAlgo modu açıkken
> bypass edilir (`configs/config.phase2_1k.yaml:180-188`). Canlı akış: §1 ve `CONTEXT.md`.

v2 **AKTİF ve CANLI EMİR veriyor**:
1. `configs/config.phase2_1k.yaml` → `engine.smc_version=v2` → SetupStateStore aktif.
2. `engine.smc_v2_symbols=[BTC/USDT, ETH/USDT, XRP/USDT, DOGE/USDT, SOL/USDT, ...]` → whitelist dolu.
3. `engine.smc_v2_shadow=false` → gerçek emir yerleştiriliyor.

**Giriş akışı (CHoCH + BOS)**:
```
LTF (15m) CHoCH/BOS kırılımı
  → HTF bias uyumu (BULL/BEAR)
  → kırılımı yapan OB/BB bölgesi (veya FVG/OTE fallback)
  → SetupCandidate(state=AWAITING_PULLBACK)
  → fiyat bölgeye geri çekilir (retest)
  → engulfing teyidi (require_confirmation=true)
  → CONFIRMED → limit emir
  → SL: likidite çizgisi (kırılım öncesi swing) ötesinde
```

**v1 susturma**: v2'nin sahiplendiği sembollerde v1 sinyal girişleri
`_v2_entry_active()` ile susturulur — kırılım anında market emri girilmez.

### 5c. Son operatör revizyonları (2026-10-01/02)

> **TARİHSEL.** Sonraki değişiklikler: `collab/log/*.md`; bazı değerler sonradan değişti
> (ör. `max_zone_overshoot_atr` → `configs/config.phase2_1k.yaml:168`).

| Tarih | Değişiklik | Commit |
|---|---|---|
| 2026-10-02 | BOS kırılımları da setup üretiyor (CHoCH ile aynı pullback akışı) | `658a905` |
| 2026-10-01 | Acil bakiye HALTI kaldırıldı (emergency_balance_threshold=0) | `b2154c5` |
| 2026-10-01 | v1 MARKET girişi v2 canlı sembolde susturuldu | `b2154c5` |
| 2026-10-01 | Bölge aşım toleransı 0.5→2.0 ATR | `228382d` |
| 2026-10-01 | Volatil rejim girişleri açıldı (allow_volatile_entries=true) | `228382d` |

---

## 13. Sosyal Medya Yayın Pipeline'ı (YENİ — 2026-07-26)

Bot sinyallerini otomatik chart + video + caption olarak X, Instagram, YouTube'da
paylaşmaya hazırlar. **Varsayılan duruş: hiçbir şey yayınlanmaz.** Üç bağımsız
güvenlik kapısı var.

### Tek komutla çalıştırma

```bash
cd /opt/efloud-bot
python -m scripts.daily_social_run --date "$(date -u +%F)"
```

### Pipeline Zinciri

```
Lane A (bot)  → ContentJobEmitter (JSONL)            engine/content_jobs.py
Lane B        → analiz artifact                       scripts/lane_b_consumer.py
Lane C        → compliance-gated caption + levels      scripts/lane_c_copywriter.py
Lane D        → markalı chart PNG (ENTRY/SL/TP)       scripts/chart_render.py
Lane G        → per-platform bundle + MP4 klip        scripts/lane_g_social.py
Lane G pub    → onaylı bundle → platform dispatch      scripts/lane_g_publish.py
```

### Üç güvenlik kapısı (hepsi default KAPALI)

1. **Onay kapısı** — `--auto-approve` verilmezse tüm bundle'lar `pending_review`
2. **Live kapısı** — `--live` verilmezse yayın dry-run
3. **Platform flag'leri** — `X_API_ENABLED`, `INSTAGRAM_ENABLED`, `YOUTUBE_ENABLED`

Üçü de açılmadan dışarıya TEK BİT veri çıkmaz.

### Medya formatları

| Platform | Medya | Geometri |
|---|---|---|
| X | Still PNG | 1080×1350 |
| Instagram | Still PNG | 1080×1350 |
| Reels | Vertical MP4 | 1080×1920 |
| YouTube Shorts | Vertical MP4 | 1080×1920 |

Video backend: **ffmpeg** (default, pixel-exact, ücretsiz). Higgsfield opt-in
ama fiyat etiketlerini bozduğu için sinyal chart'larında KULLANILMAZ.

### Cron (sadece üretim, yayın yok)

```
0 * * * * cd /opt/efloud-bot && python -m scripts.daily_social_run --date "$(date -u +%F)" >> /app/logs/social.log 2>&1
```

### Bug fix'ler (bu güncelleme ile)

- Instagram: `render_promo_card` import hatası → her paylaşım ImportError (düzeltildi)
- YouTube: `video_path=None` hardcoded → Shorts'a video yüklenemiyordu (düzeltildi)

### Detaylı doküman

`skills/social-publishing/SKILL.md` — tüm modüller, API'ler, testler, cron pattern'leri.

**Bot canlı, kararlı, kod %100 hazır. Acele yok, risk yok.**

---

## 14. Çoklu ajan düzeni

- **Kilo Code:** orchestrator; görevleri `agents/tasks/` altına yazar ve `agents/TASKBOARD.md` üzerinden takip eder.
- **Claude:** kod, test, hata düzeltmesi ve inceleme. Hermes kod kusurlarını bulgularla Claude'a devreder; bot kaynak mantığını değiştirmez.
- **Hermes Agent:** terminal ve operasyon; görevleri okuyup yürütür, doğrular ve sonuçlarını görev dosyasına işler. `hermes_tasks/` yereldir, commit edilmez. `agents/` protokolü varsa `agents/README.md` ve taskboard önceliklidir; yoksa eksikliği bildir, protokol varmış gibi davranma.
- **Güvenlik:** sır değerleri ve secret içeren çıktı asla raporlanmaz veya commit edilmez. Canlıya dokunan işlemlerde Telegram üzerinden açık kullanıcı onayı, deploy/restart/config/breaker reset öncesi güncel açık pozisyon kontrolü gerekir. Açık pozisyon varsa görev açıkça izin vermedikçe dur ve ayrıca onay iste. `emergency_balance_threshold` operatör onayı olmadan değiştirilmez.
- **Sonuç:** secret'sız komutlar, kısaltılmış çıktılar, commit hash ve healthz yanıtı görevde bulunur; doğrulanamayanlar işaretlenir. Aynı komut iki kez başarısız olursa üçüncü kez denenmez, görev blocked yapılır.
- Repo `skills/` altındaki operasyon rehberleri Hermes skill biçimindedir. Hermes'in bunları otomatik görmesi için ilgili dış skill dizini yapılandırılmalı veya ayrı kurulmalıdır; repo dosyalarının varlığı otomatik yüklemeyi garanti etmez. Bkz. https://hermes-agent.nousresearch.com/docs/user-guide/features/skills.
