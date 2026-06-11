# Claude UltraPlan Prompt — P-002 Marketing & Growth

> **Hedef:** Efloud-bot için marketing + growth pipeline'ının tam planını rekonstrükte et.
> **Format:** UltraPlan (ground-truth → gap → atomic PR'lar → strateji → security)
> **Sonraki adım:** Bu dosyayı Claude'a gönder, UltraPlan çıktısını `LLTODO/plans/2026-06-10-efloud-marketing-growth.md`'e yaz.

---

## Kimlik

Sen efloud-bot projesinin Claude agentsın. Çift rolün var:
1. **Reviewer:** Plan review (R-00X), ultra review (UR-001), mimari kararlar
2. **UltraPlan Reconstructor:** Hermes'in v1 draft planlarını al, repo ground-truth ile doğrula, eksikleri kapat, per-PR atomic plan üret

---

## Görev: Marketing & Growth UltraPlan

**Epic:** P-002 (önerilen)
**Branch:** `feat/marketing-growth-pipeline`
**Hermes v1 draft:** `LLTODO/plans/2026-06-10-efloud-marketing-growth.v1-hermes-draft.md`

### 6 Faz

**Faz 1 — Ground-Truth:**
Repo'yu baştan sona tara (master 39c2738). CLAUDE.md, HERMES.md, README, docs/, LLTODO/, engine/, frontend/, pine/, configs/ her şeyi oku. CLAUDE.md'deki iddiaları gerçek kodla karşılaştır. "Next.js 15" claim'i doğru mu? Hangi dosya statik hangisi dinamik? List all API/MCP/CLI.

**Faz 2 — Gap Analysis:**
Hermes v1 planındaki eksikleri bul. Hangi varsayımlar yanlış? Hangi bağımlılıklar atlanmış?

**Faz 3 — Per-PR Plan (15 PR):**
- Faz A: Altyapı (xurl, TV MCP, Manus auth, YouTube)
- Faz B: İçerik Pipeline (Manus task templates, Higgsfield video, TV chart export)
- Faz C: Web Site (bot.ualgotrade.com → bot.u2algo.com, dashboard, SEO)
- Faz D: Growth (X @efloud, YouTube Shorts, Telegram, Google Ads)
- Her PR: exact file paths, test komutları, acceptance, rollback

**Faz 4 — Marketing Stratejisi:**
Hedef kitle, keyword research, content calendar, conversion funnel, CAC, MRR projeksiyonu

**Faz 5 — Security Audit:**
API key surface, data leak vectors, rate limit riskleri, dashboard auth, dry-run/live karışıklığı

**Faz 6 — UltraReview Checklist:**
G1-G8 compliance gate'leri

### Teknik Kısıtlar

- VPS read-only deploy key → planlar format-patch ile transfer
- Tüm secret'lar VPS-only (.env), repo'da ASLA
- Manus API: REST, `x-manus-api-key` header
- Higgsfield: MCP üzerinden (zaten bağlı)
- TradingView: Desktop debug port 9222 (henüz bağlı değil)
- X: xurl CLI (henüz kurulu değil)
- Dil: Türkçe
- Bu CANLI MAINNET bot — her adım "trade'i bozar mı?" sorusuyla test edilmeli

---

## Çıktı Formatı

```
# Efloud-Bot Marketing + Growth — UltraPlan (Reconstructed)
## 0. Ground-Truth Findings (G1, G2, ...)
## 1. Gap Analysis
## 2. Per-PR Implementation Plan (PR #1..#15)
## 3. Marketing & SEO Strategy
## 4. Security Audit
## 5. UltraReview Compliance Checklist
## 6. Open Questions
```

Canonical path: `LLTODO/plans/2026-06-10-efloud-marketing-growth.md`
Hermes v1 backup: `.v1-hermes-draft` suffix ile aynı dizinde

> **Path notu (@claude, 2026-06-11):** Orijinal prompt `.hermes/plans/` path'ini kullanıyordu;
> kanonik yer `LLTODO/plans/` olarak güncellendi (Hermes 2026-06-11 talimatı, süreç-görünürlük).
