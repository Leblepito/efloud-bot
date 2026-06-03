# 06 — Agent Team Setup (efloud-bot)

> Phase 6 deliverable. İki ayrı "agent ekibi" var: (A) **dev-time** Claude Code
> subagent'ları (`.claude/agents/`) ve (B) **runtime** LLM advisory team (`engine/agents/`).
> Bu doküman ikisinin de kimliğini, sorumluluğunu, ne-zaman-hangisi karar ağacını,
> ve değişmez hard-rule'larını belgeler. Tarih: 2026-06-02.

---

## A. DEV-TIME subagent roster (`.claude/agents/`)

### Mevcut (lokal, master)
| Agent | Model | Rol | Ne zaman çağır |
|---|---|---|---|
| `risk-safety-auditor` | **opus** | safety/risk/lifecycle/config safety blokları audit | `engine/safety/`, `engine/risk/`, `lifecycle.py`, config `safety:` dokunulunca |
| `smc-strategy-reviewer` | **opus** | SMC mantık değişikliği (BoS/CHoCH/OB/FVG/OTE/swing) | `engine/smc*.py`, `signals.py`, `confluence.py`, `smc_v2/**` dokunulunca |
| `backtest-runner` | sonnet | backtest çalıştır + özetle | confluence/risk/regime tuning sonrası |
| `agent-team-engineer` | sonnet | `engine/agents/` geliştir, `/api/ai/*` wire | runtime agent rolü ekleme/değiştirme |
| `api-integration` | sonnet | `backend/api.py` endpoint pattern enforce | api.py endpoint dokunulunca |
| `efloud-explorer` | (Read/Grep/Bash) | read-only kod-map | değişiklik ÖNCESİ keşif |
| `efloud-code-reviewer` | default | atomik PR / overengineering / test coverage review | her push/PR öncesi |
| `efloud-risk-ops-reviewer` | default | sermaye-koruma diff review | risk-path diff'lerinde |
| `efloud-test-engineer` | (Write/Edit) | pytest test yaz+çalıştır | bugfix/feature sonrası |

### #117 ile gelen (sponsor README branch — henüz master'da değil)
| Agent | Rol | Audit kullanımı |
|---|---|---|
| `quant-strategy-analyst` | İstatistiksel edge / overfit / backtest rigor | Phase 3 (persona ile simüle edildi — agent lokalde yoktu) |
| `fund-manager-overseer` | Portföy/korelasyon/sermaye riski | Phase 3 |
| `market-microstructure-expert` | Crypto-perp microstructure / SMC fidelity / LuxAlgo | Phase 3 |
| `live-ops-sentinel` | Canlı-ops izleme / incident | gelecek |

### Örtüşme analizi (Phase 4 ile bağlantılı)
| Çift | Karar | Gerekçe |
|---|---|---|
| `efloud-explorer` ↔ built-in `Explore` | **KORU ikisi** | efloud-explorer Bash'li (graphify query); Explore generic. Hafif örtüşme, zararsız |
| `efloud-risk-ops-reviewer` ↔ `risk-safety-auditor` | **NETLEŞTİR** | İkisi de safety-path. Öneri: `risk-safety-auditor`=derin audit (opus, mevcut kod), `efloud-risk-ops-reviewer`=diff-review (PR öncesi). Rolleri .md'de ayır, ikisini de tut |
| `efloud-code-reviewer` ↔ `/code-review` skill | **KORU** | skill=cloud multi-agent; agent=lokal hızlı. Farklı tetikleyici |
| `agent-team-engineer` ↔ `api-integration` | KORU | farklı dosya alanları (engine/agents vs backend/api) |

**Öneri:** Eski `efloud-*` prefix ile yeni kanonik agent'lar arası **gerçek duplicate YOK** — sadece efloud-risk-ops-reviewer vs risk-safety-auditor'da rol netliği gerek. #117 merge olunca 4 yeni advisor agent kanonik olur; toplam 13 agent yönetilebilir. Arşivlenecek agent YOK.

### Karar ağacı — hangi dev-agent ne zaman
```
Görev tipi?
├─ Geniş read-only keşif → Explore / efloud-explorer
├─ Kod değişikliği yapacağım, hangi alan?
│   ├─ safety/risk/lifecycle/config-safety → ÖNCE plan, SONRA risk-safety-auditor (opus)
│   ├─ SMC/signals/confluence/smc_v2 → smc-strategy-reviewer (opus)
│   ├─ backend/api.py endpoint → api-integration
│   ├─ engine/agents runtime layer → agent-team-engineer
│   └─ test yazımı → efloud-test-engineer
├─ Strateji/edge sorusu → quant-strategy-analyst (+ fund-manager-overseer / market-microstructure-expert paralel)
├─ Backtest çalıştır → backtest-runner
├─ PR/push ÖNCESİ → efloud-code-reviewer (+ risk-path varsa efloud-risk-ops-reviewer)
└─ Canlı incident → live-ops-sentinel (#117)
```

