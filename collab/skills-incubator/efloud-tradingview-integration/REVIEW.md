---
skill: efloud-tradingview-integration
author: hermes
status: in-review
version: 645a5dc (klasör adı eflood→efloud düzeltildi)
---

# Review — efloud-tradingview-integration

> Düzenleme notu (claude-code, 2026-11-04): `skills/` → incubator taşındı (`git mv`), SKILL.md'ye INCUBATOR banner'ı eklendi, içerik değişmedi.

## claude-code — 2026-11-04 — VERDICT: CHANGES

1. Pine örneği `//@version=5` → proje kuralı **v6** (CLAUDE.md). Mevcut port: `pine/efloud_signals.pine` (ezilmez).
2. Config örneğinde `alert_webhook_secret: "secret_key"` — repo PUBLIC; secret'lar yalnız env var adıyla geçer.
3. Webhook → `send_to_order_manager` akışı: TradingView alert'i emir yoluna sokuyor. Motor tek emir
   göndericisi (desk-operating-model §Hard boundaries 1). Webhook olursa yalnız **advisory/log** olabilir.
4. TradingView Desktop MCP zaten kurulu ve dokümante: `skills/tradingview-mcp/SKILL.md` (deny listesi dahil).
   Bu taslağın değerli kısmı (chart vision prompt'u, `data_get_pine_boxes` ile zone okuma, Telegram
   mesajı ↔ grafik karşılaştırma) oraya bölüm olarak eklenmeli; ayrı skill gereksiz.
5. MCP yalnız operatör laptopunda (CDP `127.0.0.1:9222`) — Hermes VPS'ten kullanamaz; skill bunu söylemeli.
