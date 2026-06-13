# T-003: Strateji Backtest + Görsel Validasyon

**Epic:** P-001
**Claimed by:** @hermes (2026-06-11 — read-only key; claim kaydı Hermes adına @claude tarafından patch akışıyla işlendi)
**Tahmini süre:** 2-3 gün
**Bağımlılık:** T-002

## Hedef

`pine/u2algo/wave1_strategy.pine` yaz: backtest edilebilir STRATEGY versiyonu. Min 100 trade OOS, repaint kontrolü, görsel validasyon.

> ⚠️ PATH KURALI (plan v1.3 §3a — T-001'de yaşanan çakışmanın tekrarını önle):
> Wave-1 dosyaları SADECE `pine/u2algo/` altına. `pine/efloud_signals.pine`,
> `pine/efloud_strategy.pine` ve `pine/PINE_SPEC.md` mevcut SMC v2 sadık portuna
> aittir (PR #148 publish temeli) — DOKUNMA. Spec güncellemeleri
> `pine/u2algo/WAVE1_SPEC.md`'ye yazılır. Input isimleri `wave1_signals.pine`
> (v1.1.1, G-T2 compile-verified) ile SENKRON tutulur.

## Çıktılar

- [ ] `pine/u2algo/wave1_strategy.pine` — STRATEGY versiyonu (v6 syntax)
- [ ] `strategy.entry` + `strategy.exit` mantığı
- [ ] Backtest: min 100 trade, OOS period (son %30 veri)
- [ ] Gate kontrolleri: WR ≥ %50, PF ≥ 1.5, MaxDD ≤ %5
- [ ] Repaint audit: tüm referanslar `barstate.isconfirmed` / `[1]`
- [ ] Görsel validasyon: equity curve, trade marker'ları
- [ ] `pine/u2algo/WAVE1_SPEC.md` final
- [ ] Alert template: Telegram/Discord mesaj formatı

## Acceptance Kriterleri

- [ ] Pine Compile: sıfır hata, sıfır warning
- [ ] Backtest gate'leri (G-T4, G-T5, G-T6): PASS
- [ ] Repaint: sıfır look-ahead bias
- [ ] OOS Sharpe ≥ IS Sharpe × 0.7
- [ ] İş gate'leri (G-B1—G-B5): belgelenmiş

## Log

| Zaman | Durum | Not |
|---|---|---|
| — | BACKLOG | T-002 tamamlanınca başlayacak |
| 2026-06-11 | BACKLOG | T-002 DONE (G-T2 PASS) → T-003 claim'e açık. Path'ler plan v1.3'e güncellendi (`pine/u2algo/wave1_strategy.pine`); SMC v2 port dosyalarına dokunma uyarısı eklendi. @claude |
| 2026-06-11 | IN_PROGRESS | @hermes claim + iskelet geldi (format-patch+sha256 ✅, 2 commit beyan=2 geldi): wave1_strategy.pine 542 satır + WAVE1_SPEC §7. Claude `git am` → `feat/p001-t003-strategy` + ön-compile: 3 derleyici-zorlamalı fix (tuple destructuring `[a,b]=f()`, line.new named-arg, strategy'de `alert()`) → **0 hata 0 marker**. Review bulguları draft PR'da — Hermes sonraki patch'te ele alacak. |
| 2026-06-11 | REVIEW_FIXES | Round-2: Hermes fix patch'i (`60e6421`, sha256 ✅, 1/1 commit) — N3 parite + qty_percent + in_window + slippage/sizing uygulandı; expiry ölü koddu → Claude fix (`39df356`, pending takibi sig_entry_bar_*). Compile 0 hata 0 marker. **smc-strategy-reviewer: REQUEST_CHANGES** — parite APPROVE ama execution'da F1 (qty_percent=50×2 ≈ %75 yönetim), F2 (non-OCA çift stop), F3 (notional sizing ≠ risk-bazlı), F5 (karşı-yön pending iptal yok), F6 (pending'ken sinyal ezme). Detay PR #194 yorumu. Ball @hermes (round-3). |
| 2026-06-11 | CODE_READY ✅ | Round-3: Hermes patch'i (`b1bd38b`, sha256 ✅ 1/1) — F1+F2 (TP2 qty'siz kalan-tamamı + kendi stop'u), F3 (risk_pct=0.5% risk-bazlı qty), F5 (fill'de her iki yöne cancel), F6 (çift sayaç gate), F4 (spec intrabar caveat). Compile 0 hata 0 marker (596 satır). **smc-strategy-reviewer: APPROVE_WITH_NITS — "gate'ler artık koşulabilir ve güvenilir"** (G-T6 OOS-Sharpe spec'teki güven bandıyla okunacak). Nit'ler kapandı (N1 fallback yorumu, N2 spec). Kalan: G-T3 resmi + G-T4..G-T6 backtest koşuları (@claude TV) + rapor + alert template → DONE. |
| 2026-06-11 | GATE_RUN_1 | **G-T3 PASS (0 hata 0 marker, f8ce5c2) · G-T4 FAIL (trade_count=0, BTC+ETH perp 15m, ~4.3 ay) · G-T5/G-T6 değerlendirilemedi.** Kök neden: OB-aktif ZORUNLU ön koşulu + 5-ardışık-mum kuralı sinyal evrenini çökertiyor (~1-2 sinyal/4ay/sembol); tek sinyal de limit-retrace dolmadan expire. Detay + revizyon seçenekleri (R1: OB'yi faktöre indir — önerilen; R2: parametre gevşet; R3: market entry): `LLTODO/reports/REPORT-T-003-gate-run-1.md`. Plan §6 kaçış maddesi devrede — **revizyon konsensüsü gerekli (@hermes + @claude, plan v1.4)**. Gate işini yaptı: R-002'nin istediği validasyon tam bu senaryoyu yakaladı. @claude |
| 2026-06-13 | GATE_RUN_2 | **G-T3 PASS (committed 533e225) · G-T4a PASS (trade_count=168 closed-leg agg, 5 perp 15m, allow_ob_less=true+2026 pencere) · G-T4b OOS-Sharpe DEĞERLENDİRİLEMEZ (bt_oos_pct ÖLÜ input) · G-T5 PASS (inverted=0) · G-T6 PASS (subRR=0) · WR FAIL (~%10-15) · PF MARJİNAL FAIL (agg 1.44; XRP 0.38 kaybeden) · Fill ZAYIF (~%41, 9-60 değişken).** R1+R3 sayıyı 0→168 çıkardı ama kalite gate'leri geçmiyor. Per-sembol: BTC 28/PF1.57, ETH 6/PF3.97, SOL 24/PF1.29, BNB 54/PF2.59, XRP 56/PF0.38. Metrik: diagnostik instrumented build (committed mantık değişmeden, data_get_pine_tables; TV internal-api kırık). Yan-bulgu LATENT BUG: bt_date_end default=2025 → yayında 0 trade. Rapor: `LLTODO/reports/REPORT-T-003-gate-run-2.md`. **NET FAIL → round-5 (gerçek market-entry R3, F-01 BLOCKING) + bt_date_end & OOS-split fix. #194 MERGE EDİLMEZ.** Ball @hermes. @claude |
| 2026-06-13 | ROUND-5 + GATE_RUN_3 | **Round-5 market entry IMPLEMENTE (Claude, Hermes patch erişilemedi) → ❌ FAIL DECISIVE.** smc-strategy-reviewer APPROVE_WITH_NITS (B-01 spec + H-01 unused-var fix). Değişiklik: limit→market (`process_orders_on_close=true`, entry=close), limit_expiry/F5-F6/f_entry_price/sig_entry_bar/unused-OB silindi, bt_date default fix, bt_segment OOS-split, indicator SENKRON. G-T3 PASS (0 marker EXACT committed). GATE_RUN_3 (5 perp 15m Full): count=270/inverted=0/subRR=0 PASS, **AMA agg PF 0.71<1, net −%14.3, 4/5 kaybeden, MaxDD>%5, Sharpe neg.** 🔑 Edge OB-retrace LİMİT girişine bağlı; market-at-close kötü fiyat. Round-4 PF 1.44 vs round-5 0.71. **Hem limit hem market FAIL = derin tasarım sorunu, entry-mekanizması değil. Wave-1 STRATEGY shippable değil → OPERATÖR/KONSENSÜS (FAZ 4 UR-001): hibrit-limit/düşük-frekans/indicator-only/redesign.** Korunan: bt_date fix + OOS-split. Rapor: `LLTODO/reports/REPORT-T-003-gate-run-3.md`. @claude |
