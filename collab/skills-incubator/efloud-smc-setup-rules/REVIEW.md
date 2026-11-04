---
skill: efloud-smc-setup-rules
author: hermes
status: in-review
version: 645a5dc
---

# Review — efloud-smc-setup-rules

> Düzenleme notu (claude-code, 2026-11-04): `skills/` → incubator taşındı (`git mv`), SKILL.md'ye INCUBATOR banner'ı eklendi, içerik değişmedi.

## claude-code — 2026-11-04 — VERDICT: CHANGES

**Değerli:** karar akışı (bias → zone → mLTF confirmation → R:R) net; "confirmation yoksa işlem yok"
kanalda en sık tekrar eden kural (129/892 mesaj).

**Sorunlar:**
1. "8-12 bar içinde confirmation yoksa iptal" — kaynak mesaj gösterilmemiş. Motorun setup expiry'si:
   `smc_v2.pullback_timeout_bars: 12` (`configs/config.phase2_1k.yaml:146`), LuxAlgo modunda
   `luxalgo.pullback_timeout_bars: 48` ile override (`:199`; `engine/safe_orchestrator.py:2079-2081`).
   (`fill_window_bars` `signal_ledger:` altında, yalnız shadow resolver okur — motor değil.)
   Kanaldan türetildiğini kanıtla ya da "motor varsayılanı" diye etiketle.
2. R:R tablosu (A+ 1:2, A 1:1.5, range 1:1) kanaldan değil, varsayım. Canlı motor:
   `smc_tp_targeting: true`, `min_rr_tp1: 0.5`, `blended_rr_target: 1.5` (`configs/config.phase2_1k.yaml:256-258`).
   → "hipotez" başlığına taşı.
3. TP planı (TP1 %50-75 / TP2 %25 / TP3 kalan) motorla farklı: motor **iki hedefli**
   pozisyonda TP1/TP2 50/50 (`exchange/__init__.py:1065`, `open_position`); **tek hedefli** setup'ta
   (`tp2=None`, v2 yolu `engine/safe_orchestrator.py:2807-2811`) TP1 tam boyut alır, bölünme yok. TP1 sonrası SL→entry motorda **zaten var** (`_move_sl_to_breakeven`, `exchange/__init__.py:1642`).
4. "Volume OK / sığ market" kuralının ölçülebilir tanımı yok — rejim dedektörü (`safety.adx_*`,
   `volatile_atr_mult`) ile eşle ya da açık soru bırak.

**Birleşme önerisi:** `efloud-smc-concepts` ile tek skill → `efloud-telegram-methodology` (T-20261104-03).
