# Hermes Yetenek Haritası & Gap Analizi — 2026-05-31

> Utku'nun "u2algo marketing & multi-platform yayın sistemi" vizyonu için
> Hermes'in (bu ajan) projeyi taradıktan sonra çıkardığı MEVCUT DURUM + BOŞLUK haritası.
> Amaç: revizyonlar bitince işe eksik yetenekle başlamamak.

---

## 0. Utku'nun hedef vizyonu (özet)

1. Bot Binance'de canlı trade ediyor → `bot.ualgotrade.com` dashboard'da izleniyor. **(VAR)**
2. **u2algo.com**'da bu botu/sinyalleri SATIŞA sun. **(YOK — landing/satış sitesi kurulacak)**
3. **TradingView**'da `.pine` script olarak kullanıcılara sun (MCP bağlandı). **(KISMEN — pine kodu var, satış/publish akışı yok)**
4. **u2algo Instagram + u2algo X** hesaplarında otomatik paylaşım. **(YOK)**
5. **ualgobot** Telegram botu → **u2algo topluluğuna** bağla, topluluk iletişimi. **(KISMEN — telegram alerter var, community bağlama yok)**
6. Bot artık **3 mantık: scalp / orta / uzun vadeli** config'leri. **(YOK — henüz configs/ altında yok; Utku ekleyecek)**
7. **TradingView chart screenshot** → sinyal tetikleyince → **YouTube video + X + Instagram** için
   metin/video/görsel yorumlu marketing içeriği üret & yayınla. **(YOK — kurulacak ana sistem)**

---

## 1. MEVCUT DURUM (VAR olan yetenekler)

### Trade çekirdeği (olgun)
- SMC v1 CANLI (Hetzner VPS, Binance USDT-M futures). SMC v2 kod hazır, 3-katman inert.
- Backtest motoru: `backtest/cli.py` (single/portfolio/grid/compare).
- Forex adapter (MT5/OANDA) protocol + concrete impl (Faz 3.5 done).
- Hedge mode + cross margin (Faz 3.6 done).

### Pine (KISMEN — kod var, henüz publish/satış akışı yok)
- `pine/PINE_SPEC.md` — V1 + V2 tam spec (onaylı).
- `pine/efloud_signals_v1.pine` (indikatör), `pine/efloud_strategy_v1.pine` (strateji) — V1 fidelity fix'leri uygulanmış (2026-05-30).
- TradingView MCP araçları CLAUDE.md'de belgeli: `tv_health_check`, `pine_set_source`, `pine_smart_compile`, `pine_get_errors`, `pine_save`.
  - ⚠️ NOT: TradingView MCP `.mcp.json`'da TANIMLI DEĞİL. `.mcp.json` sadece github MCP içerir.
    Pine MCP muhtemelen Claude Code desktop config'inde / harici. Hermes'te kurulması gerekebilir.

