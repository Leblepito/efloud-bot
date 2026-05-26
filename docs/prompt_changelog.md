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

### 2026-05-26 — Phase 4.2 Prompt Evolution
- **Dosyalar:** 
  - `.claude/agents/efloud-test-engineer.md`
  - `.claude/agents/efloud-code-reviewer.md`
  - `.claude/agents/efloud-risk-ops-reviewer.md`
  - `.claude/agents/efloud-explorer.md`
- **Motivasyon:** Ajan ekosistemini TDD, AST Graphify, strict mainnet safeguards ve gelişmiş hata ayıklama yetenekleri ile donatarak canlı kapital güvenliğini artırmak.
- **Referans:** `superpowers/skills/test-driven-development/`, `system_prompts_leaks/Google/gemini-3.5-flash.md`, `system_prompts_leaks/Anthropic/claude-opus-4.7.md`, `graphify/README.md`
- **Önceki davranış:** Prompt'lar basic seviyedeydi, TDD demir kanunları ve AST Graphify entegrasyonu bulunmuyordu.
- **Yeni davranış:**
  - `efloud-test-engineer.md` artık TDD "Iron Law" (No production code without failing test) ve Red-Green-Refactor döngüsünü zorunlu kılmaktadır.
  - `efloud-code-reviewer.md` artık atomik commit kurallarını ve AST Graphify ile caller/impact side-effect analizini zorunlu kılmaktadır.
  - `efloud-risk-ops-reviewer.md` artık server-side conditional SL/TP emirlerini, isolated vs cross margin limitlerini ve geriye uyumlu DB migrations kurallarını doğrulamaktadır.
  - `efloud-explorer.md` artık kod tespiti ve dosya aramalarında `graphify query` ve `graphify explain` CLI araçlarını öncelikli kılmaktadır.

