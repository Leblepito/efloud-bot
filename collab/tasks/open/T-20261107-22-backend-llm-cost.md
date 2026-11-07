---
id: T-20261107-22
title: Backend + DB ve LLM maliyet/gecikme ölçümü (backlog madde 11 + 13)
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
Backend/DB sağlığını ve LLM çağrılarının canlıdaki gerçek maliyet/gecikmesini ölçmek
(skill: fastapi-patterns, database-migrations, cost-aware-llm-pipeline, latency-critical-systems). Yalnız rapor.

## Beklenen çıktı (Definition of Done)
- [x] Rapor: `collab/outputs/claude-code/2026-11-07-backend-db-llm-cost.md`.
- [x] Canlı ölçüm (salt okuma): yapı doğrulama 23.085/23.085 fallback; sentiment çalışıyor (motor kullanmıyor); alerter formatlayıcı hep ham.
- [ ] L1 kararı: yapı doğrulamayı kaldır/bayrakla kapat (önerilen) ya da asenkron trade-sonrasına taşı — operatör + risk-ops.
