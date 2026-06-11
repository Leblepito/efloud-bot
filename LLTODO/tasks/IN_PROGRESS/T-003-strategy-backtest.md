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
