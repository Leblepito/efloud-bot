# Sonraki Adım — Task Distribution (Bot V2 + Growth + Audit)

> **Tarih:** 2026-06-20 · **Üreten:** Claude (Opus 4.8). Master plan: `.claude/plans/cryptic-dazzling-balloon.md`.
> Bu doküman: açık PR/branch durumu + Gemini çıktı analizi + ajan başına görev dağılımı (RACI) + Hermes/Leblep prompt'ları + operatör gate'leri.

## 1. Açık PR / branch durumu (8 branch push'lu)
| PR | İçerik | Review | Merge notu |
|----|--------|--------|-----------|
| #233 | V2 long-bot config (`config.phase2_long_1k.yaml`) | risk-ops APPROVE_WITH_NITS | additive; deploy gated |
| #234 | Leblep scaffolding + Gemini infra handoff | lint 8/8 | doc/LLTODO |
| #235 | u2algo.com rebuild+growth spec | doc | doc |
| #236 | A5 multi-instance persistence (migration 012 `bot_id`) | code-review + risk-ops APPROVE | code safe; **live DB-apply gated** |
| #237 | Track-A bot-ops audit + backlog | 3-agent doğrulama | doc |
| **#238** | **P3 quick-wins SEC-1/SEC-2/CFG-1 (Gemini impl)** | **risk-ops APPROVE_WITH_NITS** | **⚠️ deploy gate: prod SESSION_SECRET doğrula** |
| (branch) `chore/session-log-2026-06-20-s3` | session log | — | ops. |
| (branch) `docs/2026-06-20-task-distribution` | bu doc + LB-001 | — | doc |

