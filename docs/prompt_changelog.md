# Ajan Prompt Evolution Changelog
# ═════════════════════════════════
# Ajan prompt'larındaki her değişiklik buraya loglanır.
# Referans: docs/ROADMAP_AI_INTEGRATION.md §4.2
# Kaynak referansları: external_repos/system_prompts_leaks/

---

## Format

```
### YYYY-MM-DD — [Ajan Adı] — [Değişiklik Özeti]
- **Dosya:** `.claude/agents/xxx.md` veya benzeri
- **Motivasyon:** Neden değiştirildi
- **Referans:** Hangi system prompt'tan ilham alındı (varsa)
- **Önceki davranış:** ...
- **Yeni davranış:** ...
```

---

## Changelog

### 2026-05-26 — Sistem Kurulumu
- **Dosya:** `docs/ROADMAP_AI_INTEGRATION.md` (yeni)
- **Motivasyon:** Çoklu ajan ekosistemi için merkezi yol haritası ve işbirliği protokolü oluşturuldu
- **Referans:** `external_repos/superpowers` (ajan metodolojisi), `external_repos/system_prompts_leaks` (prompt stratejileri)
- **Not:** İlk kurulum, henüz mevcut ajan prompt'larında değişiklik yapılmadı

### 2026-05-26 — KingGemini Protokolü (SMR Loop) Aktivasyonu
- **Dosya:** `docs/KING_GEMINI_PROTOCOL.md` (yeni), `GEMINI.md` (güncelleme)
- **Motivasyon:** Model değiştirmeden tek bir Gemini 3.5 Flash oturumunda hem Opus (Mimar) derin mimari analizini hem de Flash (Mühendis) cerrahi kod yazımını ve Risk/QA analizini ardışık koşturabilmek için 3-katmanlı SMR (Synthesized Multi-Role) Loop protokolü aktif edildi.
- **Referans:** `system_prompts_leaks/Anthropic/claude-opus-4.6.md`, `superpowers/skills/subagent-driven-development/`, `graphify/README.md`, `caveman/skills/caveman-compress/`
- **Önceki davranış:** Gemini 3.5 Flash sadece Python yazımı ve script koşturma gibi mekanik mühendislik görevlerini (Flash) üstleniyor, mimari analiz için Opus modeline geçiliyordu.
- **Yeni davranış:** Gemini 3.5 Flash, isteği aldığında kendi içinde sanal Opus (Mimar), sanal Flash (Mühendis) ve sanal Risk (QA) katmanlarını ardışık koşturup otonom doğrulama yapar.

---

## Planlanan Prompt İyileştirmeleri

| Hedef Ajan | Planlanan Değişiklik | Kaynak Referans | Öncelik |
|---|---|---|---|
| efloud-code-reviewer | Superpowers TDD ve code-review skill'lerinden best-practice entegrasyonu | `superpowers/skills/requesting-code-review/` | ORTA |
| efloud-test-engineer | RED-GREEN-REFACTOR döngüsünün zorunlu kılınması | `superpowers/skills/test-driven-development/` | YÜKSEK |
| efloud-risk-ops-reviewer | Gemini 3.5 Flash ve Claude Opus 4.7 system prompt'larındaki güvenlik pattern'leri | `system_prompts_leaks/Google/gemini-3.5-flash.md`, `Anthropic/claude-opus-4.7.md` | ORTA |
| efloud-explorer | Graphify bilgi grafiği sorgulama yeteneği eklenmesi | `graphify/README.md` | DÜŞÜK |
