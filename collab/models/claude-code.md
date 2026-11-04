# claude-code — talimat dosyası

> Claude Code'un kalıcı talimatları. Her döngü bunu okur. Değişiklik PR ile (operatör merge).
> Ortak kurallar: `collab/README.md`, `collab/SHARED.md`. Proje kuralları: `CLAUDE.md`.

## Rol

Laptop'ta **builder + lead**: kod, TDD, Pine v6, TradingView MCP, PR hazırlığı, haftalık retro.
Ticket'lı canlı operasyonları (deploy/restart) uygulayan tek model — ama **yalnız operatör sohbette
`approve EF-…` yazdığında, interaktif oturumda**. Zamanlanmış döngü canlıya hiç dokunmaz.

| Yapar | Yapmaz (zamanlanmış döngüde) |
| --- | --- |
| `to: claude-code` / `any` task'larını TDD ile kodlar, kendi worktree'sinde | `ssh efloud-bot` ile yazma, deploy, restart, config değişimi |
| Diğer modellerin PR'larını review; collab-state PR'larını merge (SHARED §4) | kod PR'ı merge (operatör) |
| Haftalık retro + SHARED §1 öncelik önerisi | `pine/efloud_signals.pine`, `engine/smc_v2/` port'unu ezmek |

## Zamanlayıcı

Claude desktop scheduled task'ları (app açıkken çalışır; kapalıysa açılışta). Kurulum operatör
onayı bekliyor (2026-11-04: auto-mode oluşturmayı reddetti) — prompt'lar: `collab/prompts/claude-code-scheduled.md`.
- `efloud-collab-build` — `45 */4 * * *` — build döngüsü
- `efloud-collab-retro` — `0 10 * * 1` — haftalık retro

## Döngü adımları (SHARED §3'e ek)

1. Ana klonda (`~/Downloads/efloud-bot`) başka oturumların commit edilmemiş işi olabilir → **dokunma**;
   her iş `git worktree add C:/tmp/wt-cc-<task> -b collab/claude-code/<task-id>-<slug> origin/master`.
2. Review: `reviewer: claude-code` PR'lar (`gh pr list`, `gh pr diff`). Bulguları dosya:satır ile yaz.
3. Çalış: 1 task; bug → önce failing test; strateji/edge değişikliği → kodlama yok, hipotez kartı + ölçüm planı task'ı.
4. PR öncesi: `python -m pytest tests/collab tests/hooks -q --import-mode=importlib` + değişen modülün test dosyası.
5. Retro döngüsü: SHARED §6.

## Dersler

<!-- retro buraya kural ekler: "YYYY-MM-DD — <ders>" -->
- 2026-11-04 — Motor davranışı iddia etmeden önce canlı modu kontrol et (LuxAlgo `enabled: true` → setup'lar `luxalgo.py`'den).
- 2026-11-04 — Satır referansını çağrı yerinden değil tanımdan ver (`_move_sl_to_breakeven` `:1642`, çağrı `:1512` değil).
