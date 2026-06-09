---
plan_id: P-XXX
author: hermes | claude | gemini
status: AWAITING_REVIEW | CONSENSUS_REACHED | STRONG_CONSENSUS | REVISING | REJECTED | IMPLEMENTING | DONE
created: YYYY-MM-DDTHH:MM:SS+03:00
reviewers: [claude, gemini]
approvals_needed: 2
approvals_received: 0
---

# Plan: [Slug / Başlık]

## Amaç
[Planın temel amacı ve çözdüğü problem]

## Kapsam

### Yapılacaklar (In Scope)
- [ ] İş 1
- [ ] İş 2

### Yapılmayacaklar (Out of Scope)
- ...

## Task'lar & Dağıtım (Task Matrix — ZORUNLU: her satır SCOREBOARD'a atıfla gerekçeli)

| ID | Görev | Agent | Faz | Süre | Dependencies | Gerekçe (SCOREBOARD'a atıf) |
|----|-------|-------|-----|------|--------------|------------------------------|
| T-001 | ... | hermes | IMPLEMENT | 30dk | [] | hermes: implementation specialty (X DONE) |
| T-002 | ... | claude | CONSENSUS | 15dk | [T-001] | claude: review specialty (avg conf Y) |

> Dağıtım bu plan içinde CONSENSUS'ta onaylanır (teyit-2). Reviewer'lar "Dağıtım Adil mi?" satırında onaylar/itiraz eder.

## Skill Pipeline
1. `skill_view(name='...')` → ...
2. ...

## Riskler
- ...
