---
name: efloud-forex-adapter-research
description: Research and decision document for picking a forex broker adapter (MT5, OANDA, cTrader, etc.) for efloud-bot, given Turkish + Thai user banking realities and Linux/Docker deploy constraints. Use BEFORE writing any forex adapter code. Output is a recommendation, not an implementation.
---

# efloud-forex-adapter-research

`exchange/__init__.py` is currently Binance-bound. To support forex we need a
pluggable adapter. This skill produces the **broker selection memo**, not the
adapter code itself.

## Context to load
- `exchange/__init__.py` — current Binance interface surface.
- `engine/lifecycle.py` — Position contract the adapter must satisfy.
- `main.py` — how `BinanceClient` is wired (what we'll inject).
- `docker-compose.prod.yml` — current deploy target (Linux containers).

## Candidates to evaluate

| Broker | Python SDK | Linux/Docker | TR retail use | TH retail use | Demo account |
|--------|-----------|--------------|---------------|---------------|--------------|
| **MetaTrader 5** | `MetaTrader5` (official) | ❌ Windows-only — needs Wine bridge or Win VPS | High (most TR brokers) | High (XM/Exness/FBS) | Yes |
| **OANDA v20** | `oandapyV20` (official REST) | ✅ Pure REST/JSON | Low | Medium | Yes |
| **cTrader Open API** | `ctrader-open-api` (FIX-based) | ✅ Linux ok | Medium | Low-Medium | Yes |
| **Interactive Brokers** | `ib_insync` (TWS gateway) | ⚠️ Needs IB Gateway container | Low | Low | Yes (paper) |
| **Dukascopy JForex** | Java-only | ❌ JVM bridge needed | Low | Low | Yes |

## Decision criteria (weighted)

1. **TR + TH banking compatibility (35%)** — does a trader's bank actually fund this broker?
2. **Linux/Docker deploy fit (25%)** — must run alongside current efloud-bot stack on Hetzner.
3. **Python SDK quality + maintenance (15%)** — last release, GitHub activity, async support.
4. **Asset coverage (10%)** — major + minor FX pairs minimum; XAU/XAG bonus.
5. **Demo/sandbox parity (10%)** — can we mirror the testnet→mainnet gate pattern?
6. **Order types parity with current bot (5%)** — server-side SL + TP1 + TP2; trailing optional.

## Method

1. Read `exchange/__init__.py` and list the **interface surface** the adapter must implement
   (methods, return shapes, side effects).
2. For each candidate, check the SDK against this surface — is there a 1:1 mapping or do we
   need a translation layer?
3. Check the broker's order types: server-side STOP, server-side TAKE_PROFIT, OCO?
4. Check the broker's leverage/margin model vs. our ISOLATED expectation.
5. Identify the symbol naming rules (e.g., `EURUSD` vs `EUR/USD`).
6. Spike-cost estimate: hours to build adapter + tests for each candidate.

## Output

```
## Recommendation
<broker> — <one-paragraph why>

## Adapter interface (extracted from exchange/__init__.py)
- fetch_ohlcv(symbol, timeframe, limit) -> DataFrame
- create_order(symbol, side, type, qty, price=None, stop=None) -> dict
- ...

## Per-candidate gap analysis
### MetaTrader 5
- Pros: ...
- Cons: Windows runtime — need Wine container OR separate Win VPS.
- Spike estimate: <hours>
### OANDA v20
- ...

## Deploy implication
<does the chosen broker change docker-compose.prod.yml?>

## Open questions for Hermes/Utku
- TR/TH banka deneyimleri (hangi broker'da fund/withdraw sorunsuz?)
- Mainnet açma onay süreci farklı olacak mı?
```

## Hard rules
- This skill produces a **memo**, not code. No `/exchange/` edits.
- No spec'ing a custom broker adapter from scratch — pick from real candidates.
- Wine-based MT5-on-Linux setups must include a "what breaks at 3am" risk note.
- Recommendation must include a **rollback path** (keep BinanceClient working).