---

## B. RUNTIME advisory team (`engine/agents/`)

### Mimari
```
AgentTeam (team.py:53)
  SignalValidatorAgent + RiskReviewerAgent + RegimeAgent → OverseerAgent → team_verdict
  PostMortemAgent (cycle-dışı, /api/ai/post-mortem)
  GeminiClient (tek shared HTTP client, fail-safe → {})
```

### DEĞİŞMEZ HARD-RULE'lar (audit kırmızı çizgileri)
1. **ADVISORY ONLY** — agent verdict trade mantığına dokunmaz; yalnız annotate eder (gating=false).
2. **gating default FALSE** — `cfg.get("gating", False)`. REJECT yalnız EKLER (veto), breaker/guard/orphan/reverse/entry-drift'i ASLA KALDIRMAZ.
3. **FAIL-SAFE** — `GEMINI_API_KEY` yoksa veya hata → NEUTRAL, `{}`, asla raise/block. Timeout zorunlu (şu an 20s).
4. **Deterministik katman bağımsız** — breaker/PositionGuard/orphan her cycle agent'tan bağımsız çalışır.

### MEVCUT DURUM (A1 — kritik)
- ⚠️ `gemini-3.5-flash` geçersiz model → **TÜM advisory + sentiment + Gemini-signal-validation PR #112'den (2026-06-01) beri sessizce NEUTRAL/ölü.**
- `agent_disagreements.jsonl` "model nötr düşündü" gibi görünen ÇÖPLE dolu → **shadow PnL korelasyonu için kullanılamaz.**
- Sözleşme ihlalleri (02_findings): C8 (signals.py Gemini blocking gate — advisory değil, key çalışınca trade bloklar), A5 (notional-blind risk review), A2 (hata DEBUG-only).

### gating:true açılması için ÖN-KOŞULLAR (F2 — sırayla)
1. **A1 fix** (P0-4) — gemini-2.0-flash; shadow saati buradan başlar (eski JSONL geçersiz).
2. **A2** — hata WARNING + JSONL `error` alanı (kırık-NEUTRAL ↔ gerçek-NEUTRAL ayrımı).
3. **C8 fix** — Gemini validation'ı blocking gate'ten advisory annotate'e taşı.
4. **A5/F1 fix** — 2-pass risk review (gerçek `size_notional_pct`).
5. **A4** — `htf_slope_pct` orchestrator→ctx.
6. **Shadow penceresi** — ≥50 geçerli-LLM trade (`grep -c '"error"' jsonl == 0`); `precision_REJECT > 0.6` (≥10 REJECT örneği).
7. **min_team_score policy** — örn. `gating yalnız overseer==REJECT AND score<0.34`.
8. **PR süreci** — gating flip PR'ı shadow-metrik snapshot + verdict histogram + reload-ile-rollback planı içerir.

---

## C. Öneriler özeti
1. **Hard-rule'lar korunur** — gating=false, advisory-only, fail-safe (red çizgi).
2. **A1 fix önce** (roadmap P0-4) — advisory katmanını gerçekten aktive eder; aksi halde tüm runtime agent ekibi dekoratif.
3. **Dev-agent roster temiz** — duplicate yok; sadece `efloud-risk-ops-reviewer` vs `risk-safety-auditor` rol netliği (.md güncelle: biri diff-review, biri derin-audit).
4. **#117 merge** 4 advisor agent'ı kanonik yapar → 13 agent. Phase 3'te persona ile simüle edildiler; merge sonrası gerçek subagent_type olarak çağrılabilirler.
5. **Karar ağaçları** (A: dev-time, B: gating ön-koşul) bu repoda kanonik referans — gelecek agent işlerinde buraya dön.

---

## D. Gelecek strateji/setup işleri için zihinsel harita (mission gereği)
Bu audit'in subagent kullanım haritası `00_journal.md`'de. Özet kalıcı ders:
- **Yeni SMC modülü** → smc-strategy-reviewer (opus) + önce backtest'i fee+funding ile güvenilir yap (S2), sonra ablation.
- **Gating arbitration** → A1+A2+C8+50-trade shadow ön-koşulu (yukarıda) tamamlanmadan AÇMA.
- **Korelasyon-aware sizing** → fund-manager-overseer lens + correlation matrix ölç (ÖLÇÜLMEMİŞ şu an).
- **Config/threshold değişimi** → her zaman docs/results/ backtest kanıtı + re-backtest (S1 dersi: gut-feel "daha çok sinyal" −43.75% getirdi).
