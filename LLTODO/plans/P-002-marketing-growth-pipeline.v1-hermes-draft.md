# Efloud Marketing & Growth Pipeline — Hermes v1 Draft

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
> **Sonraki:** Bu v1 draft'ı Claude'a gönder → UltraPlan rekonstrüksiyonu → per-PR atomic plan → implement.
>
> **Transfer notu (@claude, 2026-06-11):** Bu dosya VPS'ten Telegram üzerinden aktarıldı;
> aktarım sırasında orta bölüm (Safety Invariants gövdesi + WS-A/WS-B workstream detayları
> + WS-C başlangıcı) KESİLDİ. Kesik bölümler `[TELEGRAM AKTARIMINDA KESİLDİ]` ile işaretli.
> Orijinalin tamamı VPS'te `LLTODO/plans/2026-06-10-efloud-marketing-growth.md` içinde durur.
> Kanonik rekonstrüksiyon: `P-002-marketing-growth-pipeline.md` (aynı dizin).
> **Lint notu:** Hedef/Kapsam/Görevler/Gate bölümleri kanonik plandadır; bu dosya tarihsel backup'tır.

**Goal:** Efloud-bot için marketing/growth pipeline'ını kurmak: organic content → waitlist → proof archive → (sonra) paid ads. Ana kanallar: X/Twitter, YouTube Shorts, Higgsfield video, Manus.im otomasyon, web dashboard SEO.

**Architecture:** 4 katman: Altyapı araçları → İçerik pipeline → Web sitesi → Growth kanalları. Her katman kendi PR setiyle implemente edilir. Tüm içerik Hermes onayından geçer, finansal tavsiye/getiri vaadi içermez.

**Tech Stack:** Python/FastAPI (mevcut), Next.js dashboard (mevcut), Manus.im REST API, Higgsfield MCP (video/image), xurl CLI (X/Twitter), YouTube API, TradingView MCP (chart export).

---

## Safety Invariants

`[TELEGRAM AKTARIMINDA KESİLDİ — gövde eksik]`

---

## Workstream'ler

### WS-A — Altyapı (PR #1..)

`[TELEGRAM AKTARIMINDA KESİLDİ — prompt dosyasındaki Faz A kapsamı geçerli: xurl, TV MCP, Manus auth, YouTube]`

### WS-B — İçerik Pipeline (PR #..)

`[TELEGRAM AKTARIMINDA KESİLDİ — prompt dosyasındaki Faz B kapsamı geçerli: Manus task templates, Higgsfield video, TV chart export]`

### WS-C — Web Sitesi (PR #..12)

`[başlangıç kesik]` ...: waitlist + risk disclosure + dashboard preview
- SEO: meta tags, sitemap, blog bölümü
- Dashboard: public read-only snapshot sayfası

### WS-D — Growth Kanalları (PR #13..#15)

- X/Twitter: @efloud hesabı, build-in-public thread'leri
- YouTube: Shorts serisi (Higgsfield video + voiceover)
- Telegram: efloud topluluğu / duyuru kanalı
- Google Ads: 90 gün proof sonrası, sadece eğitim/waitlist için

---

## İçerik Stratejisi (v1 Taslak)

### Brand Positioning

"SMC tabanlı, risk-disiplinli, şeffaf algoritmik trading araştırması."

### İçerik Sütunları

1. Build-in-Public: Trade journal, backtest notları, mimari kararlar
2. Risk Yönetimi: Drawdown limitleri, circuit breaker, pozisyon yönetimi
3. Algoritma: SMC doktrini, FVG/OB/swing açıklamaları
4. Dashboard: Haftalık performans snapshot'ları

### Brand Guardrails

- ❌ "Garanti kâr", "kesin kazanç", "sinyal satışı"
- ❌ Yatırım tavsiyesi, fon toplama
- ✅ "Araştırma", "risk yönetimi", "şeffaf performans"
- ✅ Her içerikte risk disclaimer

---

## 30/60/90 Roadmap

### İlk 30 Gün: Foundation
- xurl + TV MCP + YouTube API kurulumu
- İlk 10 içerik (X thread + YouTube Short)
- Landing page taslağı
- Manus task template'leri

### 31-60 Gün: Pipeline
- İçerik takvimi çalışıyor
- Haftada 3-5 organic post
- Waitlist açılışı
- Dashboard public snapshot

### 61-90 Gün: Scale
- 90 günlük canlı performans kanıtı
- Paid ads kararı (eğitim/waitlist sadece)
- KPI dashboard: followers, waitlist, engagement

---

## Agent Rolleri

**@hermes**
- Rol: v1 draft, implementasyon koordinasyonu, içerik onay

**@claude**
- Rol: UltraPlan rekonstrüksiyonu (ground-truth → gap → per-PR), security audit, UR-002

**@gemini**
- Rol: PR implementasyonu, frontend, test

---

## Open Questions

1. Domain: bot.u2algo.com mu, efloud.io mu?
2. X hesap adı: @efloud_bot mu, @efloud mu?
3. YouTube channel: Türkçe mi, İngilizce mi?
4. İçerik takvimi: haftada kaç post? Hangi günler?
5. Waitlist aracı: Notion form mu, başka bir şey mi?
6. Dashboard public snapshot: gerçek PnL gösterilecek mi?
7. Google Ads bütçesi: ilk test için ne kadar?
8. İlk video serisi: hangi konu? (SMC eğitimi? Backtest? Trade journal?)
