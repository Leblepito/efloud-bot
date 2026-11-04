# skills-incubator — bir model yükler, diğerleri geliştirir

`skills/` = **aktif** skill'ler (Claude Code plugin'i her oturumda yükler, agent'lar
`skills:` frontmatter'ıyla preload eder). Oraya giren hatalı bir skill doğrudan
davranışa dönüşür. Bu yüzden yeni skill'ler önce burada olgunlaşır.

## Yaşam döngüsü

```
draft ──(yazar PR açar)──> in-review ──(≥1 başka model APPROVE)──> accepted ──(PR: git mv SKILL.md → skills/<ad>/)──> promoted
                               └──(REJECT / yerini başka skill aldı)──> rejected (klasör kalır, gerekçeli)
```

| Durum | Kim değiştirir | Koşul |
| --- | --- | --- |
| `draft` | yazar | `SKILL.md` + `REVIEW.md` (frontmatter'lı) eklendi |
| `in-review` | yazar | PR açıldı, reviewer atandı |
| `accepted` | reviewer | en az **bir başka model** APPROVE; risk/config/emir yoluna değinen skill'de claude-code + risk-manager bakışı şart |
| `promoted` | merge eden PR | `SKILL.md` (+ `references/`) `git mv` ile `skills/<ad>/`'e taşındı; **`REVIEW.md` incubator'da `status: promoted` stub'ı olarak kalır** (karantina testi promosyonu buradan okur, review geçmişi korunur); `tests/collab` + `tests/hooks/test_desk_plugin.py` yeşil |
| `rejected` | reviewer + operatör | gerekçe REVIEW.md'de |

## Klasör

```
skills-incubator/<skill-adı>/
  SKILL.md     # yazarın taslağı (name/description frontmatter'ı skills/ ile aynı biçim)
  REVIEW.md    # frontmatter: skill, author, status, version + her reviewer'ın bölümü
  (opsiyonel) references/*.md
```

`REVIEW.md` frontmatter'ı:

```yaml
---
skill: <klasör adı>
author: <claude-code|hermes|abacus>
status: <draft|in-review|accepted|rejected|promoted>
version: <SKILL.md'nin incelenen sürümü / commit>
---
```

Her reviewer kendi başlığını ekler: `## <model> — YYYY-MM-DD — VERDICT: APPROVE|CHANGES|REJECT`.
Başkasının bölümünü düzenleme; cevap verirken kendi bölümüne yaz.

## Geliştirme kuralları

- Başka modelin skill'ini **geliştirmek** serbest: branch + PR, REVIEW.md'ye "v2 değişiklikleri" notu.
- Skill içindeki her motor referansı **dosya:satır** ile doğrulanmış olmalı (var olmayan sınıf adı yok).
- Sayı (risk %, ATR çarpanı, limit) yazacaksan kaynağı `configs/config.phase2_1k.yaml` satırı olsun; "önerilen" değerler ayrı başlıkta ve **hipotez** etiketiyle.
- Pine kodu Pine **v6** (CLAUDE.md).
- Hermes kendi `~/.hermes/skills/` kopyasını buradan senkronlar; kaynak-of-truth repo'dur.

## Mevcut taslaklar (2026-11-04)

| Skill | Yazar | Durum | Özet karar (claude-code) |
| --- | --- | --- | --- |
| efloud-smc-concepts | hermes | in-review | CHANGES — 35/892 mesaj; motor referansları kısmen yanlış (LuxAlgo modu canlı) |
| efloud-smc-setup-rules | hermes | in-review | CHANGES — confirmation farkı değerli; birleştir |
| efloud-risk-management | hermes | in-review | CHANGES (kritik) — config tablosu canlıyla çelişiyor |
| efloud-tradingview-integration | hermes | in-review | CHANGES — Pine v5, hardcoded secret; `skills/tradingview-mcp`'ye birleştir |
| efloud-master-orchestrator | hermes | in-review | REJECT (runtime olarak) — ikinci emir yolu |
