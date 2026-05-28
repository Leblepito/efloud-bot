# Efloud Growth Operating System Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Efloud-bot'u güvenli şekilde geliştirmek, trading kanıtını biriktirmek, yazılım kalitesini yükseltmek ve pazarlamayı erken ama regülasyon/risk kontrollü başlatmak.

**Architecture:** Proje üç ayrı ama bağlı hatla yönetilecek: Trading Research, Software/Product, Marketing/Growth. Trading hattı canlı sistemi değiştirmeden backtest + shadow + insan onayı üretir. Software hattı testli PR ve dashboard/observability üretir. Marketing hattı paid-ad yerine önce güven inşa eden içerik, waitlist ve kanıt arşivi üretir.

**Tech Stack:** Python/FastAPI, Binance USDT-M futures, pytest, backtest compare, Next.js dashboard, social research pipeline, docs/runbooks.

---

## Safety invariants

1. Canlı `config.yaml`, `.env`, `docker-compose.prod.yml`, VPS deploy ve mainnet risk ayarları bu planla otomatik değişmez.
2. Sosyal medya, LLM, Gemini/Claude veya marketing içeriği canlı emir kararına bağlanmaz.
3. Yeni strateji fikri sadece candidate config/report olarak kalır; canlıya geçiş için test, backtest, shadow ve Utku/Hermes onayı gerekir.
4. Marketing dili yatırım tavsiyesi, garanti kâr, getiri vaadi veya fon toplama iddiası içermeyecek.
5. Öncelik sırası: sermaye koruma > sistem güvenilirliği > ölçülebilir edge > ürünleştirme > agresif pazarlama.

---

## Masa kararı: Trader + Yazılımcı + Marketing uzmanı ne derdi?

### Trader / Fon yöneticisi kararı

- Paid reklam için erken; çünkü canlı performans kanıtı henüz yeterince uzun değil.
- Şimdi yapılması gereken: trade journal, backtest baseline, shadow raporları, risk metrikleri, drawdown limitleri.
- Satılacak şey “kazanç vaadi” değil, “şeffaf araştırma ve risk-disiplinli algoritmik trading yolculuğu”.

### Yazılımcı / Mimar kararı

- Önce sistem güvenilirliği: test suite, staging/shadow, observability, dashboard, reproducible backtest.
- AI/social-learning doğru yönde başlamış ama research-only kalmalı.
- Her feature TDD + küçük PR + rollback planıyla yürümeli.

### Marketing uzmanı kararı

- Sosyal medya hemen başlamalı, paid ads beklemeli.
- İlk 30-60 gün hedef: marka güveni, eğitim içerikleri, build-in-public, waitlist, proof log.
- Paid reklam ancak şu kanıtlar oluşunca: 90 günlük canlı metrik, net ürün vaadi, landing page, risk disclosure, funnel ölçümü.

### Nihai karar

Şimdi pazarlamaya geçiyoruz ama reklam bütçesiyle değil: organik içerik + waitlist + kanıt arşivi. Ürün ve trading kanıtı olgunlaşınca düşük bütçeli retargeting/test ads başlar.

---

## Workstreams

### W1 — Trading Research & Fund Management

Owner: Hermes/Utku + Architect review

Amaçlar:
- v1 canlı botu güvenli izlemek.
- v2 shadow/backtest ile kanıt toplamak.
- Sosyal doktrinden gelen hipotezleri sadece research candidate olarak test etmek.

İlk backlog:
1. Günlük trading health checklist oluştur.
2. Haftalık performans raporu formatı oluştur: PnL, win rate, avg R, max DD, exposure, symbol breakdown.
3. `scripts/research_social_strategy.py` candidate config + manifest akışını kullanarak sosyal hipotezleri ölç.
4. 180d baseline compare için veri hazırlığı planla.
5. v2 shadow rollout için karar raporu şablonu yaz.

Validation:
- `pytest backend/tests/test_social_* backend/tests/test_research_social_strategy.py -q`
- `python -m backtest.cli compare ...` sadece cached OHLCV varsa.
- Canlı config diff yok.

### W2 — Software/Product Engineering

Owner: Gemini Flash 3.5 / Claude Opus 4.7 mühendis ajanları; Hermes mimari/QA

Amaçlar:
- Test ve observability borcunu azaltmak.
- Research Center/Learning Center dashboard'u ürünleştirmek.
- Exchange adapter ve hedge/cross-margin katmanını stabil tutmak.

İlk backlog:
1. Social Learning API test coverage genişlet.
2. Frontend `SocialLearningCenter` bileşenini ekle.
3. Backtest report içinde hypothesis/doctrine tags görünürlüğünü doğrula.
4. Dashboard health + positions + risk + learning snapshot tek ekranda topla.
5. PR template'e “live config touched?” ve “research-only?” checkbox ekle.

Validation:
- Backend targeted pytest.
- Frontend typecheck/build.
- No live config/compose/env mutation.

### W3 — Marketing/Growth

Owner: Hermes + gerektiğinde Gemini/Claude içerik taslakları

Amaçlar:
- Güven oluşturan organik varlık kurmak.
- Waitlist ve topluluk sinyali toplamak.
- Paid ads için kanıt ve funnel altyapısı hazırlamak.

