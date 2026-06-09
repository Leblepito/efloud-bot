---
task_id: T-XXX
assigned_by: hermes | claude | gemini
assigned_to: hermes | claude | gemini | manus | codex
priority: P1 | P2 | P3
status: PENDING | IN_PROGRESS | DONE
skill: [kullanılacak skill veya tool]
phase: PLAN | CONSENSUS | IMPLEMENT | ULTRAREVIEW | CROSSTEST
deadline: YYYY-MM-DDTHH:MM:SS+03:00
dependencies: []
plan_id: P-XXX
created: YYYY-MM-DDTHH:MM:SS+03:00
# --- claim alanları: görev IN_PROGRESS'e taşınınca damgalanır ---
claimed_by: null
claimed_at: null
---

# Görev: [Slug / Görev Başlığı]

## Ne Yapılacak
[Net, spesifik, tek cümlelik veya maddeli talimatlar. Başka iş yapılmayacaktır.]

## Skill / Tool Adımları
1. ...
2. ...

## Çıktılar
[Hangi dosyalar oluşturulacak veya düzenlenecek]

## Kapanış Kontratı (Done Criteria)
1. Bu görevi `LLTODO/tasks/DONE/` altına taşı.
2. `LLTODO/reports/<agent>/YYYY-MM-DD-<özet>.md` raporunu yaz.
3. Varsa sonraki adımları `LLTODO/STATE.md`'ye kaydet.
