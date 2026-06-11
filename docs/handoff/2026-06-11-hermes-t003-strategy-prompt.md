# 🟧 Hermes — T-003 Görev Prompt'u (2026-06-11)

> Hazırlayan: Claude (Architect/Review). Bitince Claude review + compile/backtest
> gate'lerini koşacak. Kurallar: feature-branch + PR, atomic, append-only/claim
> (`git add -A` YASAK), secrets sadece VPS, destructive-op yok.
> Transfer: **git push** (format-patch + sha256 yalnız push mümkün değilse).

Bağlam: **P-001 FAZ 3'ün son görevi.** T-001 ✅ (G-T1 PASS) ve T-002 ✅
(G-T2 PASS, PR #190) tamamlandı. `pine/u2algo/wave1_signals.pine` v1.1.1
TradingView'de compile-verified (0 hata 0 marker). Sıra STRATEGY versiyonunda.

---

## GÖREV (TOP SENDE) — T-003: Strateji Backtest + Görsel Validasyon

**Yapılacak:**
1. `LLTODO/tasks/BACKLOG/T-003-strategy-backtest.md` → `IN_PROGRESS/`'e taşı,
   claim et (`Claimed by: @hermes`), STATE.md'ye heartbeat ekle (append-only).
2. `pine/u2algo/wave1_strategy.pine` yaz — `wave1_signals.pine` v1.1.1'in
   STRATEGY karşılığı (`strategy()` + `strategy.entry`/`strategy.exit`).
   Sinyal mantığı AYNEN: confluence 7-faktör ≥ threshold + 1h bias + OB entry,
   `f_calc_sl`/`f_calc_tp` SL/TP'leri. Input isimleri SENKRON (CLAUDE.md kuralı).
3. Kart'taki çıktılar: OOS period (son %30), repaint audit, equity görselleri,
   `pine/u2algo/WAVE1_SPEC.md` final, alert template.

## ⚠️ KRİTİK KURALLAR

1. **PATH:** Wave-1 dosyaları SADECE `pine/u2algo/`. `pine/efloud_signals.pine`,
   `pine/efloud_strategy.pine`, `pine/PINE_SPEC.md` = SMC v2 sadık portu
   (PR #148 publish temeli) — **DOKUNMA** (T-001'deki CRIT'in tekrarı olmasın).
2. **Pine v6 syntax — G-T2'de senin patch'inde yakalanan 2 derleyici dersi**
   (VPS'te TV yok, derleyemiyorsun; bu yüzden defansif yaz):
   - Satır devamı için `\` YOK — "no viable alternative at character '\'".
     Uzun ifadeyi girintili satır sarmayla böl veya tek satırda tut.
   - `x = na` YASAK — "Value with NA type cannot be assigned to a variable
     that was defined without type keyword". Her zaman `float x = na` /
     `int x = na` yaz.
3. **Repaint:** yalnız `barstate.isconfirmed` / `[1]`; `request.security`'de
   `lookahead=barmerge.lookahead_off`; 1h pivot için v1.1.1'deki
   **gecikmeli-pivot** kalıbını kopyala (B1 fix — `[-j]` gelecek-bar erişimi yasak).
4. **Strategy ayarları:** komisyon + slippage gerçekçi (örn. `commission_value=0.05`
   %, `slippage` ticks>0), `calc_on_every_tick=false`, `process_orders_on_close=true`
   (sinyal confirmed-bar'da üretildiği için). Default'lar backtest gate'lerini
   şişirmesin.

## Gate'ler (Claude koşacak — TV MCP lokalde)

- **G-T3 compile:** `pine_smart_compile` + `pine_get_errors` → 0 hata 0 marker.
- **G-T4/G-T5/G-T6 backtest:** min 100 trade; WR ≥ %50, PF ≥ 1.5, MaxDD ≤ %5;
  OOS Sharpe ≥ IS Sharpe × 0.7. Sonuçları Claude TV Strategy Tester'dan çekecek;
  sen kartta gate eşiklerini ve OOS tanımını WAVE1_SPEC'e yaz.

**Acceptance:** kart'taki tüm checkbox'lar + LLTODO lint 8/8 + PR açık.
→ FAZ 4 UR-001 UltraReview (@claude).

**Ref:** `LLTODO/tasks/BACKLOG/T-003-strategy-backtest.md` (path'leri bu PR'da
düzeltildi), `LLTODO/plans/P-001-u2algo-wave1-tradingview.md` (v1.3),
`pine/u2algo/wave1_signals.pine` (v1.1.1), `pine/u2algo/WAVE1_SPEC.md`.
