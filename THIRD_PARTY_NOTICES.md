# Third-party notices

## HyperGrok Trading Desk (MIT)

Parts of the efloud-desk plugin are adapted from
[HyperGrok Trading Desk](https://github.com/galleonlabs/hypergrok-trading-desk) by
[Andrew Wilkinson](https://andrewwilkinson.io) and [Galleon Labs](https://github.com/galleonlabs),
used under the MIT license:

- `hooks/live_write_gate.py`, `hooks/live-write-gate.json` — adapted from
  `hooks/exchange_write_gate.py` / `hooks/exchange-write-gate.json` (Hyperliquid
  patterns replaced with Binance/ccxt, efloud bot API and deploy patterns; only
  executed scripts are inspected).
- `skills/desk-operating-model/SKILL.md` — adapted from `skills/desk-operating-model`
  (rewritten for an autonomous engine: the desk works around the engine, never in its
  order path).
- `agents/*.md` — role structure (single writer, Risk PASS, ticket approval by id,
  evidence standard, handoff format) adapted from `agents/*.md`; content rewritten
  for efloud-bot.

This is not HyperGrok and is not endorsed by its authors.

```
MIT License

Copyright (c) 2026 Galleon Labs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## day-trader-skill (MIT)

`scripts/desk/plan_replay.py` and `skills/plan-replay/SKILL.md` are adapted from
`trader-timemachine` in [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)
by Jake Schincariol (reviewed at `3d0f4ef`), used under the MIT license. Changes:
Binance USDT-M bars, UTC time-of-day slots instead of NYSE sessions, horizon in bars,
long and short plans, fees folded into R. The other ten skills target US equities and
were not imported.

```
MIT License

Copyright (c) 2026 Jake Schincariol

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Referenced, not vendored

- [TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache-2.0, Tauric
  Research) — installed only into an isolated research venv from
  `requirements-research.txt` (pinned `c454491`) and called by
  `scripts/desk/tradingagents_brief.py`. No TradingAgents code is copied into this repo.
- [tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp) (MIT, tradesdontlie)
  — installed by the operator on the desktop per `skills/tradingview-mcp/SKILL.md`
  (pinned `c05b8f5`). No code is copied into this repo.

## LuxAlgo — Smart Money Concepts (CC BY-NC-SA 4.0)

`engine/smc_v2/luxalgo.py` ports the logic of the TradingView script
"Smart Money Concepts (SMC) [LuxAlgo]" (`CnB3fSph`), published by LuxAlgo under
Creative Commons Attribution-NonCommercial-ShareAlike 4.0
(https://creativecommons.org/licenses/by-nc-sa/4.0/). The non-commercial and
share-alike terms apply to that logic; see `skills/luxalgo-smc/SKILL.md` for the
open licensing decision.

`pine/lab/core.pine` (and the generated `pine/efloud_lab.pine`, `pine/efloud_lab_strategy.pine`)
carry the same ported logic in Pine Script and the same licence terms; these lab scripts are
kept private / invite-only on TradingView and are not distributed commercially.
