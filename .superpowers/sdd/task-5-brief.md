# Task Brief: Task 5

## Task 5: Reduce Default check_interval_sec in config.yaml

**Files:**
- Modify: `config.yaml` — `check_interval_sec` value
- Test: N/A (config change, verification via smoke test)

**Interfaces:**
- Consumes: None
- Produces: Config file change

**Description:** Reduce default check_interval_sec from 30 to 10 seconds for faster close detection while candle-close sync prevents excessive API calls.

- [ ] **Step 1: Edit config.yaml**

Locate `check_interval_sec` and change from `30` to `10`:
```yaml
runner:
  check_interval_sec: 10  # Reduced from 30 for faster close detection
```

- [ ] **Step 2: Verify config loads**

Run: `python -c "from engine.config import load_config; cfg = load_config('configs/config.testnet.yaml'); print(f'check_interval_sec: {cfg.runner.check_interval_sec}')"`

Expected output: `check_interval_sec: 10`

- [ ] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "config: reduce default check_interval_sec to 10s"
```
