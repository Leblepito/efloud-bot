---
id: T-20261107-21
title: Video — seslendirme kesilmesin + ses seviyesi (backlog madde 9)
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
Grafik → MP4 hattında (`scripts/video_render.py`) seslendirmeli klipleri platforma hazır hale getirmek (skill: video-editing).

## Beklenen çıktı (Definition of Done)
- [x] Hata: seslendirme verildiğinde klip her zaman varsayılan 8 sn'de kesiliyordu (`-t 8` + `-shortest`) → anlatımın sonu kayboluyordu. Artık süre verilmezse seslendirme süresi kullanılıyor; açık `--duration` hâlâ öncelikli.
- [x] Seslendirme EBU R128 −16 LUFS / −1.5 dBTP'ye normalize (IG/YT/TikTok konuşma seviyesi), 128k AAC.
- [x] RED→GREEN: `tests/test_video_render_voiceover.py` (4).
- [ ] Dashboard demo videosu (ui-demo): canlı panel giriş + gerçek hesap verisi gösterir → hangi verinin gösterileceği operatör kararı; bu PR'da yok.
