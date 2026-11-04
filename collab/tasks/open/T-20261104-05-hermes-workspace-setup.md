---
id: T-20261104-05
title: Hermes çalışma alanı — ayrı klon, reddedilen skill'leri devreden çıkar, MCP config doğrula
from: claude-code
to: hermes
status: open
claimed_by: null
reviewer: claude-code
created: 2026-11-04
touches_live: false
---

## Amaç
Hermes'in prod deploy dizini dışında çalışması ve reddedilmiş taslakların Hermes runtime'ında
aktif kalmaması.

## Girdi
- `collab/README.md`, `collab/MODELS.md`, `collab/skills-incubator/*/REVIEW.md`, `collab/mcp/README.md`

## Beklenen çıktı
- [ ] Ayrı klon: `git clone https://github.com/Leblepito/efloud-bot.git ~/work/efloud-bot` (`/opt/efloud-bot`'a dokunma).
- [ ] `~/.hermes/skills/trading/efloud-*` kopyalarını **aktif skill yolundan çıkar** (ör. `~/.hermes/skills-incubator/` altına taşı). Özellikle `efloud-master-orchestrator` (REJECT) ve `efloud-risk-management` (canlıyla çelişen sayılar) yüklenmemeli. Kaynak-of-truth repo'daki `collab/skills-incubator/`.
- [ ] `collab/mcp/README.md` Hermes config parçasını kendi şemana göre doğrula; yanlışsa PR ile düzelt.
- [ ] `collab/log/hermes.md` ilk giriş + `STATUS.md` hermes satırı — branch `collab/hermes/T-20261104-05-setup`, PR.

## Kısıtlar
- Canlı sisteme yazma yok; prod dizininde edit/commit yok.

## Log
- 2026-11-04 claude-code: task açıldı.

## Review
