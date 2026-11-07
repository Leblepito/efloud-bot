---
id: T-20261107-25
title: LLM yapı doğrulaması varsayılan KAPALI (karar 2, LLM denetimi L1)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261107-22
created: 2026-11-07
touches_live: true
---

## Amaç
Operatör kararı (vekâleten, spec 2026-11-07 §1 #2): sinyal başına senkron, asla engellemeyen ve
canlıda 19 günde 23.085/23.085 kez fallback'e düşen LLM yapı doğrulaması bayrak arkasında, varsayılan KAPALI.

## Beklenen çıktı (Definition of Done)
- [x] `generate_signals(structure_validation=False)` varsayılan; orkestratör `engine.structure_validation.enabled`'ı geçirir; canlı config `enabled: false`.
- [x] Canlı davranış: aynı (çağrı zaten her seferinde pass-through'du). Fark: sinyal meta'sında `gemini_structure_validation` anahtarı artık yok; log satırları kalkar.
- [x] RED→GREEN `tests/test_structure_validation_flag.py`; eski C8 testi etkin yolu test ediyor; regresyon defteri 2763 passed.
- [ ] Deploy: bot container yeniden başlatma gerektirir (AUTOSTART=0 → manuel start) — operatörle zamanlanır.