İlk backlog:
1. Positioning dokümanı: “SMC tabanlı, risk-disiplinli, şeffaf algoritmik trading araştırması”.
2. Landing page taslağı: waitlist + risk disclosure + dashboard screenshot/video.
3. 30 günlük içerik takvimi: build-in-public, risk yönetimi, backtest notları, trade journal, mimari anlatımlar.
4. Brand guardrails: yasak kelimeler, disclaimer, getiri vaadi yok.
5. KPI dashboard: followers, waitlist conversion, post engagement, demo request, trust signals.

Validation:
- Her içerikte risk disclaimer.
- Finansal tavsiye/getiri vaadi yok.
- Paid ads başlamadan 90 gün canlı kanıt veya açık araştırma ürünü kararı.

---

## 30/60/90 roadmap

### İlk 30 gün: Foundation + trust

- Trading: v1 canlı izleme, v2 shadow hazırlığı, daily/weekly report şablonları.
- Software: Social research backend tamamlanır, runner guard/test yeşil, frontend planlanır.
- Marketing: organik hesaplar, landing/waitlist taslağı, 30 içerik fikri.

Exit criteria:
- Test suite yeşil.
- Research-only sınırlar dokümante.
- Haftalık trading raporu üretilebiliyor.
- İlk organik içerik serisi hazır.

### 31-60 gün: Evidence + product surface

- Trading: 180d compare raporları, shadow log inceleme, hypothesis gap report.
- Software: Learning Center dashboard, report exports, runbook'lar.
- Marketing: haftada 3-5 organik post, build-in-public thread, waitlist açılışı.

Exit criteria:
- En az 1-2 hipotez için backtest verdict.
- Dashboard research snapshot gösteriyor.
- Waitlist dönüşümü ölçülüyor.

### 61-90 gün: Controlled growth

- Trading: v2 rollout kararı için gate raporu; hard reject varsa redesign.
- Software: staging/shadow workflow polish, PR/QA automation.
- Marketing: small-budget experiment yalnızca eğitim/waitlist için; kâr vaadi yok.

Exit criteria:
- 90 günlük canlı/shadow kanıt seti.
- Paid ads için compliance-safe landing page.
- Net ürün stratejisi: private alpha, SaaS dashboard, sinyal değil araştırma ürünü, veya kapalı fon-içi tooling.

---

## Agent task distribution

### Hermes / Architect + Fund Manager

- Risk sınırları, roadmap, PR sign-off, production guardrails.
- Backtest/shadow sonuçlarını yorumlar.
- Marketing iddialarını risk/compliance filtresinden geçirir.

### Gemini Flash 3.5 / Engineer

- Mekanik implementation: pytest, scripts, frontend components, docs table updates.
- Graphify/codebase scans, test suite fixes.
- Küçük ve izole PR'lar.

### Claude Opus 4.7 / Senior Engineer-Reviewer

- Mimari/spec, strategy gap analysis, code review, edge-case audit.
- Risky changes için two-stage review.
- Prompt/agent workflow iyileştirme.

### Marketing support agents

- İçerik varyasyonları, landing copy, thread/video script.
- Hermes onayı olmadan yayın yok.
- Finansal tavsiye/getiri vaadi yok.

---

## Immediate tasks

### Task 1: Verify current social research slice

Run:

```bash
python -m pytest backend/tests/test_social_feeds.py backend/tests/test_social_doctrine.py backend/tests/test_social_archive.py backend/tests/test_social_hypotheses.py backend/tests/test_social_reports.py -q
```

Expected: PASS.

### Task 2: Add research runner safety tests

Files:
- Modify: `scripts/research_social_strategy.py`
- Create: `backend/tests/test_research_social_strategy.py`

Expected:
- Runner accepts custom `--state`.
- Candidate configs include `NO_PROMOTION`.
- Manifest includes `research_only: true` and `no_promotion: true`.
- Runner refuses `config.yaml` as base config.

### Task 3: Write operating docs

Files:
- Create: `docs/PROJECT_OPERATING_SYSTEM_2026-05-28.md`
- Create: `docs/marketing/GO_TO_MARKET_2026-05-28.md`
- Create: `.hermes/plans/2026-05-28_efloud-growth-operating-system.md`

Expected:
- Trade, software, marketing workstreams clear.
- Paid ads decision documented.
- Agent role distribution documented.

### Task 4: Run validation

Run:

```bash
python -m pytest backend/tests/test_social_feeds.py backend/tests/test_social_doctrine.py backend/tests/test_social_archive.py backend/tests/test_social_hypotheses.py backend/tests/test_social_reports.py backend/tests/test_research_social_strategy.py backend/tests/test_api_smoke.py backend/tests/test_reverse_guard.py backend/tests/test_backtest_cli_compare.py -q
```

Expected: PASS.

---

## Open questions

1. Efloud markası B2C sinyal/dash mı olacak, yoksa önce private research log olarak mı kalacak?
2. Marketing dili Türkçe mi İngilizce mi başlayacak?
3. Landing/waitlist için domain ve form aracı ne olacak?
4. Paylaşımlarda gerçek PnL gösterilecek mi, yoksa sadece oran/risk metrikleri mi?
5. Paid ads için minimum kanıt eşiği: 60 gün mü, 90 gün mü?
