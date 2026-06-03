# Console Modifications — Opinionated Code Review (gstack EM / QA / Reviewer)

> Scope: every frontend + backend change shipped in Phases 1–4 of the Efloud
> console upgrade. Reviewed in the spirit of the gstack EM / QA-Lead / Reviewer
> role playbooks. (I could not `gh repo clone garrytan/gstack` from my
> environment — run that locally; this is the same review the playbooks drive.)
>
> Verification baseline reported by the operator: `npm run build` → 0 errors;
> `pytest backend/tests tests` → **1268 passed, 6 skipped, 0 failures**; safety
> suites (MainnetGuard / CircuitBreaker / PositionGuard) untouched & green.

---

## 1. Engineering Manager — scope, risk, blast radius

| Dimension | Assessment |
|---|---|
| **Change type** | Additive. New module + new route + new test + new hook; existing components restyled (no logic removed). No trading-path or safety code touched — corroborated by 1268/1268 green. |
| **Blast radius** | Low. The only runtime addition to the hot path is one auth-guarded read endpoint and one SWR poll. Everything else is presentational. |
| **Rollback** | Trivial & independent per phase: flip `showSMC` default to `false`, or drop the `/api/signals/smc` route — overlay vanishes, nothing else regresses. |
| **Operational risk** | **MEDIUM** — see QA finding Q1 (duplicate Binance kline load). Worth confirming before high-traffic demo on `bot.ualgotrade.com`. |
| **Verdict** | **Ship.** Conditioned on acknowledging Q1 and R2 as fast-follows. |

---

## 2. QA Lead — coverage, edge cases, failure modes

- **Q1 (MEDIUM) — Duplicate Binance load.** `InteractiveChart` already fetches
  `/fapi/v1/klines` directly in the browser; the new backend `/api/signals/smc`
  fetches the *same* klines server-side. Under many concurrent viewers this
  doubles Binance request volume and risks `418/429`. *Fix:* cache the SMC
  response server-side per `(symbol,timeframe)` for ~15–30s, or compute SMC from
  the klines the client already has and POST them up. Today's mitigation: SWR
  `refreshInterval: 30000` keeps it modest.
- **Q2 (LOW) — Route/engine paths untested.** `test_signals_smc.py` covers the
  pure heuristic well (shape, empty-guard, FVG, equilibrium, structure). The
  `get_smc_signal` network branch and `_engine_smc` bridge are **not** covered.
  *Fix:* add a test that monkeypatches `httpx.AsyncClient.get` and one that feeds
  a fake `runner.orch.smc_telemetry` to assert `source == "engine"`.
- **Q3 (LOW) — Overlay toggle has no component test.** No RTL/Playwright asserts
  that toggling **SMC Overlay** attaches/detaches the primitive. Manual visual QA
  done; automate before this surface grows.
- **Failure modes — PASS.** klines fetch wrapped → `source:"unavailable"` empty
  payload (never 500); engine bridge swallows shape drift; frontend falls back to
  client `computeSMC` while `serverSmc` is `undefined`/empty. Good defensive depth.
- **Responsiveness — PASS.** Verified in the HTML reference at 1320 / 1100 / 640
  breakpoints: status grid 4→2→1, grids collapse, tables fit without scrollbars.

---

## 3. Reviewer — line-level correctness & craft

- **R1 (LOW, perf) — O(n²) FVG mitigation.** Both `smcOverlay.ts` and
  `signals_smc.py` test mitigation via `candles.slice(i+2).some(...)` per FVG
  candidate → ~O(n²) on 500 bars. Fine at current sizes; for larger windows do a
  single forward pass tracking the running min-low / max-high after each gap.
- **R2 (LOW) — Magic constants.** `swing_lookback=5`, `range_bars=90`, `max_fvg=6`
  are hard-coded. Promote `swing_lookback` / `range_bars` to query params on
  `/api/signals/smc` so the engine and chart can agree on sensitivity per timeframe.
- **R3 (LOW) — Primitive z-order.** `SmcOverlayPrimitive` attaches in effect `8b`,
  after the `PositionOverlayPrimitive` (effect `8`). Zones use ≤0.10 alpha so the
  entry/SL/TP lines stay readable — verify visually once on a symbol with an open
  position; if zones ever feel heavy, drop OB/FVG alpha to 0.07.
- **R4 (PASS) — Time-base alignment (the subtle one).** Backend emits
  `time = openTime // 1000` (UNIX **seconds**); the chart's candles use
  `Math.floor(d[0]/1000)`. They match, so `timeToCoordinate` resolves overlay X
  correctly. ✅ This is the bug class that usually bites lightweight-charts overlays.
- **R5 (PASS) — Types.** `SmcSignal extends SmcData`; server payload feeds
  `new SmcOverlayPrimitive(serverSmc)` with no cast. `range:null` guarded in the
  renderer. No `any` leaks beyond the existing chart-primitive boundary.
- **R6 (PASS) — Motion/a11y.** `.dot-breathe` / `.ws-beat` gated behind
  `prefers-reduced-motion: no-preference`; base states are visible (no content
  hidden behind a frozen animation). Custom `--ek-*` easings throughout; no
  `transition: all`.

---

## 4. Consolidated punch list (fast-follows, none blocking)

1. Cache `/api/signals/smc` per `(symbol,timeframe)` ~15–30s **(Q1, MEDIUM)**.
2. Add route + engine-bridge tests (httpx monkeypatch; fake `smc_telemetry`) **(Q2)**.
3. Expose `swing_lookback` / `range_bars` as query params **(R2)**.
4. Single-pass FVG mitigation if window grows **(R1)**.
5. RTL/Playwright test for the SMC toggle **(Q3)**.

**Overall verdict: APPROVE for merge.** Additive, well-guarded, safety suite
untouched, type-safe, on-palette. Address Q1 before a high-traffic public demo.
