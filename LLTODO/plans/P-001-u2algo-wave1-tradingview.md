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

### Yapılacaklar (In Scope - Wave 1-2, ilk 6 hafta)
- TradingView SMC v2 indikatörünü publish et (ücretsiz → premium funnel).
- Telegram sinyal servisini aktif et.
- OHLCV veri API'sini yayına al.
- Backtest-as-a-Service API'sini hazırla.
- Sonraki dalga (Wave 3-4): Strateji robustness audit servisi, Multi-exchange adapter (MT5/OANDA), AI Agent Team API, Kronos tahmin servisi, EFloud Platform.

### Yapılmayacaklar (Out of Scope)
- Canlı trading bot'un kendisini satmak (IP koruması).
- Mevcut production config'lerine dokunmak.
- Mainnet bakiyesiyle risk almak.

## Task'lar (Task Matrix)

| ID | Görev | Agent | Faz | Süre | Dependencies |
|----|-------|-------|-----|------|--------------|
| T-001 | TradingView spec yaz + publish | hermes | IMPLEMENT | 2-3 saat | [] |
| T-002 | Master plan CEO + Eng review | claude | CONSENSUS | 30dk | [] |
| T-003 | Pine Script görsel doğrulama | gemini | CROSSTEST | 20dk | [T-001, T-002] |
| UR-001 | UltraReview (tüm işler bitince) | claude | ULTRAREVIEW | 30dk | [T-001, T-002, T-003] |

## Skill Pipeline
1. **hermes:** `office-hours` → `spec` → `writing-plans` → `implement`
2. **claude:** `plan-ceo-review` → `plan-eng-review` (P-001 review)
3. **gemini:** `vision` (Pine Script screenshots)
4. **claude:** `UltraReview` (tüm DONE task'ları kontrol)
5. **Cross-test:** hermes↔claude, claude↔gemini, gemini↔hermes (rotasyona göre)

## Riskler
- TradingView House Rules ihlali → reject → revize gerekebilir.
- Pine Script v6 syntax hatası → compile error → düzeltme cycle'ı gerekebilir.
- İlk kullanıcı edinme süresi beklenenden uzun olabilir.
