---
id: T-20261104-02
title: Hermes'in 5 incubator skill'ini koda karşı bağımsız review et
from: claude-code
to: abacus
status: claimed
claimed_by: abacus
reviewer: claude-code
created: 2026-11-04
touches_live: false
---

## Amaç
İkinci, bağımsız bir model görüşü. Claude'un review'u her `REVIEW.md`'de var; **önce kendi
review'unu yaz, sonra Claude'unkini oku** (anchoring olmasın), en sonda farkları not et.

## Girdi
- `collab/skills-incubator/*/SKILL.md` (5 adet)
- Kod: `engine/smc.py`, `engine/levels.py`, `engine/signals.py`, `engine/smc_v2/`, `exchange/__init__.py`
- Canlı config: `configs/config.phase2_1k.yaml` (`risk:` ve `safety:` blokları)
- Kanal verisi (laptop): `~/efloud-collab-private/telegram-efloud-2023-2025/messages.jsonl`

## Beklenen çıktı
- [ ] Her skill'in `REVIEW.md`'sine `## abacus — YYYY-MM-DD` bölümü: VERDICT (APPROVE/CHANGES/REJECT), dosya:satır kanıtlı bulgular, Claude review'u ile uyuşan/uyuşmayan noktalar.
- [ ] Kendi worktree'n + branch `collab/abacus/T-20261104-02-skill-review` → draft PR (= claim) → hazır olunca PR.
- [ ] `collab/log/abacus.md` girişi (`- VPS: N/A`).

## Kısıtlar
- SKILL.md içeriğini sen düzeltme (yazar = hermes); yalnız review yaz.
- Config/kod değiştirme.

## Log
- 2026-11-04 claude-code: task açıldı.

## Review
