# CCXT defaultType "futures" → "future" Normalization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop CCXT from silently routing `fetch_open_orders()` to the SPOT endpoint, so reconcile can actually see the bot's STOP_MARKET / TAKE_PROFIT_MARKET orders on Binance USD-M futures.

**Architecture:** Single-line normalization inside `BinanceClient.__init__`. `self.market_type = "futures"` (the bot's internal name, used in 40+ comparisons across the codebase) is preserved unchanged. Only the string forwarded to CCXT's `options.defaultType` is converted to the canonical CCXT value `"future"` (singular). No config files, no callers, no tests of internal `== "futures"` comparisons need to change.

**Tech Stack:** Python 3.12, ccxt 4.5.40 (`ccxt.binance`), pytest, unittest.mock.

---

## Background — why this is a one-line fix

CCXT 4.5.40 binance.py only recognizes these `defaultType` values: `'spot' | 'future' | 'margin' | 'delivery' | 'option'` (binance.py:1356 in the installed package). The bot was passing `"futures"` (plural). Inside `fetch_open_orders()` (binance.py:6904-6989) the routing is:

```python
defaultType = self.safe_string_2(self.options, 'fetchOpenOrders', 'defaultType', 'spot')
type = self.safe_string(params, 'type', defaultType)   # type = 'futures'
...
elif self.is_linear(type, subType):     # is_linear strict-compares type=='future' or 'swap' → False
    response = self.fapiPrivateGetOpenOrders(...)
elif self.is_inverse(type, subType):    # type=='delivery' → False
    response = self.dapiPrivateGetOpenOrders(...)
elif type == 'margin' or marginMode is not None:
    response = self.sapiGetMarginOpenOrders(...)
else:
    response = self.privateGetOpenOrders(...)   # ← FALLS THROUGH HERE: spot /api/v3/openOrders
```

Empirically verified locally (no auth needed, `ex.fetch = lambda url, *a, **k: capture(url)`):

| `defaultType` | URL hit |
|---|---|
| `"futures"` (production typo) | `https://api.binance.com/api/v3/openOrders` (spot) |
| `"future"` (canonical)        | `https://fapi.binance.com/fapi/v1/openOrders` (futures) |

This is the entire root cause of the 2026-05-08 stacking incident: spot account has no orders → `[]` → `OrderManager.reconcile` declares every TP1 filled.

Internal `self.market_type == "futures"` comparisons (e.g. `exchange/__init__.py:70,87,107,127,155`, `engine/permissions/__init__.py:93,99`, `engine/universe.py:132`) and YAML configs (`market_type: futures`) are kept as-is. The bot's own ontology stays consistent; only the CCXT-bound string is normalized.

---

## File Structure

| File | Responsibility | Change kind |
|---|---|---|
| [exchange/__init__.py](../../exchange/__init__.py) | `BinanceClient.__init__` builds the CCXT options dict | Modify (3 lines) |
| [backend/tests/test_binance_client_default_type.py](../../backend/tests/test_binance_client_default_type.py) | Unit test: BinanceClient configures CCXT with canonical singular value | Create |
| [backend/tests/test_binance_client_url_routing.py](../../backend/tests/test_binance_client_url_routing.py) | Regression test: `fetch_open_orders()` URL goes to fapi, not spot | Create |

Both new tests live under `backend/tests/` to match the existing test layout (the bot's pytest discovery walks that directory).

---

## Chunk 1: Single-line normalization + unit test

### Task 1: Add normalization in BinanceClient + unit test

**Files:**
- Modify: [exchange/__init__.py:30-48](../../exchange/__init__.py#L30-L48)
- Create: [backend/tests/test_binance_client_default_type.py](../../backend/tests/test_binance_client_default_type.py)

- [ ] **Step 1: Write the failing unit test**

Create `backend/tests/test_binance_client_default_type.py`:

```python
"""BinanceClient must hand CCXT the canonical singular defaultType string.

CCXT 4.5.40 binance.py only recognizes 'spot|future|margin|delivery|option'
for options.defaultType. Passing 'futures' (plural — the bot's internal name)
silently routes fetch_open_orders to the spot endpoint, which is the 2026-05-08
reconcile-blindspot bug.
"""
import pytest
from unittest.mock import patch, MagicMock

from exchange import BinanceClient


def _make_client(market_type: str) -> BinanceClient:
    """Construct a BinanceClient without making network calls."""
    with patch("exchange.ccxt.binance") as mock_ctor:
        mock_ctor.return_value = MagicMock()
        mock_ctor.return_value.options = {}
        client = BinanceClient(
            api_key="k", api_secret="s",
            testnet=False, market_type=market_type,
        )
        # Capture the opts dict that was passed to ccxt.binance(...)
        client._captured_opts = mock_ctor.call_args.args[0] if mock_ctor.call_args.args else mock_ctor.call_args.kwargs
        return client


def test_market_type_futures_passes_singular_to_ccxt():
    """market_type='futures' (bot internal name) → CCXT receives 'future' (singular)."""
    client = _make_client(market_type="futures")
    opts = client._captured_opts
    assert opts["options"]["defaultType"] == "future", (
        f"Expected 'future' (singular CCXT canonical) but got "
        f"{opts['options']['defaultType']!r}. Bug: 'futures' routes to spot endpoint."
    )


def test_internal_market_type_unchanged():
    """self.market_type keeps the bot's internal 'futures' label so existing
    `client.market_type == "futures"` comparisons (40+ sites) keep working."""
    client = _make_client(market_type="futures")
    assert client.market_type == "futures"


def test_market_type_spot_passes_through():
    """Non-futures market_type values are passed to CCXT unchanged."""
    client = _make_client(market_type="spot")
    opts = client._captured_opts
    assert opts["options"]["defaultType"] == "spot"
    assert client.market_type == "spot"
```

- [ ] **Step 2: Run test, confirm it fails**

```
pytest backend/tests/test_binance_client_default_type.py -v
```

Expected: `test_market_type_futures_passes_singular_to_ccxt` FAILS with assertion `'futures' != 'future'`. Other two PASS.

- [ ] **Step 3: Apply the minimal fix**

Edit [exchange/__init__.py:30-48](../../exchange/__init__.py#L30-L48). Replace the existing `__init__` body up to and including the CCXT instantiation with:

```python
    def __init__(self, api_key: str = "", api_secret: str = "",
                 testnet: bool = True, market_type: str = "futures"):
        # CCXT 4.x binance only accepts 'spot|future|margin|delivery|option' for
        # options.defaultType. The bot uses 'futures' (plural) as its own internal
        # market_type label (40+ `== "futures"` comparisons across the codebase),
        # so we normalize here for CCXT and leave self.market_type unchanged.
        # Without this normalization, fetch_open_orders silently falls through
        # is_linear/is_inverse and routes to /api/v3/openOrders (spot) — see the
        # 2026-05-08 reconcile-blindspot incident.
        ccxt_default_type = "future" if market_type == "futures" else market_type
        opts = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": ccxt_default_type},
        }
        if testnet:
            opts["sandbox"] = True

        self.exchange = ccxt.binance(opts)
        self.exchange.options["warnOnFetchOpenOrdersWithoutSymbol"] = False
        self.market_type = market_type
        self.testnet = testnet
        log.info(f"Binance {'testnet' if testnet else 'MAINNET'} | {market_type}")
```

- [ ] **Step 4: Run test, confirm it passes**

```
pytest backend/tests/test_binance_client_default_type.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```
git add exchange/__init__.py backend/tests/test_binance_client_default_type.py
git commit -m "fix(exchange): normalize CCXT defaultType to 'future' for USD-M futures

CCXT 4.5.40 only accepts 'spot|future|margin|delivery|option' as defaultType.
The bot's internal 'futures' (plural) silently routed fetch_open_orders to the
spot endpoint /api/v3/openOrders, which is empty — reconcile then declared
every TP1 filled. Normalize the value passed to CCXT while preserving the
40+ internal '== \"futures\"' comparisons.

Root cause of the 2026-05-08 reconcile-blindspot stacking incident."
```

---

## Chunk 2: URL routing regression test

This test is not strictly necessary for the fix, but it pins the routing behavior so a future refactor (e.g. someone changing `market_type` defaults again) won't silently regress to spot.

### Task 2: Lock the URL with a routing regression test

**Files:**
- Create: [backend/tests/test_binance_client_url_routing.py](../../backend/tests/test_binance_client_url_routing.py)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_binance_client_url_routing.py`:

```python
"""Regression: BinanceClient(market_type='futures') must produce a CCXT
exchange whose fetch_open_orders() hits fapi.binance.com (futures), not
api.binance.com (spot). Tests by intercepting the HTTP call before it
goes out — no live exchange, no auth, no markets reload over the network.
"""
import ccxt
import pytest

from exchange import BinanceClient


@pytest.fixture(scope="module")
def shared_markets():
    """Load Binance markets once on a public client; share across tests."""
    boot = ccxt.binance({"options": {"defaultType": "spot"}})
    boot.load_markets()
    return boot


def _capture_fetch_open_orders_url(client: BinanceClient, symbol=None) -> str:
    """Run fetch_open_orders against the BinanceClient's exchange and return the
    URL CCXT was about to hit. Network is intercepted before any real call."""
    ex = client.exchange
    captured = []

    def fake_fetch(url, *a, **kw):
        captured.append(url)
        raise RuntimeError("intercepted")

    ex.fetch = fake_fetch
    try:
        if symbol:
            ex.fetch_open_orders(symbol)
        else:
            ex.fetch_open_orders()
    except RuntimeError as e:
        if "intercepted" not in str(e):
            raise
    return captured[-1] if captured else ""


def _client_with_markets(market_type: str, shared_markets) -> BinanceClient:
    client = BinanceClient(
        api_key="dummy", api_secret="dummy",
        testnet=False, market_type=market_type,
    )
    # Inject pre-loaded markets so load_markets() does not hit the network
    client.exchange.markets = shared_markets.markets
    client.exchange.markets_by_id = shared_markets.markets_by_id
    client.exchange.symbols = shared_markets.symbols
    client.exchange.ids = shared_markets.ids
    return client


def test_futures_client_routes_no_symbol_to_fapi(shared_markets):
    client = _client_with_markets("futures", shared_markets)
    url = _capture_fetch_open_orders_url(client)
    assert "fapi.binance.com/fapi/v1/openOrders" in url, (
        f"Expected futures URL but got: {url}\n"
        "Regression: defaultType normalization broken — routing to spot."
    )
    assert "/api/v3/openOrders" not in url


def test_futures_client_routes_with_slash_symbol_to_fapi(shared_markets):
    """Even with bot's slash-only symbol form, routing must go to fapi.

    With buggy defaultType='futures', symbol='FIL/USDT' (slash-only) loads as
    spot market and hits /api/v3/openOrders. The fix forces fapi via the
    canonical 'future' string."""
    client = _client_with_markets("futures", shared_markets)
    url = _capture_fetch_open_orders_url(client, symbol="FIL/USDT:USDT")
    assert "fapi.binance.com/fapi/v1/openOrders" in url
    assert "symbol=FILUSDT" in url
```

- [ ] **Step 2: Run the routing test against the patched client**

```
pytest backend/tests/test_binance_client_url_routing.py -v
```

Expected: both tests PASS (because Task 1 already applied the fix). If a future regression sets `defaultType` back to `"futures"` plural, these tests will catch it.

- [ ] **Step 3: Run the full test suite (sanity)**

```
pytest backend/tests/ -x -q
```

Expected: 0 failures. Existing tests using `client.market_type == "futures"` keep passing because `self.market_type` was preserved.

- [ ] **Step 4: Commit**

```
git add backend/tests/test_binance_client_url_routing.py
git commit -m "test(exchange): pin fetch_open_orders URL to fapi for futures clients

Regression guard: if a future change sets options.defaultType back to a
non-canonical value (e.g. 'futures'), CCXT silently falls through is_linear
to the spot endpoint. This test intercepts the HTTP call before the network
and asserts the URL host is fapi.binance.com — catching the regression
without needing live exchange access."
```

---

## Chunk 3: PR + deploy + post-deploy verification

### Task 3: Open PR + deploy

**Files:** none (git/PR/deploy operations only)

- [ ] **Step 1: Push branch**

Branch name: `fix/ccxt-default-type-future-singular`

```
git push -u origin fix/ccxt-default-type-future-singular
```

- [ ] **Step 2: Open PR via gh**

```
gh pr create --title "fix(exchange): normalize CCXT defaultType to 'future' (singular)" --body "$(cat <<'EOF'
## Summary
- CCXT 4.5.40 binance only accepts `spot|future|margin|delivery|option` for `options.defaultType`. The bot was passing `'futures'` (plural — its own internal name) which silently routes `fetch_open_orders()` to the spot endpoint `/api/v3/openOrders`.
- Spot account has no orders → reconcile saw `[]` → declared every TP1 filled → 2026-05-08 stacking incident.
- Fix: normalize `'futures'` → `'future'` for CCXT only; keep `self.market_type = 'futures'` so the 40+ internal `== "futures"` comparisons stay correct.

## Test plan
- [x] Unit test: `BinanceClient(market_type='futures')` produces a CCXT exchange with `options.defaultType == 'future'`.
- [x] URL routing regression test: `fetch_open_orders()` hits `fapi.binance.com/fapi/v1/openOrders`, not `api.binance.com/api/v3/openOrders`.
- [x] Full backend test suite passes (`pytest backend/tests/`).
- [ ] Post-deploy: SSH to prod, run a read-only Python snippet that captures the URL hit by `fetch_open_orders()` against the live `BinanceClient` — confirm `fapi.binance.com`. Wallet currently 0 positions / 0 orders, so an empty list is expected; the URL inspection is the actual verification.
- [ ] Post-deploy: start the bot, watch first cycle. When the first position opens, dashboard "Open Orders" tab should show 3 orders (SL + TP1 + TP2). With the bug, it showed 0.

## Notes
- Bot is currently STOPPED so deploy is risk-free w.r.t. interrupting trading.
- This unblocks restart. Other pending bugs (`_processed_signals` persistence, TZ tolerance) are tracked in separate plans/PRs.
EOF
)"
```

- [ ] **Step 3: Wait for review approval, then merge**

User reviews. After approval:

```
gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Deploy to Hetzner**

```
ssh efloud@178.104.122.91 'cd /opt/efloud-bot && git pull && bash deploy/deploy.sh'
```

- [ ] **Step 5: Post-deploy URL verification (read-only — no positions opened)**

SSH command (one-liner; runs inside the bot container so it uses the deployed code path):

```
ssh efloud@178.104.122.91 'cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml exec -T efloud-bot python -c "
import yaml, os
from exchange import BinanceClient
cfg = yaml.safe_load(open(os.environ[\"EFLOUD_CONFIG_PATH\"]))
ex_cfg = cfg[\"exchange\"]
client = BinanceClient(
    api_key=os.environ[\"BINANCE_API_KEY\"], api_secret=os.environ[\"BINANCE_API_SECRET\"],
    testnet=ex_cfg[\"testnet\"], market_type=ex_cfg[\"market_type\"],
)
print(\"defaultType in CCXT:\", client.exchange.options[\"defaultType\"])
captured = []
orig = client.exchange.fetch
def fake(url, *a, **k):
    captured.append(url); raise RuntimeError(\"stop\")
client.exchange.fetch = fake
try:
    client.exchange.fetch_open_orders()
except RuntimeError:
    pass
client.exchange.fetch = orig
print(\"URL hit:\", captured[0] if captured else \"NONE\")
"'
```

Expected output:

```
defaultType in CCXT: future
URL hit: https://fapi.binance.com/fapi/v1/openOrders?...
```

- [ ] **Step 6: Update memory**

Edit [efloud_state.md](../../../../.claude/projects/c--Users-utkuc-Downloads-efloud-bot/memory/efloud_state.md):
- Move section "1. CCXT/Binance conditional-orders blindspot" to a "Resolved" section with PR # and verification result.
- Update the top-of-file "Status" line to remove the "DO NOT RESTART BOT" warning if the post-deploy URL check passed.

(MEMORY.md and binance_ccxt_conditional_orders.md were already updated during the diagnosis session — no change needed there.)
