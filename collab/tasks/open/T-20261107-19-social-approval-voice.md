---
id: T-20261107-19
title: Sosyal içerik — onay içeriğe bağlı + marka sesi (backlog madde 8)
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
Sosyal içerik hattında (Lane A→G) onay döngüsünü sağlamlaştırmak ve tek bir marka sesi kaynağı
oluşturmak (skill: operator-approval-loop, brand-voice, content-engine, crosspost).

## Beklenen çıktı (Definition of Done)
- [x] Onay içeriğe bağlı: `approve_bundle` / `--auto-approve` `approved_digest` yazar (caption + thread + alt + medya baytları sha256); `lane_g_publish` onaydan sonra değişmiş veya digest'siz bundle'ı `approval_stale` ile reddeder.
- [x] X coin hashtag'i postun sembolünden (`#SOL`); önce her posta sabit `#BTC` ekleniyordu.
- [x] `docs/social/BRAND_VOICE.md` — gönderilmiş kopyadan türetilmiş ses, platform uyarlaması, kod tarafından uygulanan kurallar.
- [x] RED→GREEN testler; TESTS.md TEST-SOCIAL-001/002.

## Not
- Önceden `approved` olup digest'i olmayan bundle'lar yeniden onay ister (fail-closed). Canlı yayın bayrakları zaten kapalı.
