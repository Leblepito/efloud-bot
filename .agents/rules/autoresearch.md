# Strategy Auto-Optimizer Agent Steering Rules

This project has an autonomous trading strategy backtest optimizer located in `scripts/autoresearch/`.

When the user types `/optimize` or requests strategy optimization:
1. Propose a branch name (e.g. `strategy-opt/may26`) and checkout: `git checkout -b strategy-opt/<tag>`
2. Read the instructions in `scripts/autoresearch/program.md` completely.
3. Establish the baseline by running:
   ```powershell
   $env:PYTHONPATH="."
   python scripts/autoresearch/train.py
   ```
4. Record baseline results in `scripts/autoresearch/results.tsv` under the status `keep`.
5. Enter the infinite autonomous loop:
   - Formulate a strategy hypothesis (e.g., tweaking Fibonacci ratios, confluence score limits, lookbacks, ATR margins).
   - Edit the CONFIG dictionary in `scripts/autoresearch/train.py`.
   - Stage and commit the change.
   - Run `python scripts/autoresearch/train.py > scripts/autoresearch/run.log 2>&1`.
   - Extract metrics using regex.
   - Log to `results.tsv`.
   - If Sharpe ratio or profit improved and max drawdown is within acceptable limits, keep the commit.
   - If metrics deteriorated, reset back to the last known kept commit.
   - Loop forever without stopping or asking the user for permission.
