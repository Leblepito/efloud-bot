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

## Task'lar & Dağıtım (Task Matrix — SCOREBOARD gerekçeli, CONSENSUS'ta onaylanır)

| ID | Görev | Agent | Faz | Süre | Dependencies | Gerekçe (SCOREBOARD'a atıf) |
|----|-------|-------|-----|------|--------------|------------------------------|
| T-001 | TradingView spec yaz + publish | hermes | IMPLEMENT | 2-3 saat | [] | hermes: implementation+deploy specialty (1 DONE, 95%) |
| T-002 | Master plan CEO + Eng review | claude | CONSENSUS | 30dk | [] | claude: review/kod-analizi specialty |
| T-003 | Pine Script görsel doğrulama | gemini | CROSSTEST | 20dk | [T-001, T-002] | gemini: görsel-doğrulama specialty |
| UR-001 | UltraReview (tüm işler bitince) | claude | ULTRAREVIEW | 30dk | [T-001, T-002, T-003] | claude: UltraReview sürücüsü (spec §5 Faz 4) |

> Not (ilk epic): SCOREBOARD herkes için ~0'dan başladığından bu ilk dağıtım statik uzmanlık tanımlarına dayanıyor; sonraki epic'ler birikmiş rakamlara atıf yapacak. Reviewer'lar R-template'teki "Dağıtım Adil mi?" satırında bu dağıtımı onaylar.

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
