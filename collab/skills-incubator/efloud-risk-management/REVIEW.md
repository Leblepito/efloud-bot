---
skill: efloud-risk-management
author: hermes
status: in-review
version: 645a5dc
---

# Review — efloud-risk-management

> Düzenleme notu (claude-code, 2026-11-04): `skills/` → incubator taşındı (`git mv`), SKILL.md'ye INCUBATOR banner'ı eklendi, içerik değişmedi.

## claude-code — 2026-11-04 — VERDICT: CHANGES (kritik)

**Kritik:** "Integration with efloud-bot Config" bölümü `risk:`/`safety:` değerlerini *eşleme* gibi sunuyor
ama canlı config ile çelişiyor. Bir agent bunu okuyup "config'i skill'e uydur" önerirse
backtest'le seçilmiş değerler geri alınır:

| Anahtar | Taslak | Canlı (`configs/config.phase2_1k.yaml`) | Not |
| --- | --- | --- | --- |
| daily_loss_limit_pct | 3.0 | 10.0 (`:348`) | operatör kararı |
| weekly_drawdown_limit_pct | 8.0 | 25.0 (`:349`) | operatör kararı 2026-06-01 |
| max_total_exposure | 3.0 | 6.0 (`:380`) | 10 pozisyon hedefi için |
| max_holding_hours | 48 | 36 (`:381`) | BT-sweep5: 48h daha kötü |
| min_sl_atr | 0.5 | 2.0 (`:383`) | BT-sweep5: 0.5 daha kötü |
| risk_per_trade_pct | 1-2% | 1.0 (`:248`) | |

**İstenen:**
1. Config tablosunu sil; yerine "kaynak = canlı config, bu skill sayı önermez" cümlesi.
2. Kanaldan gelen gerçek ilkeler (TP1 sonrası BE, kısmi kâr, chop'ta daha seçici ol) ayrı
   "kanal ilkeleri" başlığında, her biri mesaj id'siyle; motorda karşılığı varsa dosya:satır
   (BE: `_move_sl_to_breakeven`, `exchange/__init__.py:1642`).
3. Portfolio heat / korelasyon önerileri → hipotez başlığı; korelasyon guard'ı ayrı bir audit
   bulgusudur (R1; doküman repo'dan silindi, geçmişte: `git show 479590c:docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md`).
4. Promote hedefi: ayrı skill değil, `agents/risk-manager.md`'ye kısa bölüm.
