# claude-code — iş günlüğü (append-only)

> Yalnız claude-code yazar. Yeni giriş en alta eklenir, eskiler düzenlenmez. Format: `collab/README.md` §4.

## 2026-11-04 18:30 UTC — collab/ ortak çalışma alanı kuruldu
- task: (bootstrap) | branch/PR: feat/quarantine-hermes-skills (A) + feat/collab-protocol (B) | commit: PR'larda
- ne yapıldı: (A) Hermes'in 5 skill'i `skills/` → `collab/skills-incubator/` (aktif değil, REVIEW.md'li, karantina testi); (B) `collab/` protokolü (PR-only akış, draft-PR claim, güvenilmeyen metin yalnız laptop), MODELS/STATUS/MCP, 6 task, onboarding prompt'ları, layout testi.
- VPS: N/A
- not: VPS'e yalnız `~/efloud-collab-private/` dizini eklendi (export kopyası; kaldırılması T-20261104-04'te). `/opt/efloud-bot` ve container'lara dokunulmadı. TradingView MCP laptopta CDP ile bağlandı.
- istek: abacus → T-20261104-02, T-20261104-01 · hermes → T-20261104-05 · operator → T-20261104-04

## 2026-11-04 18:10 UTC — STATUS + T-04 güncellemesi (#268 review takibi)
- task: T-20261104-04 | branch/PR: collab/claude-code/fix-status-t04 | commit: PR'da
- ne yapıldı: STATUS master satırı `71dfff5`; LuxAlgo satır referansı netleştirildi (`:182-183` bayrak, `:180-181` not); T-04 merge adımı işaretlendi.
- VPS: N/A
- istek: yok

## 2026-11-04 18:40 UTC — STATUS VPS satırı (#269 review takibi)
- task: T-20261104-04 | branch/PR: collab/claude-code/fix-status-vps | commit: PR'da
- ne yapıldı: master `68fdc9a`; VPS `b6c6bd1` 4 commit geride, fark yalnız doküman/test/.dockerignore (runtime yok) olarak düzeltildi.
- VPS: N/A
- istek: yok

## 2026-11-04 20:50 UTC — T-08 LuxAlgo bölge erken uyarısı (kod)
- task: T-20261104-08 | branch/PR: collab/claude-code/T-20261104-08-lux-zone-alert | commit: PR'da
- ne yapıldı: motor `[lux] near` log satırı (yalnız log, `smc_v2.luxalgo.near_alert_atr` yoksa kapalı); alerter `LuxZoneAlertRule` (near/touch/confirmed) + `V2RejectAlertRule` (env `EFLOUD_ALERTER_LUX_ALERTS`, default kapalı), olay başına dedup, LLM formatlayıcı atlanır, HTML escape; 283 komşu test yeşil; bağımsız review CHANGES → bulgular düzeltildi.
- VPS: N/A
- not: Alerter prod'da dry-run (T-20261104-10) — o düzelmeden mesaj gitmez. Alerter yalnız mid bot logunu okur.
- istek: hermes → review · operator → risk-ops gate + merge + deploy kararı
