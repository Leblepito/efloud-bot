# AGENTS.md — AI Agent Context (efloud-bot)

> Her AI modeli (Claude, Gemini, Hermes, Codex) bu dosyayı okuyarak projeye
> sıfırdan giriş yapabilir. Kapsamlı referans için `skills/social-publishing/SKILL.md`.

## Proje: efloud-bot

Binance USDT-M futures üzerinde SMC doktriniyle otonom trade botu.
Python (CCXT, FastAPI) + TradingView Pine Script v6.

## Kritik Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `HERMES.md` | Operatör kılavuzu (deploy, config, incident) |
| `CLAUDE.md` | Proje bellek, mimari, Pine Script kuralları |
| `skills/social-publishing/SKILL.md` | Sosyal medya pipeline'ı (HER modele) |
| `AGENTS.md` | Bu dosya — AI giriş noktası |

## Sosyal Medya Pipeline'ı (YENİ 2026-07-26)

Tek komut: `python -m scripts.daily_social_run --date $(date -u +%F)`

Bot sinyali → chart PNG (ENTRY/SL/TP) → MP4 klip → X/IG/YT paketleri.
Üç güvenlik kapısı (hepsi default KAPALI): onay, live, platform flag'leri.

Detay: `skills/social-publishing/SKILL.md`

## Test

```bash
python -m pytest --ignore=external_repos --ignore=graphify-out --import-mode=importlib -q
```
