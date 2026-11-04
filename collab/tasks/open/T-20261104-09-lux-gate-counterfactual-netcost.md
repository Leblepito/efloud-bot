---
id: T-20261104-09
title: "İstek: LuxAlgo kapı reddleri için NET-cost karşı-olgu ölçümü (hangi kapı edge'e mal oluyor?)"
from: claude-code
to: any
status: open
claimed_by: null
reviewer: null
parent: null
created: 2026-11-04
touches_live: false
---

## Amaç
Teşhis, chart'ta görünen LuxAlgo OB dokunuşlarının çoğunun motor tarafından bilinçli kapılarla
elendiğini gösterdi (HTF bias yönü, recency, premium/discount, min_confluence, engulfing-zone-içi
kapanış). Bu kapılardan birini gevşetmek ancak NET-cost kanıtla düşünülebilir. Bu task yalnız
**ölçer**; config/motor değişikliği önermez, önerirse default-OFF bayrak + risk-ops + operatör onayı.

## Girdi
- `collab/outputs/claude-code/2026-11-04-ob-entry-gap.md` §2–§3 (sebep dağılımı, replay yöntemi).
- Replay harness'ı (laptop, git dışı): `c:/tmp/obgap_scripts/{fetch.py,replay.py}` — gerekiyorsa
  `scripts/desk/` altına testli bir araç olarak taşınır (ayrı PR).
- `scripts/desk/plan_replay.py`, `scripts/desk/agent_verdict_edge.py`, signal ledger.

## Beklenen çıktı (Definition of Done)
- [ ] Her red kategorisi için "kapı olmasaydı" işlemin ileri sonucu (SL/TP1/TP2 ya da timeout),
      komisyon + slippage + funding dahil NET R; sembol ve yön kırılımı; ≥ 60 gün, IS/OOS ayrımı.
- [ ] Kategori başına örnek sayısı < 30 ise "karar için yetersiz" yazılır.
- [ ] Çıktı `collab/outputs/<model>/YYYY-MM-DD-lux-gate-counterfactual.md`; ham veri git dışı.

## Kısıtlar
- Salt-okuma; canlı config/motor değişmez. VPS'e yazma yok.

## Log
- 2026-11-04 claude-code: task açıldı (OB-entry-gap teşhisinin takibi).

## Review