### Social/AI katmanı (backend slice var, research-only)
- `backend/social/*` — doctrine/hypotheses/research-snapshot read-only endpoints.
- `scripts/research_social_strategy.py` — candidate research runner (NO_PROMOTION guard'lı).
- `scripts/collect_social_doctrine.py`.
- `frontend/components/SocialLearningCenter.tsx`, `SocialFeeds.tsx`, `InteractiveChart.tsx`.
- Gemini sentiment + SMC structure validation (Faz 2.1/2.2 done).

### Telegram (alerter var, community değil)
- `ops/alerter/telegram_client.py` + `alerter.py` — sinyal/health alert gönderimi.
- `ops/overseer/sinks/telegram.py` — overseer alerts.
- Env: `EFLOUD_TELEGRAM_TOKEN`, `EFLOUD_TELEGRAM_CHAT_ID`.

### Dashboard / frontend
- FastAPI :8080 + Next.js 15 static export. `bot.ualgotrade.com`.

### Marketing dokümanları (niyet var, kod yok)
- `docs/marketing/GO_TO_MARKET_2026-05-28.md` — marka cümlesi, yasak/izinli ifadeler, içerik sütunları, 30g ritim.
- `docs/PROJECT_OPERATING_SYSTEM_2026-05-28.md` — trade/eng/marketing 3 masa, 30/60/90 plan.
- `docs/runbooks/social-research-promotion.md` — 7-gate promotion (research→live).

### Hermes/ajan altyapısı
- `.claude/agents/`: efloud-code-reviewer, efloud-explorer, efloud-risk-ops-reviewer, efloud-test-engineer.
- `.claude/skills/`: bugfix-workflow, deploy-safety, forex-adapter-research, trading-risk-checklist, uiux-audit.
- `.mcp.json`: SADECE github MCP.
- graphify knowledge graph: `graphify-out/graph.json` (+ git post-commit hook ile auto-update).

---

## 2. BOŞLUKLAR (kurulacak / Utku ekleyecek)

| # | Boşluk | Tip | Kim | Not |
|---|--------|-----|-----|-----|
| G1 | **scalp/orta/uzun config'leri** | config | Utku ekleyecek | configs/ altında henüz yok |
| G2 | **u2algo.com satış/landing sitesi** | yeni proje | Hermes kurabilir | GTM guardrails hazır |
| G3 | **TradingView screenshot capture** otomasyonu | yeni sistem | Hermes | MCP `tv_*` araçları var ama screenshot tool'u doğrulanmalı |
| G4 | **Sinyal→tetikleme** event hattı (signal fired → content pipeline) | yeni sistem | Hermes | Pub/Sub veya webhook var (Faz 3.1), content trigger'a bağlanacak |
| G5 | **YouTube video üretimi** (screenshot + metin yorumu → video) | yeni sistem | Hermes | manim-video / ascii-video skill'leri var; YouTube upload MCP/API yok |
| G6 | **X (Twitter) otomatik paylaşım** | yeni entegrasyon | Hermes | x_search toolset var (okuma); POST/publish için API/MCP yok |
| G7 | **Instagram otomatik paylaşım** | yeni entegrasyon | Hermes | Hiç yok — Graph API / 3rd-party gerekecek |
| G8 | **ualgobot ↔ u2algo community** bağlama | telegram | Hermes+Utku | alerter var, community/group yönetimi yok |
| G9 | **Marketing content generator** (metin+görsel+video yorumu) | yeni sistem | Hermes | image_generate, baoyu-* skill'leri, video_gen toolset mevcut |
| G10 | **efloud X hesabı izleme → sentez → u2algo özgün içerik** | yeni sistem | Hermes | efloud postlarını topla/analiz et, Utku'nun mantığıyla sentezle, u2algo'da özgün post üret. İçerik telif/atıf + risk disclosure'a dikkat. |
| G11 | **efloud postlarından bot strateji varyantı türetme** | research-only | Hermes | X içeriğinden hipotez → candidate config. SADECE research-only, 7-gate promotion (social-research-promotion.md). Canlı config'e otomasyon DOKUNMAZ. |

### G10/G11 akış notu (efloud X → sentez)

**Kaynak kimliği (sabit):**
- X hesabı: `https://x.com/Efloud` — görünen ad: **"Efloud TA & Charts"** (teknik analiz + grafik içerikleri).
- Erişim: SALT-OKUMA yeterli (`x_search` toolset / browser). Yazma/POST gerekmez.
- Telegram kaynak adı: Utku sonra verecek (TODO).

```
efloud X postları (izle/topla)
   │  x_search (okuma) / X API
   ▼
analiz + sentez (Utku'nun mantığı + Hermes)
   ├──► u2algo özgün içerik (X/Instagram/YouTube)   [G10 — marketing, atıf + risk disclosure]
   └──► strateji hipotezi → candidate_*.yaml         [G11 — research-only, 7-gate, ASLA canlı]
```

- Kaynak toplama: `x_search` toolset (okuma) veya X API. `scripts/collect_social_doctrine.py` zaten benzer doctrine toplama yapıyor — efloud feed'i buraya kaynak olarak eklenebilir.
- Hipotez→config: `scripts/research_social_strategy.py` (NO_PROMOTION guard'lı) kullanılır. Candidate `configs/candidates/` altına yazılır, canlıya ASLA.
- İçerik sentezi: `humanizer` (AI-ism temizle), `baoyu-*` (görsel), GTM guardrails (getiri vaadi yok).

---

## 3. KURULMASI GEREKEBİLECEK Hermes yetenekleri (iş başlayınca)

### MCP'ler
- **TradingView MCP** — pine compile/save + (varsa) chart screenshot. `.mcp.json`'a eklenmeli VEYA Hermes config'inde MCP server tanımlanmalı. native-mcp skill ile kurulur.
- **YouTube Data API** (upload) — muhtemelen MCP yok, google-workspace skill + YouTube API veya custom script.
- **X/Twitter API** (write) — publish için. x_search sadece okuma.
- **Instagram Graph API** — Meta business hesabı + Graph API.

### Skill'ler (zaten VAR — kullanılacaklar)
- `youtube-content` (transcript→içerik), `baoyu-infographic`/`baoyu-comic`/`baoyu-article-illustrator` (görsel),
  `manim-video`/`ascii-video` (video), `humanizer` (AI-ism temizleme), `native-mcp` (MCP kurulum),
  `trading-strategy-research-pipelines` (research-only hatları).
- Toolset'ler: `image_gen`, `video_gen`, `video`, `tts`, `x_search`, `web`, `browser`.

### Yazılacak yeni skill'ler (öneri)
- `efloud-content-pipeline` — sinyal→screenshot→metin/görsel/video→multi-platform publish akışı.
- `tradingview-chart-capture` — TV MCP ile chart screenshot + annotate.
- Platform publish skill'leri (x-publish, instagram-publish, youtube-upload) — API'ler netleşince.

---

## 4. DEĞİŞMEZ GÜVENLİK SINIRLARI (her zaman geçerli)

- Canlı `config.yaml`, `config.phase2_1k.yaml`, `.env`, `docker-compose.prod.yml`, VPS deploy, mainnet → SADECE Utku/Hermes-insan. Otomasyon DEĞİŞTİRMEZ.
- AI/social çıktısı doğrudan emir üretmez.
- Marketing içeriği: getiri garantisi / "kesin kazanır" / fon toplama YASAK. Risk disclosure ZORUNLU.
- Strategy değişimi research-only candidate olarak kalır; promotion 7-gate + insan onayı.

---

## 5. SONRAKİ ADIM

Utku revizyonları bitirip "başla" deyince:
1. Bu dokümanı + ilgili kaynak dosyaları tekrar oku (güncel diff'i al).
2. Yukarıdaki G1-G9 boşluklarından hangisi öncelik → Utku ile netleştir.
3. Gerekli MCP/skill'leri native-mcp + skill_manage ile kur.
4. Spec→plan→impl (TDD) + güvenlik guard'larıyla ilerle.
