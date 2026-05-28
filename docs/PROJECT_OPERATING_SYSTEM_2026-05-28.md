# Efloud-bot Project Operating System — 2026-05-28

Bu doküman Efloud-bot geliştirme düzenini üç masada toplar: trade/fon yönetimi, yazılım/product engineering, marketing/growth.

## 1. Ana karar

Sosyal medya şimdi başlamalı; paid reklam henüz başlamamalı.

Gerekçe:
- Bot canlı ama uzun dönem, pazarlanabilir performans kanıtı henüz erken aşamada.
- Erken paid ads yanlış beklenti ve regülasyon/compliance riski yaratır.
- Buna karşılık organik içerik, build-in-public, waitlist ve şeffaf research log düşük riskli ve değerlidir.

Doğru pozisyonlama:
- “Kâr vadeden sinyal servisi” değil.
- “SMC tabanlı, risk-disiplinli, şeffaf algoritmik trading araştırması ve otomasyon platformu.”

## 2. Değişmez güvenlik sınırları

- Canlı `config.yaml`, `.env`, `docker-compose.prod.yml`, VPS deploy ve mainnet parametreleri otomasyonla değişmez.
- AI/social-learning çıktısı doğrudan emir üretmez.
- Strategy değişiklikleri candidate config/report olarak kalır.
- Promotion için test + backtest + shadow + insan onayı gerekir.
- Marketing içeriği yatırım tavsiyesi, garanti getiri, “kesin kazanır” veya fon toplama iddiası içermez.

## 3. Workstream'ler

### A. Trading Research / Fund Management

Sorumluluklar:
- Canlı v1 performansını izlemek.
- v2 shadow/backtest kararlarını yönetmek.
- Sosyal doktrinlerden hipotez üretip sadece research-only ölçmek.
- Risk, drawdown, exposure ve lifecycle metriklerini haftalık raporlamak.

Haftalık çıktı:
- PnL ve R-multiple özeti.
- Win rate, avg realized RR, max drawdown, stop-hunt rate.
- En iyi/kötü semboller.
- Açık riskler ve önerilen deneyler.

### B. Software / Product Engineering

Sorumluluklar:
- Testli küçük PR'lar.
- Dashboard, API, backtest, observability.
- Social Learning Center / Research Center.
- Exchange adapter, hedge mode, safety guard testleri.

Kalite kapısı:
- Targeted pytest yeşil.
- No live config mutation.
- Research-only değişikliklerde promotion guard testi.
- Rollback planı.

### C. Marketing / Growth

Sorumluluklar:
- Organik içerik ve güven inşası.
- Waitlist / landing page.
- Ürün anlatımı: risk, süreç, şeffaflık.
- Paid ads için kanıt ve funnel hazırlığı.

Kanal sırası:
1. X/Twitter build-in-public.
2. Telegram/Discord community updates.
3. Landing page + waitlist.
4. YouTube/short video eğitim içerikleri.
5. 60-90 gün sonra küçük bütçeli paid ads testi.

## 4. 30/60/90 plan

### İlk 30 gün

Trading:
- Daily health checklist.
- Weekly report template.
- v2 shadow hazırlığı.
- Social hypotheses için candidate research manifest.

Software:
- Social research tests.
- Research runner guard.
- API smoke doğrulama.
- Learning Center frontend planı.

Marketing:
- Positioning ve brand guardrails.
- 30 günlük organik içerik takvimi.
- Landing/waitlist taslağı.

### 31-60 gün

Trading:
- 180d compare raporları.
- Shadow log analizi.
- Doctrine-to-engine gap report.

Software:
- Frontend Learning Center.
- Report exports.
- CI/test workflow polish.

Marketing:
- Haftada 3-5 organik paylaşım.
- İlk waitlist ölçümü.
- Case-study formatı.

### 61-90 gün

Trading:
- v2 rollout gate raporu.
- Hard reject varsa redesign.

Software:
- Staging/shadow workflow stabilizasyonu.
- Dashboard polish.

Marketing:
- Paid ads sadece eğitim/waitlist için küçük bütçe test.
- Performans iddiası yok; risk disclosure zorunlu.

## 5. Ajan rolleri

Hermes:
- Mimar + fon yöneticisi + güvenlik kapısı.
- Production/deploy/risk onayı.
- Plan ve task orchestration.

Gemini Flash 3.5:
- Hızlı mühendislik, test, script, frontend uygulama.
- Mekanik işlerde güçlü.

Claude Opus 4.7:
- Mimari/spec, code review, edge-case analysis.
- Risky strategy/software değişikliklerinde reviewer.

Marketing ajanları:
- İçerik taslakları, landing copy, sosyal medya varyasyonları.
- Hermes/Utku onayı olmadan yayın yok.

## 6. Şu an repo durumu

Doğrulanan hazırlıklar:
- Social learning backend slice mevcut: `backend/social/*`.
- Read-only endpoints mevcut: `/api/social/doctrine`, `/api/social/hypotheses`, `/api/social/research-snapshot`.
- Candidate research runner mevcut: `scripts/research_social_strategy.py`.
- Social tests mevcut: `backend/tests/test_social_*.py`.

Bugün tamamlanan ek hazırlık:
- Research runner `--state` ve `--plan-only` destekler.
- Runner protected `config.yaml` base olarak verilirse reddeder.
- Candidate configs ve manifest `NO_PROMOTION` / `research_only` / `no_promotion` bayrakları taşır.
- `backend/tests/test_research_social_strategy.py` eklendi.

## 7. İlk uygulanacak backlog

1. Frontend Learning Center planını uygulama.
2. Social research endpoint coverage genişletme.
3. Doctrine-to-engine gap report scripti.
4. Weekly trading report generator.
5. Landing/waitlist copy + brand guardrails.
6. 180d baseline compare için cache/veri hazırlığı.

## 8. Paid ads karar kriteri

Paid ads başlamadan minimum koşullar:
- En az 60-90 gün canlı/shadow izleme raporu.
- Landing page + risk disclosure.
- Net conversion goal: waitlist/demo, doğrudan “yatırım yap” değil.
- Content archive: en az 20 güven inşa eden post.
- Compliance review: getiri vaadi yok.

Karar: Bugün paid ads yok. Bugün organik pazarlama, içerik altyapısı ve waitlist hazırlığı var.
