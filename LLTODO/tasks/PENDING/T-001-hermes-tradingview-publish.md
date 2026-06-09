---
task_id: T-001
assigned_by: hermes
assigned_to: hermes
priority: P1
status: PENDING
skill: gstack-office-hours → gstack-spec → writing-plans
deadline: "after:T-002"
dependencies: [T-002]
created: 2026-06-09T11:00:00+03:00
---

# Görev: TradingView SMC v2 İndikatörü Publish

## Ne Yapılacak
efloud-bot'un `pine/publish/efloud_signals_v2_en.pine` dosyasını TradingView'de
Protected/Public olarak yayınla. Bu, u2algo'nun ilk ürünü olacak.

## Skill Pipeline
1. `skill_view(name='gstack-office-hours')` — Builder mode: "TradingView indikatörü"
2. `skill_view(name='gstack-spec')` — 5-faz executable spec → GitHub issue
3. `skill_view(name='writing-plans')` — Task task publish planı
4. `skill_view(name='subagent-driven-development')` — Planı uygula

## Çıktı
- GitHub issue: "Publish TradingView SMC v2 Indicator"
- TradingView'de yayınlanmış indikatör
- `pine/publish/PUBLISH_efloud_signals.md` güncellenmiş
- u2algo.com landing page'de CTA

## Bittiğinde
1. Bu dosyayı `LLTODO/tasks/DONE/` altına taşı
2. `LLTODO/reports/hermes/2026-06-09-tradingview-publish.md` raporunu yaz
3. Claude için T-004 (backtest API planı) oluştur
