---
plan_id: P-001
author: hermes
status: AWAITING_REVIEW
created: 2026-06-09T12:00:00+03:00
reviewers: [claude, gemini]
approvals_needed: 2
approvals_received: 0
---

# Plan: u2algo Master Plan — 12 Ürün, 4 Wave

## Amaç
efloud-bot kod tabanından 12 satılabilir ürün çıkar, 3 ayda $14K MRR hedefine ulaş.

## Kapsam

**Yapılacak (Wave 1-2, ilk 6 hafta):**
- TradingView SMC v2 indikatörü publish (ücretsiz → premium funnel)
- Telegram sinyal servisi
- OHLCV veri API'si
- Backtest-as-a-Service API

**Yapılacak (Wave 3-4, sonraki 6 hafta):**
- Strateji robustness audit servisi
- Multi-exchange adapter (MT5/OANDA)
- AI Agent Team API
- Kronos tahmin servisi
- EFloud Platform (hepsi bir arada)

**Yapılmayacak:**
- Canlı trading bot'un kendisini satmak (IP koruması)
- Mevcut production config'lere dokunmak
- Mainnet bakiyesiyle risk almak

## Task'lar (Wave 1: TradingView)

| ID | Görev | Agent | Faz | Süre |
|----|-------|-------|-----|------|
| T-001 | TradingView spec yaz + publish | hermes | IMPLEMENT | 2-3 saat |
| T-002 | Master plan CEO + Eng review | claude | CONSENSUS | 30dk |
| T-003 | Pine Script görsel doğrulama | gemini | CROSSTEST | 20dk |
| - | UltraReview (tüm işler bitince) | claude | ULTRAREVIEW | 30dk |

## Skill Pipeline (Wave 1)

```
1. hermes: office-hours → spec → writing-plans → implement
2. claude: plan-ceo-review → plan-eng-review (P-001 review)
3. gemini: vision (Pine Script screenshots)
4. claude: UltraReview (tüm DONE task'ları kontrol)
5. Cross-test: hermes↔claude, claude↔gemini, gemini↔hermes
```

## Dayandığı Dosyalar
- Ana plan: `.hermes/plans/2026-06-09_u2algo-master-plan.md`
- CEO portföy: `docs/ceo-product-portfolio-2026-06-09.md`
- Pine Script: `pine/publish/efloud_signals_v2_en.pine`
- gstack entegrasyon: `.hermes/plans/2026-06-09_gstack-integration.md`

## Riskler
- TradingView House Rules ihlali → reject → revize gerekebilir
- Pine Script v6 syntax hatası → compile error → düzeltme cycle
- İlk kullanıcı edinme süresi beklenenden uzun olabilir
