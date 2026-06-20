# LLTODO / leblep — Orchestrator Request Lane

Bu dizin **@leblep** orkestratör ajanına (GPT-5.5 + Minimax-M3 + DeepSeek-V4-Pro → ortak
karar, tek çıktı) yapılan istekleri ve yanıtları tutar. Rol kartı: `../PROMPT-leblep.md`.

## Akış (relay disiplini — Gemini ile aynı)

```
@claude  →  LB-XXX-<slug>.md            (Status: LEBLEP_REQUESTED)
operatör →  Leblep'e iletir (kopyala-yapıştır)
operatör →  LB-XXX-<slug>.response.md    (Status: LEBLEP_RETURNED)
@claude  →  adversarial review → kabul edilenler owner/tester-etiketli BACKLOG
```

- İstek dosyası: `LB-XXX-<slug>.md` (template: `TEMPLATE-LB.md`).
- Yanıt dosyası: `LB-XXX-<slug>.response.md` (aynı XXX numarası).
- `Status:` alanı **bu dosyalara özeldir** — STATE.md epic state-machine'ine (DRAFT→DONE)
  karışmaz. Lint bu dizini isimlendirme kuralına tabi tutmaz (`P/R/T/S/X` prefix'leri
  yalnızca plans/reviews/tasks/splits/tests içindir).

## Ne zaman Leblep'e gidilir (4 tetikleyici)
1. **EXCEEDS-CLAUDE / DEADLOCK** — Claude'u aşan / consensus tıkanması.
2. **CROSS-CUTTING / IRREVERSIBLE** — geri dönülmesi zor mimari/strateji.
3. **GENERATE-BACKLOG** — açık + ertelenmiş iş kalmadığında sistemi geliştirecek backlog.
4. **SPLIT-DISTRIBUTE** — onaylı planı finalize edip görev dağıt.

## Self-improvement loop (backlog boşalınca)
Koşul: `tasks/IN_PROGRESS/` boş + gate'siz owned-BACKLOG yok + gerçek-para işleri (Bot V2
go-live vb.) operatör-gate'inde bekliyor.
1. Önce **parked edge bulgularını** (audit C4/H1/H5/H6/H7/M1/M2, Edge Measurement Core
   gate'i) drain et — bunlar zaten tanımlı, üretim gerektirmez.
2. Tükenince @claude bir `GENERATE-BACKLOG` LB-XXX isteği açar (STATE.md + bot-ops audit
   bulgularıyla seed'ler).
3. Operatör iletir/commit'ler → @claude adversarial review → BACKLOG.

## Kabul (acceptance) ilkesi
Her Leblep çıktısı @claude tarafından **kör değil, eleştirel** değerlendirilir; kabul için:
additive/flag-OFF, Simplicity-First (over-engineering reddedilir), trade-path görevleri
sadece öneri (risk-ops + operatör sign-off), her görev test-first hedefe çevrilebilir.
