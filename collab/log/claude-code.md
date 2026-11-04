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

## 2026-11-04 19:45 UTC — OB/BB giriş açığı teşhisi (chart OB'leri vs. motor)
- task: (operatör isteği, claude-code oturumu) → takip T-20261104-07/08/09 | branch/PR: collab/claude-code/ob-entry-gap | commit: PR'da
- ne yapıldı: TradingView LuxAlgo kutuları (MCP, salt-okuma) + Binance 15m/12h verisiyle motorun kendi fonksiyonlarını bar-bar replay (10 sembol, 14 gün) + VPS log/state (salt-okuma) → `outputs/claude-code/2026-11-04-ob-entry-gap.md`; erken-uyarı önerisi (a) kabul, TV→motor girdisi (b) şimdilik red.
- VPS: N/A
- not: VPS'te yalnız `docker logs` / `docker exec … cat|python -c` ile okuma yapıldı; hiçbir dosya yazılmadı, bot start/stop yok. scalp/long botların idle olduğu bulundu → T-20261104-07 (operatör).
- istek: operator → T-20261104-07 · any → T-20261104-09 (review: abacus)
