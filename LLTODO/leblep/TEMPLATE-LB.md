# LB-XXX — <kısa başlık>

| Alan | Değer |
|---|---|
| Mode | DECIDE \| DESIGN \| GENERATE-BACKLOG \| SPLIT-DISTRIBUTE |
| Requested-by | @claude |
| Date | <YYYY-MM-DD> |
| Status | LEBLEP_REQUESTED |

## Context (self-contained — Leblep repo'yu bilmiyor varsay)
<problem, ilgili dosya/karar, mevcut durum, neden Claude'u aşıyor / neden gerekli>

## Question / Task
<net soru veya üretilecek çıktı>

## Hard constraints (ihlal = @claude reddeder)
- Trade-path dokunulmaz (`engine/safety/`, `engine/lifecycle.py`, `exchange/`, order path).
- additive / flag-OFF default / clean revert; Simplicity-First (spekülatif soyutlama yok).
- Mainnet risk → risk-ops + operatör sign-off; trade-path görevleri sadece öneri.
- Karpathy 4 prensip (`CLAUDE.md`): failing test + cerrahi diff + geçilen gate.
- <task'a özel kısıtlar>

## Output format (Mode'a göre)
- **DECIDE:** tek karar + gerekçe + reddedilen alternatifler.
- **DESIGN:** adım-adım plan + dosya/satır + risk + test/doğrulama.
- **GENERATE-BACKLOG:** öncelikli, owner/tester-etiketli, additive/test-first görev listesi.
- **SPLIT-DISTRIBUTE:** `S-XXX` SPLIT (her görev owner + ≠owner tester + atama gerekçesi).

## Acceptance (@claude bunu nasıl değerlendirecek)
<adversarial review kriterleri: kabul/ret koşulları, doğrulanacak varsayımlar>
