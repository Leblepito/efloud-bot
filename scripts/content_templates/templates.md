# M6 — P-002 efloud X (Twitter) Content Templates

**Channel:** X / Twitter (posted via `xurl`, T-026)
**Gate:** `scripts.content_compliance.find_violations` → must return `[]`
**Proof:** `python scripts/content_templates/verify_compliance.py` → 12/12 CLEAN, negative control 4/4 fires.

The machine-readable source is [`templates.yaml`](./templates.yaml) — the renderer
consumes that. This file is the human-readable view: each template with a **filled
example** and its **gate result**.

Languages: **EN + TR** ready now. **RU / KZ** are skeleton stubs (`TODO`) — see
[`README.md`](./README.md) → "RU/KZ addition" for what's required.

Disclaimers (exact, reused from `engine.content_jobs`):
- TR: `Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.`
- EN: `Not investment advice. Trade at your own risk.`

---

## 1. Signal / Trade-idea — `signal_idea` (single)

Chart-export image (`{chart_img}`, from M2) attached as media, not inlined in text.

**EN** — gate: `[]` · 201 chars
```
BTCUSDT · 15m · LONG idea

Structure: bullish OB + FVG retest
Entry: 64200 · Invalidation: 63500
Targets: 65400 / 66800
R:R ~1:2.6 · Risk ~1.1% per setup

Not investment advice. Trade at your own risk.
```

**TR** — gate: `[]` · 205 chars
```
BTCUSDT · 15m · LONG fikri

Yapı: bullish OB + FVG retest
Giriş: 64200 · Geçersizleşme: 63500
Hedefler: 65400 / 66800
R:R ~1:2.6 · İşlem riski ~1.1%

Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.
```

---

## 1b. Signal / Trade-idea — `signal_idea_thread` (thread, 4 tweets)

Use when context exceeds one tweet. Attach `{chart_img}` on tweet 1.

**EN** — gate: `[]` · per-tweet chars 84 / 77 / 89 / 46
```
1/ ETHUSDT · 1h · SHORT idea 🧵

Structure: bearish breaker + EQH sweep. Chart attached.
2/ Levels (idea, not a call):
Entry 3420 · Invalidation 3505
Targets 3300 / 3180
3/ Risk first: ~1.4% per setup, R:R ~1:2.1. Invalidation if 1h close back above the breaker.
4/ Not investment advice. Trade at your own risk.
```

**TR** — gate: `[]` · per-tweet chars 77 / 84 / 85 / 55
```
1/ ETHUSDT · 1h · SHORT fikri 🧵

Yapı: bearish breaker + EQH sweep. Grafik ekte.
2/ Seviyeler (fikir, çağrı değil):
Giriş 3420 · Geçersizleşme 3505
Hedefler 3300 / 3180
3/ Önce risk: işlem başına ~1.4%, R:R ~1:2.1. Geçersizleşme: breaker üstünde 1h kapanış.
4/ Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.
```

---

## 2. Educational — `educational` (thread, 4 tweets)

Authority content, low compliance risk. Thread because definition + spot + use +
disclaimer cannot fit one 280-char tweet.

**EN** — gate: `[]` · per-tweet chars 108 / 75 / 120 / 67
```
1/ 📚 Order Block (OB)

The last opposing candle before a strong move — where institutions likely placed orders.
2/ How to spot it: last down candle before an up impulse that breaks structure
3/ How to use it: wait for price to return to the OB, then look for confirmation
Mark invalidation first, size by ~1% risk.
4/ Educational content. Not investment advice. Trade at your own risk.
```

**TR** — gate: `[]` · per-tweet chars 91 / 70 / 104 / 74
```
1/ 📚 Order Block (OB)

Güçlü hareketten önceki son ters mum — kurumların emir bıraktığı bölge.
2/ Nasıl bulunur: yapıyı kıran yükseliş impulsundan önceki son düşüş mumu
3/ Nasıl kullanılır: fiyat OB'ye dönünce teyit ara
Önce geçersizleşmeyi işaretle, ~%1 risk ile boyutlandır.
4/ Eğitim içeriğidir. Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.
```

