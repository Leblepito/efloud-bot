# T-003: Strateji Backtest + Görsel Validasyon

**Epic:** P-001
**Claimed by:** — (henüz claim edilmedi)
**Tahmini süre:** 2-3 gün
**Bağımlılık:** T-002

## Hedef

`pine/efloud_strategy.pine` yaz: backtest edilebilir STRATEGY versiyonu. Min 100 trade OOS, repaint kontrolü, görsel validasyon.

## Çıktılar

- [ ] `pine/efloud_strategy.pine` — STRATEGY versiyonu (v6 syntax)
- [ ] `strategy.entry` + `strategy.exit` mantığı
- [ ] Backtest: min 100 trade, OOS period (son %30 veri)
- [ ] Gate kontrolleri: WR ≥ %50, PF ≥ 1.5, MaxDD ≤ %5
- [ ] Repaint audit: tüm referanslar `barstate.isconfirmed` / `[1]`
- [ ] Görsel validasyon: equity curve, trade marker'ları
- [ ] `pine/PINE_SPEC.md` final
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
