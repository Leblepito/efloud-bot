# Gemini / Antigravity Hand-off Prompt — Kronos Advisory (Phases 6 & 7)

> Bu dosya, Antigravity (Gemini) IDE'sine **olduğu gibi yapıştırılacak** prompt'tur.
> Claude Code, planın güvenlik-kritik backend kısmını (Phase 0–5) zaten uyguladı
> (default-OFF, deploy yok). Aşağıdaki iki faz senin (Gemini) sorumluluğunda.

---

## PROMPT (copy from here ⤵)

You are working in the **efloud-bot** repository — a LIVE Binance USDT-M Futures (mainnet)
trading bot. A safety hardening pass has already landed in the working tree for the **Kronos
advisory layer** (time-series forecast + LLM synthesis → Telegram/DB commentary). Your job is
two well-isolated tasks: **Phase 6 (Binance-native data feed)** and **Phase 7 (frontend Kronos
card)**. Read `docs/superpowers/plans/2026-06-05-kronos-advisory-integration.md` first.

### NON-NEGOTIABLE CONSTRAINTS
1. **Advisory-only invariant:** nothing you add may feed trade, sizing, SL/TP, or the
   confluence gate. It is render/Telegram/DB output only.
2. **DO NOT MODIFY** the already-hardened safety wiring in `backend/bot_runner.py`:
   the `_init_kronos`, `_kronos_*`, `_run_kronos_analysis`, `_on_signal_readonly`,
   `_kronos_prewarm` methods; the dedicated executor / Semaphore / dedup / cooldown / cache /
   `synth_timeout_sec` / Telegram-relabel logic; the config-flag gates. You may add the **one
   small, explicitly-specified** block in Phase 6 — nothing else in that file.
3. **Default-OFF stays default-OFF.** Do not flip `kronos.enabled`. Do not change defaults.
4. **TDD:** write the test first, then the code. The full Kronos suite must stay **hermetic**
   (no real subprocess, no network) and green: `python -m pytest backend/tests/test_kronos_integration.py -q`.
5. **Subprocess isolation preserved:** the model runs in `external_repos/kronos-claude-skill/.venv`
   via the launcher; do not import torch into the bot process.
6. Provider/LLM is resolved via `engine.agents.llm.make_llm_client` — do not reintroduce a
   hard-wired `GeminiClient` anywhere.

---

### PHASE 6 — Binance-native data feed (replaces yfinance spot with the bot's perp klines)

