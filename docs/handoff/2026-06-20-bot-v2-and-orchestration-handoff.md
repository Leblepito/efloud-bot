# Handoff — Bot V2 (paralel long-bot) + Ekip Orkestrasyonu

> **Tarih:** 2026-06-20 · **Üreten:** Claude (Opus 4.8) · **Plan:** `.claude/plans/cryptic-dazzling-balloon.md` (onaylandı)
> Bu doküman operatörün **relay edeceği Gemini prompt'u** + sağlaması gereken **gate'leri** + güncel **durumu** tutar.

## Özet
Mevcut bot (`bot.ualgotrade.com`, Hetzner, profile **mid 15m**) yanına **paralel ikinci bot** (profile **long 1h/8h/1w**) kurulur. Yeni Binance cüzdanı ~**$1035** (mevcut $2075'in yarısı transfer; V1 de ~$1035'e iner), domain **bot.u2algo.com**, compute **Hetzner**'da, veri **Supabase**'de. Gerekli testlerden sonra doğrudan canlı.

## Claude'un BİTİRDİĞİ işler (bu oturum)
| İş | Durum |
|---|---|
| A0 — C1/C4 balance fail-closed | ✅ DOĞRULANDI zaten mevcut (`7c35f5b`); ek PR gerekmez |
| A1 — V2 config `configs/config.phase2_long_1k.yaml` | ✅ Oluşturuldu + validate (profile long→1h/8h/1w, $1035 kalibre). Branch `feat/bot-v2-long-config` @ `5e2291f` |
| A1 — risk-ops review | ✅ **APPROVE_WITH_NITS** (hiçbir guard zayıflamadı, V1'den sıkı). Nit'ler plana dahil |
| Leblep scaffolding | ✅ `LLTODO/PROMPT-leblep.md` + `LLTODO/leblep/` (README + TEMPLATE-LB). Branch `feat/orchestration-leblep` |
| Master plan | ✅ `.claude/plans/cryptic-dazzling-balloon.md` (onaylı) |

> Branch'ler **lokal, push/PR operatör onayına bırakıldı**. Hiçbiri canlıya deploy edilmedi (additive, ayrı container).

## Operatörün sağlaması gereken GATE'ler
1. **Yeni Binance hesabı** + API key (`canTrade=true`, `canWithdraw=false`) + **VPS IP'sini (<VPS_IP>) IP-whitelist'e** ekle.
2. **$1035 transfer:** mevcut hesaptan yeni hesaba; yeni hesap **FLAT** (pozisyon/order yok — margin/position-mode değişimi flat-book ister).
3. **DNS:** `bot.u2algo.com` A-record → `<VPS_IP>`.
4. **Supabase:** proje + connection string/keys (Option A=paylaşılan proje + bot_id migration / Option B=ayrı proje — Gemini karar verecek).
5. **V1 breaker reset kararı** + V1 recalibration ($2075→$1035) sign-off (mainnet) — **fon transferinden SONRA**.

## Sıra (kritik)
1. Operatör fonu çek (V1 → ~$1035) → V1 recalibration config + restart + breaker reset (reset **recalibration'dan SONRA**, yoksa stale peak → sahte drawdown → anında re-HALT).
2. Gemini infra prep (aşağıdaki prompt) → Hermes uygular → Claude cross-test → operatör sign-off.
3. V2 bringup (preflight → margin setup → AUTOSTART=0 idle validate → go-live checklist → Start).
4. Supabase persistence ayrı additive PR (migration 012 `bot_id` + db.py threading) — bringup'tan decouple.

---

## ⬇️ GEMINI 3.5'E RELAY EDİLECEK PROMPT (operatör kopyala-yapıştır)

> Yeni bir Gemini oturumu aç, aşağıdaki bloğu yapıştır. Gemini repo'yu bilmez — credential/bağlantı yerleri açıkça verildi.

```
Sen efloud-bot projesinde @gemini ajanısın. GÖREV: "Bot V2" (paralel long-bot) için
ALTYAPI HAZIRLIĞI tasarla/yürüt (P1 infra prep). Trade mantığına DOKUNMA.

ÖNCE OKU (GitHub Leblepito/efloud-bot, master):
  - LLTODO/PROMPT-gemini.md, LLTODO/CONSENSUS.md  (consensus/handoff disiplini)
  - CLAUDE.md  (Karpathy 4 prensip; trade-path dokunulmaz)
  - docs/superpowers/specs/2026-06-20-u2algo-rebuild-and-growth-program-design.md  (domain mimarisi)
  - .claude/plans/cryptic-dazzling-balloon.md  YOKSA: docs/handoff/2026-06-20-bot-v2-and-orchestration-handoff.md

BAĞLAM: V1 bot Hetzner'da (<VPS_IP>) docker-compose.prod.yml + Caddy ile
bot.ualgotrade.com'da CANLI (profile mid). V2 = AYNI kod, profile LONG (1h/8h/1w),
YENİ Binance cüzdanı ~$1035, domain bot.u2algo.com, AYNI Hetzner VPS'te paralel
container, Supabase persistence. Compute Hetzner'da KALIR (Railway DEĞİL — Railway
yalnızca u2algo-site marketing içindir). V2 config Claude tarafından hazır:
configs/config.phase2_long_1k.yaml (branch feat/bot-v2-long-config).

CREDENTIAL/BAĞLANTI NEREDE:
  - VPS erişim: ssh alias `efloud-bot` (~/.ssh/config; key id_ed25519). Repo: /opt/efloud-bot.
  - Secrets (VPS-only, repo'da YOK): /opt/efloud-bot/.env.production.
    Şablon (tüm env var isimleri): deploy/.env.production.example
  - Sunucu bootstrap: deploy/setup-server.sh · Deploy akışı: deploy/deploy.sh
  - Reverse proxy: deploy/Caddyfile (bot.ualgotrade.com bloğu örnek)
  - Compose: docker-compose.prod.yml (efloud-bot servisi + named volumes örnek)
  - DB layer: backend/db.py (asyncpg pool; DATABASE_URL yoksa no-op; Supabase pooler
    için statement_cache_size=0 gerekebilir). Migrations: backend/migrations/001..011
    (010_breaker_state.sql = SINGLETON id=1 — iki bot aynı projede çakışır, bkz. deliverable 1).
    Migration flag: EFLOUD_AUTO_MIGRATE. Bot örnek-ayrımı env: EFLOUD_BOT_ID.
  - Hetzner rehberi (varsa): deploy/HETZNER_GUIDE.md

DELIVERABLES (kod yazma; tasarım + runbook + PR-able diff önerisi; Hermes uygular,
Claude cross-test eder, operatör sign-off):
  1. SUPABASE KARARI: Option A (paylaşılan proje + `bot_id` kolonu, migration 012 ile
     singleton breaker_state'i per-instance yap) vs Option B (V2 için AYRI proje, kod
     değişikliği yok) — gerekçeli seç. Seçilen yola göre provisioning + migration apply runbook.
  2. DNS: bot.u2algo.com A-record → <VPS_IP> (operatör panelde uygular; sen tam
     adımlar + doğrulama: `dig bot.u2algo.com`, `curl -I https://bot.u2algo.com`).
  3. VPS KAPASİTE: 2 bot için RAM/CPU headroom (`free -m`, `docker stats`) + birleşik
     Binance REST weight analizi (her bot 10 sembol × 30s loop × parallel_workers:3).
  4. docker-compose.prod.yml için `efloud-bot-long` servis bloğu DIFF önerisi (image:
     efloud-bot:latest, container_name efloud-bot-long, env_file .env.production.long,
     EFLOUD_CONFIG_PATH=configs/config.phase2_long_1k.yaml, EFLOUD_STATE_DIR=/app/state_long,
     EFLOUD_BOT_ID=v2-long, EFLOUD_AUTOSTART=0, ayrı volume'lar efloud_state_long/
     logs_long/reports_long, expose 8080 internal) + Caddyfile bot.u2algo.com bloğu.
  5. deploy/.env.production.long.example şablonu (GERÇEK key YOK — Hermes VPS'te doldurur).
  6. Operatör gate checklist (yeni Binance acct IP-whitelist→VPS IP, canWithdraw=false,
     $1035 funded + FLAT, DNS, Supabase keys).

KISIT: additive/flag-OFF; V1 servisleri/volume'ları/state'i DOKUNULMAZ; secrets repo'ya
GİRMEZ (gitleaks); V2 izolasyonu zorunlu (distinct container_name/volume/config/.env/Binance
key). Çıktıyı docs/runbooks/ altında runbook + PR-able diff olarak ver; Claude review + Hermes apply.
SELF-ONLY: sana açıkça verilmeyen işi (trade mantığı, V1 değişikliği) yapma.
```

---

## Leblep orkestratör (yeni ekip üyesi)
- Rol kartı: `LLTODO/PROMPT-leblep.md` · İstek lane'i: `LLTODO/leblep/` (README + TEMPLATE-LB).
- Claude zor/cross-cutting kararları, backlog-üretimini ve plan-dağıtımını Leblep'e `LB-XXX` isteğiyle delege eder; operatör relay eder; Claude yanıtı adversarial review eder.
- Modlar: DECIDE / DESIGN / GENERATE-BACKLOG / SPLIT-DISTRIBUTE.

## Sonraki Claude işleri (gate'lerden bağımsız, sıraya hazır)
- A5 Supabase migration 012 (`bot_id`) + `backend/db.py` threading + TDD (additive, deferred PR).
- P3 bot-ops audit (Track A, read-only) — institutional-lens bulgularını ölçeğe-uygun fix backlog'una çevir.
- P4 u2algo.com site rebuild Phase 0 (spec: `docs/superpowers/specs/2026-06-20-u2algo-rebuild-and-growth-program-design.md`).
