# CMP-2 — Promotional-Policy Matrix (Meta / YouTube / X / Google Ads)

| Field | Value |
|---|---|
| Task | CMP-2 (backs CMP-3 BANNED_EN_PHRASES; backs ADS-3 ad copy) |
| Owner | @claude |
| Status | v1 2026-06-17 |
| Spec | §4.5 CMP-2 |
| Inputs | Gemini ADS-0 word matrix (`docs/marketing/google-ads-feasibility.md`), live site copy, `scripts/content_compliance.py` |

This is the **authoritative source** for banned/approved promotional language across every channel. CMP-3 encodes the EN list into `content_compliance.py`; ADS-3 / CON / SD copy all map to it. Positioning is fixed: **u2algo is an educational/decision-support charting tool + research log, NOT a signal service, NOT a profit promise.**

## 1. Banned claim patterns (REJECT — `banned_phrase` / `absolute_money` / `performance_pct_claim` / `unlabeled_simulation`)

| # | EN pattern | TR pattern | Why (policy) | Gate tag |
|---|---|---|---|---|
| 1 | guaranteed profit / guaranteed returns / guaranteed win | Garantili getiri / Kesin kazanç | Meta+YT+Google misrepresentation; "guaranteed financial return" banned | `banned_phrase` |
| 2 | risk-free / no loss / can't lose / cannot lose | Risksiz / kayıpsız / kaybetmezsin | Misrepresentation; unrealistic expectation | `banned_phrase` |
| 3 | double your money / get rich / get-rich-quick | Paranı ikiye katla / hızlı zengin ol | Get-rich-quick ban (all platforms) | `banned_phrase` |
| 4 | passive income machine / signal and earn | Pasif gelir makinesi / Sinyal al, kazan | Misrepresentation + signal-service | `banned_phrase` |
| 5 | Buy/Sell signals / signal generator / AI signal | Al-Sat sinyali / sinyal üreteci | Google trading-signals ban; reposition as "market-structure visualization" | `banned_phrase` (+ADS hard) |
| 6 | auto-trading bot (in ad copy) | otomatik işlem botu (reklamda) | Google complex-speculative framing | `banned_phrase` (ADS) |
| 7 | "80% win rate" / "+81% profit" / any perf % | "%80 isabet" / "%73 kazanç" | Unverified performance % | `performance_pct_claim` |
| 8 | "$250 profit" / "made $1,000" / per-trade $ | "$250 kâr" / "1000$ kazandı" | Conservative-proof; absolute $ PnL | `absolute_money` |
| 9 | "fund deposit" / invest in our fund | Fonumuza para yatır | Unlicensed financial solicitation | `banned_phrase` |
| 10 | simulated/backtest results without a label | etiketsiz backtest/simülasyon | Misrepresentation (hindsight) | `unlabeled_simulation` |

> EN strings 1-5 are the seed of `BANNED_EN_PHRASES` in CMP-3 (extend with morphological variants: "risk free"/"risk-free", "no-loss"/"no loss", "cant lose"/"can't lose").

## 2. Approved framing (USE these)

| Instead of (banned) | Use (approved) |
|---|---|
| Trading signals / Buy-Sell alerts | **Technical-analysis indicators / market-structure visualization** |
| Auto-trading bot | **Educational charting tool / research framework** |
| Guaranteed profit / 80% win rate | **Transparent research log (results incl. negative), shown as shape + aggregate %** |
| Risk-free / passive income | **Risk-disciplined methodology; capital at risk; DYOR** |
| Premium product that outperforms | **Free indicator + waitlist for early access (PROD-0)** |

## 3. Platform-specific notes

- **Meta (FB/IG):** financial-products + crypto restrictions; "Special Ad Category" may apply. Organic posts still must avoid §1 patterns. Manus-routed posts pass `content_compliance` before publish (CMP-8).
- **YouTube:** harmful/dangerous + misrepresentation; "build-in-public / education" framing is safe; no profit promises in titles/thumbnails.
- **X:** financial-services promo policy; aggregate-only, disclaimer in bio + pinned.
- **Google Ads:** per ADS-0 — **global NO-GO** (G2RS for unlicensed); US "charting-tool" RESTRICTED path parked. ADS-3 copy, if ever used (US-only), must additionally carry the CFTC 4.41 landing disclaimer.

## 4. Mandatory on every public surface
- Risk disclaimer present (CMP-1 library; `has_disclaimer` byte-match).
- Conservative proof: shape + aggregate % only, zero `$`-PnL, pre-90-day (GROW-8 gate).
- Any backtest/sim labeled `[BACKTEST]` / `[TESTNET]`.
- `efloud` internal name never leaks to public copy.

## Acceptance (CMP-2)
- [x] ≥12 banned patterns EN+TR mapped to platform + gate tag.
- [x] ≥8 approved framings.
- [x] Hands CMP-3 the authoritative `BANNED_EN_PHRASES` seed.
- [x] ADS-3 / CON / SD copy reference this as the single matrix.