**Problem:** today Kronos is fed yfinance `BTC-USD` (Coinbase **spot**), while the bot trades
Binance USDT **perpetuals**. This causes basis distortion (the forecast's `last_close` won't
match the bot's entry/SL/TP) and most alts (INJ/WIF/BONK/PEPE…) simply don't exist on yfinance
→ empty → permanent static fallback. The bot already fetches the exact perp klines it needs.

**Files & exact changes:**

1. **`external_repos/kronos-claude-skill/scripts/_predict.py`** — add an optional `--df-path`:
   - Parse args so an OPTIONAL `--df-path <parquet>` can appear after the 4 positional args
     (`TICKER period interval pred_len`). Keep backward compatibility (no `--df-path` → current
     yfinance path unchanged).
   - When `--df-path` is given: `history = pd.read_parquet(path)`; ensure columns are exactly
     `["open","high","low","close","volume"]` and `history.index.name = "timestamps"` (the model
     and `build_future_timestamps`/`format_output` rely on this). Skip the `fetch_ohlcv()`
     yfinance call entirely. Everything downstream (`load_predictor`, `predictor.predict`,
     `format_output`) stays identical, so **stdout format is unchanged** (the bot's regex parser
     in `engine/ai/kronos.py` must keep matching `**Last close:** / **Direction:** /
     **Confidence band:** NARROW|MODERATE|WIDE / **Forecast range:**`).

2. **`external_repos/kronos-claude-skill/scripts/run_kronos.py`** — pass `--df-path` through:
   - Accept the optional `--df-path <path>` arg and forward it to `_predict.py` in
     `run_prediction(...)`. (It currently forwards only the 4 positional args.)

3. **`engine/ai/kronos.py`** — extend `run_kronos_prediction`:
   ```python
   def run_kronos_prediction(symbol, period="1mo", interval="1h", pred_len=24, df=None):
   ```
   - When `df is not None` (a pandas OHLCV DataFrame): write it to a **temp parquet**
     (use `tempfile` + `df.to_parquet(...)`), normalize the index name to `"timestamps"`,
     keep only `open/high/low/close/volume`, and append `["--df-path", str(parquet_path)]` to
     `cmd`. Clean up the temp file in a `finally`. When `df is None`: behavior unchanged (yfinance).
   - The stdout parsing already in place is reused verbatim.

4. **`backend/bot_runner.py`** — ADD EXACTLY this inside `_run_kronos_analysis`, replacing only
   the single prediction call (`run_in_executor(self._kronos_executor, run_kronos_prediction, …)`).
   Fetch the perp df when `data_source == "binance"`; otherwise pass `df=None`. **Change nothing
   else in this method or file.**
   ```python
   # data_source: binance → feed the bot's own closed-bar perp klines (no basis
   # distortion, 100% symbol coverage); yfinance remains the fallback.
   df = None
   if str(cfg.get("data_source", "yfinance")).lower() == "binance" and self.client is not None:
       try:
           df = await loop.run_in_executor(
               self._kronos_executor,
               self.client.fetch_ohlcv,
               symbol, str(cfg.get("interval", "1h")), 500,
           )
       except Exception as e:
           log.warning(f"🔮 Kronos Binance fetch failed for {symbol}, falling back to yfinance: {e}")
           df = None
   kronos_data = await loop.run_in_executor(
       self._kronos_executor, run_kronos_prediction,
       symbol, str(cfg.get("period", "1mo")), str(cfg.get("interval", "1h")),
       int(cfg.get("pred_len", 12)), df,
   )
   ```
   > NOTE: `BinanceClient.fetch_ohlcv(symbol, timeframe, limit=500)` returns a DataFrame with
   > columns `[open,high,low,close,volume]` and a DatetimeIndex named `"timestamp"` (closed bars
   > only — C1 guard). Normalize `"timestamp"`→`"timestamps"` on the kronos.py side.

5. **Config:** flip the committed default to `data_source: binance` in BOTH `config.yaml` and
   `configs/config.phase2_1k.yaml` ONLY after the above works (still under `enabled: false`).

**Phase 6 acceptance criteria:**
- With `data_source: binance`, `_predict.py` reads the injected parquet and **never imports/uses
  yfinance**; `last_close` equals the last close of the fed perp df.
- Works for an alt with no Yahoo coverage (e.g. `INJUSDT`).
- stdout format byte-compatible with the existing parser (the existing parse tests still pass).
- `df=None` path identical to today.

**Phase 6 tests (hermetic — add to `backend/tests/test_kronos_integration.py`):**
- `test_run_kronos_prediction_binance_df_injection`: build a synthetic OHLCV df; monkeypatch
  `engine.ai.kronos.subprocess.run` to (a) assert `--df-path` is present in the `cmd`, (b) read
  the parquet back and assert schema/columns/index-name, (c) return a crafted stdout; assert the
  parsed dict. **No real subprocess, no torch, no network.**
- A `_predict.py`-level unit (run inside the sub-venv, or a pure-pandas helper extracted from it)
  asserting the parquet branch normalizes columns and skips yfinance.

---

### PHASE 7 — Frontend Kronos dashboard card

**Goal:** render the Kronos commentary + categorical band on the dashboard, clearly labeled as
advisory. Backend already exposes the data: `frontend/lib/api.ts` `Trade` type has
`kronos_comment?: string` and `kronos_confidence?: number` (verify they're present), and
`db.fetch_recent_trades` / `fetch_trades_since` already SELECT the columns.

**Files & changes:**
- New component (e.g. `frontend/components/KronosCard.tsx` or integrate into the existing trade
  card/console): when `trade.kronos_comment` is present, show the comment + a band/badge.
- **Labeling:** the card MUST visibly state it is **advisory / commentary-only** and did NOT gate
  the trade. Do NOT present `kronos_confidence` on the same 0–100 visual axis as the SMC
  confluence (avoid implying they're comparable). Prefer the categorical band if available.
- **Graceful absence:** when the fields are null/absent (prod is DB-less → they will often be
  null), the card renders nothing / a subtle "no advisory" state — never an error.
- Follow the existing dashboard's styling/design system (look at the current console UI).

**Phase 7 acceptance criteria:**
- Renders comment + band when present; hidden/empty when absent; no console errors either way.
- Never implies Kronos influenced the trade decision.

**Phase 7 test:** a component test rendering with and without `kronos_comment`.

---

### HOW TO VERIFY YOUR WORK
```bash
# backend (must stay hermetic + green):
python -m pytest backend/tests/test_kronos_integration.py -q
# frontend:
cd frontend && npm run test
```
Do not deploy. Do not flip `kronos.enabled`. When done, summarize exactly which files you changed
and paste the test output.

## (end of prompt ⤴)