**Squash-merge önerilen sıra** (çakışma YOK — hepsi farklı dosya): docs (#235, #234, #237) → #233 (config) → #236 (A5 code) → #238 (P3, **deploy-gate sonrası**).

## 2. Gemini çıktı analizi (antigravity-IDE oturumu)
Gemini, relay edilmemiş Bot-V2-infra prompt'u yerine repo'daki audit/handoff doc'larından **P1 site-infra doğrulaması + P3 quick-win'leri** yaptı:
- **DB (u2algo MARKETING sitesi):** Supabase `kjaicqpqfwnfbioofdib` üzerinde `entitlements` + `waitlist_leads` (consent/consent_at) + advisor-cleanup tabloları CANLI doğrulandı (REST 200). ⚠️ Bu BOT V2 değil — marketing/waitlist DB'si. A5 bot-persistence (migration 012) ayrı, dokunulmadı.
- **DNS:** bot.ualgotrade.com→Hetzner ✓; u2algo.com/www→mevcut Railway (Vercel cutover operatör-registrar bekliyor). bot.u2algo.com (V2 dashboard) Gemini scope'unda YOKtu.
- **P3 kod:** SEC-1/SEC-2/CFG-1 working-tree'de **loose** bırakmıştı → Claude `feat/p3-quick-wins-gemini` branch'ine aldı + risk-ops review → **PR #238**.

## 3. RACI — Sonraki faz görev dağılımı
| İş | Owner | Review | Sign-off / Gate |
|----|-------|--------|-----------------|
| 5+1 PR squash-merge | @operator | (review yapıldı) | operatör |
| #238 deploy gate (prod SESSION_SECRET) | @operator + @hermes | @claude | operatör |
| Bot V2 VPS bringup (key sonrası) | @hermes | @claude risk-ops | operatör mainnet |
| V1 recalibration ($2075→$1035) + breaker reset | @hermes | @claude risk-ops | operatör (fon transferi SONRASI) |
| A5 live DB-apply (snapshot→klon→idempotency) | @hermes | @claude | operatör |
| u2algo.com Vercel cutover (DNS/registrar) | @operator | @gemini | operatör |
| Bot V2 key permission kararı | @leblep (DECIDE) → @operator | @claude adversarial | operatör (LB-001) |
| BT-1 funding default + R1 correlation (backtest-gated) | @claude/@gemini | @claude | backtest gate + operatör |
| Growth Faz-1+ (P-002.5) | @hermes + @manus (draft) | @claude compliance | operatör (CAC/handles) |

## 4. HERMES görev prompt'u (operatör relay eder — key + gate'ler hazır olunca)
```
Sen efloud-bot @hermes'sin (VPS deploy + mainnet sign-off owner). GÖREV: Bot V2 (paralel
long-bot) VPS bringup + V1 recalibration. ÖNCE OKU: LLTODO/PROMPT-hermes.md,
.claude/plans/cryptic-dazzling-balloon.md (yoksa docs/handoff/2026-06-20-bot-v2-and-orchestration-handoff.md),
docs/handoff/2026-06-20-next-step-task-distribution.md.

ÖN-KOŞUL (operatör sağlar): yeni Binance V2 hesabı funded ~$1035 + FLAT, V2 API key+secret,
DNS bot.u2algo.com→<VPS_IP>. Merge'li master (#233 config + #236 A5).

ADIMLAR (her biri öncesi flat-book + healthz doğrula):
1. VPS'te deploy/.env.production.long oluştur (V2 key+secret, EFLOUD_CONFIG_PATH=
   configs/config.phase2_long_1k.yaml, EFLOUD_STATE_DIR=/app/state_long, EFLOUD_BOT_ID=v2-long,
   EFLOUD_AUTOSTART=0, distinct DASHBOARD_PASSWORD/SESSION_SECRET, ENV=production). chmod 600.
2. preflight.py V2 env ile (read-only): canTrade=true, balance≈$1035, FLAT doğrula.
3. docker-compose.prod.yml'e efloud-bot-long servisi + Caddy bot.u2algo.com bloğu (Gemini'nin
   diff-önerisi varsa kullan; yoksa master plan A2). compose up -d efloud-bot-long (idle).
4. Go-live checklist (master plan A7): cert/healthz/profile-long(1h/8h/1w)/balance≈$1035(NOT $10k)/
   margin-setup ISOLATED+lev5+one-way/state_long izolasyon/V1 regresyon-yok.
5. V1 recalibration: operatör fon çektikten SONRA configs/config.phase2_1k.yaml safety $1035'e
   (PR ile, risk-ops). Restart. SONRA breaker reset (POST /breaker/reset) — sıra kritik.
6. A5 live DB-apply (DB açılacaksa): snapshot→klon-dry-run→idempotency→apply→V1 row bot_id='v1'
   backfill doğrula. V1 için EFLOUD_BOT_ID UNSET kalır.
HANDOFF: format-patch + sha256 (Telegram yasak). Her mainnet adımı operatör sign-off'lu.
SELF-ONLY: sana verilmeyen (kod/algo) işi yapma; sorun varsa Claude'a rapor.
```

## 5. LEBLEP ilk görev (LB-001 — operatör relay eder)
`LLTODO/leblep/LB-001-bot-v2-key-permissions.md` = Bot V2 API-key permission posture **DECIDE** (withdraw+transfer açık + IP-yok vs canWithdraw=false + IP-whitelist). Operatör "withdraw açık, IP-yok, problem yok" dedi; bu çok-model ikinci-görüş. Akış: operatör LB-001'i Leblep'e iletir → `.response.md` commit → Claude adversarial review → operatöre tek-cümle tavsiye.

## 6. Operatör gate'leri (özet)
1. 5+1 PR merge (sıra §1). 2. #238 deploy gate (prod SESSION_SECRET). 3. Yeni Binance V2 hesabı+key+funded($1035)+FLAT (transfer Claude+operatör birlikte). 4. DNS bot.u2algo.com. 5. V1 recalibration+breaker-reset sign-off. 6. LB-001'i Leblep'e ilet. 7. (ops.) Gemini infra prompt (#234 handoff) relay — bot.u2algo.com compose/DNS için.

> **Güvenlik notu (Q2):** Bot withdraw/transfer'e ihtiyaç duymaz; `canWithdraw=false` + VPS-IP-whitelist plaintext-.env riskinin tek büyük mitigasyonu (audit S1). LB-001 bunu çok-model doğrular. Nihai karar operatörün.
