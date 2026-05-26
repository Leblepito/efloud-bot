# Strategy Auto-Optimizer Instruction Manual

This is an autonomous optimization workspace designed to have the AI agent perform self-directed research to find the best trading strategy parameters.

## Setup

To set up a new strategy optimization run, perform the following steps:

1. **Agree on a run tag**: Propose a tag based on today's date (e.g. `strategy-opt/may26`).
2. **Create the branch**: `git checkout -b strategy-opt/<tag>` from current master.
3. **Read the in-scope files**: Read the files inside `scripts/autoresearch/` for full context:
   - `prepare.py` — preloads historical OHLCV cached data. Do not modify.
   - `train.py` — contains the CONFIG dictionary and the backtest runner. **This is the file you modify.**
4. **Confirm data exists**: Check that `cache/ohlcv/` contains cached Parquet data shards for major trading pairs (like BTC/USDT, ETH/USDT, SOL/USDT).
5. **Initialize results.tsv**: Create `results.tsv` in `scripts/autoresearch/` with just the header row.

---

## Experimentation Loop

Launch each experiment simply as: `python scripts/autoresearch/train.py` (ensure `PYTHONPATH` is set to `.`).

**What you CAN do:**
- Modify `scripts/autoresearch/train.py` CONFIG parameters. Everything in the CONFIG is fair game: swing lookbacks, orderblock boundaries, Fibonacci OTE entry zones, risk-reward ratios, minimum confluence levels, ADX filters, leverage, etc.
- You may also adapt the pricing rules or customize indicator weights directly inside the file or the underlying confluence calculations if you have a strong hypothesis.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only.
- Install new external python packages.

**Simplicity & Overfitting Criterion:**
- **Sharpe Ratio is King**: Your primary target is to maximize `sharpe_ratio` while maximizing `net_profit_pct`.
- **Drawdown Protection**: You must discard any configuration that results in a `max_drawdown_pct` higher than `10.0%` (risk breaker threshold).
- **Simplicity**: If a change yields a very tiny gain but introduces complex/ugly overrides, discard it. Simpler configurations that yield equal or better metrics are preferred.
- **Overfitting Warning**: Do not customize parameters down to ridiculous decimals (e.g., setting a threshold to `53.2173`) as this overfits to the last 90 days. Keep values realistic.

---

## Output format

When the script finishes, it prints a summary matching:
```
---
net_profit_pct:    12.450000
sharpe_ratio:      1.750000
max_drawdown_pct:  4.200000
total_trades:      85
profit_factor:     2.100000
total_seconds:     15.42
```

You can extract the metrics using grep:
```powershell
Select-String -Path scripts/autoresearch/run.log -Pattern "^net_profit_pct:|^sharpe_ratio:|^max_drawdown_pct:"
```

---

## Logging results

When an experiment finishes, log it to `scripts/autoresearch/results.tsv` (tab-separated columns).

The TSV has a header row:
```
commit	sharpe_ratio	net_profit_pct	max_drawdown	status	description
```

1. git commit hash (short, 7 chars)
2. `sharpe_ratio` achieved
3. `net_profit_pct` achieved
4. `max_drawdown_pct` reached
5. status: `keep`, `discard`, or `crash`
6. short text description of the hypothesis/parameters changed

Example:
```
commit	sharpe_ratio	net_profit_pct	max_drawdown	status	description
a1b2c3d	1.25	8.42	4.50	keep	baseline config
b2c3d4e	1.45	12.10	4.20	keep	lowered min_confluence to 45
c3d4e5f	1.10	6.20	5.10	discard	increased swing_lookback to 10
d4e5f6g	0.00	0.00	0.00	crash	invalid timeframe setting
```

---

## The Experiment Loop

LOOP FOREVER:

1. Tune `scripts/autoresearch/train.py` with an experimental idea (e.g. increase min_rr, relax confluence, enable ADX filter).
2. git commit your change: `git commit -am "opt: try [x]"`
3. Run the experiment: `python scripts/autoresearch/train.py > scripts/autoresearch/run.log 2>&1`
4. Read the results: `grep "^sharpe_ratio:\|^net_profit_pct:\|^max_drawdown_pct:" scripts/autoresearch/run.log`
5. If the output is empty, it crashed. Log `crash` in `results.tsv`, review the log, fix the typo, and run again.
6. Record the result in `results.tsv` (keep `results.tsv` untracked by git).
7. If metrics improved (higher Sharpe/profit, acceptable drawdown), keep the commit and advance.
8. If metrics are worse, reset back to the last known kept commit: `git reset --hard HEAD~1` (or to the last kept commit hash).

## NEVER STOP
Do NOT pause to ask the human if you should continue. The loop runs indefinitely until the user manually stops you. Optimize, evaluate, learn, and repeat!
