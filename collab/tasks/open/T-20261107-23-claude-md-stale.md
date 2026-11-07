---
id: T-20261107-23
title: CLAUDE.md bayat bilgiler + kanonik kaynak bağlantıları (backlog madde 14, kısım 1)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261106-04
created: 2026-11-07
touches_live: false
---

## Amaç
CLAUDE.md'deki canlıyla çelişen bilgileri düzeltmek ve yeni kanonik dokümanlara bağlamak (skill: living-docs-governance).

## Beklenen çıktı (Definition of Done)
- [x] `bot.u2algo.com` panel referansı (DNS silindi) düzeltildi.
- [x] u2algo-site: "Next.js 15" değil statik HTML + `server.js`; canlı URL `u2algo.com` (eski railway.app adresi 404).
- [x] Supabase waitlist "PGRST205, tablo hazır değil" → canlıda `ready` (2026-11-07 doğrulandı).
- [x] "Kanonik kaynaklar" bölümü: CONTEXT.md, docs/adr, TESTS.md, REGRESSION.md, canary, STATUS.md + backtest aracının master'da olmadığı uyarısı.
- [ ] Kısım 2 (operatör kararı): CLAUDE.md'yi anayasa (kalıcı kurallar) ↔ durum (tarihli "Son Durum" blokları → `collab/STATUS.md`) olarak ayırmak.