---

## 3. Performance / Recap — `performance_recap` (single)

Weekly. **SIM/backtest explicitly labeled** — the gate-required `[SIMULATED]` bracket
token (CMP-3 `unlabeled_simulation`) — outcome in **R** (not $), **no guarantee**.

**EN** — gate: `[]` · 232 chars
```
📊 Weekly recap — 2026-W24 [SIMULATED]

Ideas shared: 7
Reached first target: 4/7
Avg outcome: +1.8R · Avg risk: 1.3% per setup

Simulated/backtest results. Past performance is not indicative of future results. Not investment advice.
```

**TR** — gate: `[]` · 245 chars
```
📊 Haftalık özet — 2026-W24 [SIMULATED]

Paylaşılan fikir: 7
İlk hedefe ulaşan: 4/7
Ortalama sonuç: +1.8R · İşlem başına risk: %1.3

Simülasyon/backtest sonuçlarıdır. Geçmiş performans gelecek için garanti değildir. Bu yatırım tavsiyesi değildir.
```

---

## 4. Promotional — `promotional` (single)

Product/feature + compliant CTA. Free-waitlist / research-log framing — **no income
promise** (aligns with P-002 reframe: single Pine = free, premium dropped).

**EN** — gate: `[]` · 253 chars
```
Our SMC research log is public — every idea, every invalidation, labeled.

New: 15m + 1h multi-timeframe chart exports on every idea.

Free waitlist 👉 https://u2algo.com/waitlist

No income promises, no guarantees. Education only. Not investment advice.
```

**TR** — gate: `[]` · 264 chars
```
SMC araştırma günlüğümüz herkese açık — her fikir, her geçersizleşme, etiketli.

Yeni: her fikirde 15m + 1h çoklu-zaman grafiği.

Ücretsiz bekleme listesi 👉 https://u2algo.com/waitlist

Gelir vaadi yok, garanti yok. Eğitim amaçlıdır. Bu yatırım tavsiyesi değildir.
```

---

## 5. Market-update / Commentary — `market_commentary` (single, optional)

Context only — explicitly **not a signal**.

**EN** — gate: `[]` · 215 chars
```
BTCUSDT 4h map 🗺️

Bias: neutral → leaning long above range mid
Key levels: range 61800–66500, mid 64100
Watching: reaction at range mid for a continuation read

Market commentary, not a signal or investment advice.
```

**TR** — gate: `[]` · 234 chars
```
BTCUSDT 4h haritası 🗺️

Önyargı: nötr → range ortası üstünde long eğilimli
Kritik seviyeler: range 61800–66500, orta 64100
İzlenen: devam okuması için range ortasındaki tepki

Piyasa yorumudur; sinyal ya da yatırım tavsiyesi değildir.
```

---

## Compliance summary

| Template | EN | TR | RU | KZ | Format |
|---|---|---|---|---|---|
| signal_idea | ✅ `[]` | ✅ `[]` | stub | stub | single |
| signal_idea_thread | ✅ `[]` | ✅ `[]` | stub | stub | thread×4 |
| educational | ✅ `[]` | ✅ `[]` | stub | stub | thread×4 |
| performance_recap | ✅ `[]` | ✅ `[]` | stub | stub | single |
| promotional | ✅ `[]` | ✅ `[]` | stub | stub | single |
| market_commentary | ✅ `[]` | ✅ `[]` | stub | stub | single |

**checked = 12 · clean = 12 · failed = 0.** All single tweets ≤ 280; threads ≤ 280 per tweet.

Negative control (proves the gate is live, not a no-op):

| input | gate result |
|---|---|
| `Garantili getiri sunuyoruz` | `['banned_phrase:Garantili getiri']` |
| `Bugün 250$ kâr kilitledik` | `['absolute_money']` |
| `%80 kazanç oranı` | `['performance_pct_claim']` |
| `73.2% win rate` | `['performance_pct_claim']` |
