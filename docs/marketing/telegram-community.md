# SD-5 — Telegram Community Playbook (u2algo Customer Channel)

| Field | Value |
|---|---|
| Task | SD-5 (gates SD-6 YouTube, CON-8 video compliance) |
| Owner | @hermes |
| Status | v1 2026-06-17 |
| Spec | §4.8 SD-5 |

## 1. Channel identity

- **Bot handle**: separate Telegram bot from the operator alerter (`EFLOUD_TELEGRAM_TOKEN` / `EFLOUD_TELEGRAM_CHAT_ID`). SD-5 uses `EFLOUD_CUSTOMER_TG_TOKEN` + `EFLOUD_CUSTOMER_TG_CHANNEL_ID` — **two structurally isolated channels**.
- **Channel purpose**: public, opt-in follower channel for users following the u2algo educational/decision-support tool. NOT a signal service, NOT a trading-call channel.
- **Posting cadence**: 1 post / day, scheduled (cron). Manual override allowed for incident notes (operator-only).
- **Channel language**: EN-first. Bilingual or TR posts may appear only if a pinned welcome message explicitly labels them as TR-derivative.

## 2. Pinned welcome message (EN, post once on channel create)

```
📌 Welcome to u2algo — the open-source SMC research log.

This channel posts a single daily snapshot: how many trades closed,
how many won, net P/L in %, and a one-line disclaimer. That is all.

🛡 Hard rules of this channel:
1. **No signals.** Entry, stop, and targets are never posted.
2. **No PnL amounts.** Only %.
3. **Aggregate / delayed.** Daily, not real-time.
4. **Educational.** Not investment advice.
5. **No auto-DM, no paid group, no VIP tier.**

🔗 Waitlist (free, opt-in): https://u2algo.com/?utm_source=telegram&utm_medium=organic&utm_campaign=customer-channel
📚 Docs & code: https://u2algo.com/
```

The welcome message must include the `COMPLIANCE_EN` byte-anchor verbatim
("Not investment advice. Trade at your own risk.") so the `has_disclaimer`
gate returns True for the channel description (manual check, not
software-gated — this file is the source of truth).

## 3. Daily snapshot template

The routine emits this exact format (see `scripts/routines/telegram_digest.py`
`format_en_digest`):

```
📊 *u2algo — Daily Snapshot (YYYY-MM-DD)*
Closed: `N` trades (✅ W / ❌ L)
Net P/L: `+/-X.XX%`
_Delayed, aggregate-only snapshot. Not investment advice. Trade at your own risk._
```

Wording rules (CMP-3 compliance):
- **Aggregate-only** — counts (N, W, L) and a single net-P/L %.
- **No per-trade fields** — never symbol / entry / SL / TP / size.
- **No `$`** — `conservative-proof` rule.
- **No perf-words near `%`** — "win rate", "return", "kazanç", "getiri" etc.
  trip `performance_pct_claim`. The wording "Net P/L" is the only safe
  phrasing; CMP-3 perf-word list excludes "P/L".
- **No banned phrases** — the CMP-3 EN list (guaranteed profit, risk-free,
  etc.) is checked at every emit; a violation aborts the post.
- **Disclaimer present** — `COMPLIANCE_EN` byte-anchor embedded verbatim.

## 4. Waitlist CTA (UTM-tagged)

Every weekly milestone post (e.g. a 7-day rolling average) may include
**one** UTM-tagged link to the waitlist landing page:

```
https://u2algo.com/?utm_source=telegram&utm_medium=organic&utm_campaign=customer-channel&utm_content=digest
```

Rules:
- One CTA per post (no CTA-stuffing).
- Always `utm_source=telegram` (channels are stable; we don't create
  one UTM per channel post).
- `utm_content` differentiates the post type (digest / weekly / monthly).
- UTM is captured server-side by `u2algo-site/server.js` (GROW-2 task).
- Never shortened (no bit.ly / t.me redirect shenanigans) — channel is
  public, full URL visible.

## 5. Anti-signal-service rules (regulatory guard, P-003 §2b)

A Telegram channel that posts per-trade entries/stops/targets IS a signal
service in most jurisdictions (CFTC, MiFID II, MAS). SD-5's whole point
is to be the **opposite**. The following are FORBIDDEN in this channel:

| Forbidden | Reason |
|---|---|
| "Entry: 3500, stop: 3490" | reconstructable tradeable signal |
| "BTC long, target 67500" | specific directional call |
| "Real-time alert: ..." | real-time = signal service |
| "DM me for VIP signals" | obvious |
| "Join the paid channel: ..." | signals-for-payment |
| "$XXX profit this week" | dollar amount = prospectus-like claim |
| "Hit rate: 87%, follow for more" | performance promise |
| Screenshot of PnL with $ amounts | visual equivalent of $ claim |
| Forwarded messages from private group | unverifiable origin |

When a follower asks for signals: respond with the **pinned welcome
message** and a one-liner ("This channel is aggregate-only by design —
we do not post per-trade entries.").

## 6. Operator-gated live activation

The routine is shipped as **DRAFT** in this PR. To go live, the operator
must:

1. **Provision a separate customer-channel bot** via BotFather
   (do NOT reuse the operator alerter bot).
2. **Add the bot to a public channel**, promote to admin with
   `post_messages` permission only (no other rights).
3. **Pin the welcome message** (template above) — operator action.
4. **Set VPS `.env.production`**:
   - `EFLOUD_CUSTOMER_TG_TOKEN=<bot token>`
   - `EFLOUD_CUSTOMER_TG_CHANNEL_ID=<channel id, e.g. -100...>`
   - (optional) `EFLOUD_CUSTOMER_TG_THREAD_ID=<forum topic id>`
5. **Edit `config.yaml`** under `notifications.telegram`:
   ```yaml
   notifications:
     telegram:
       enabled: true        # SD-5 only fires when this is true
       mode: daily_digest   # the only implemented mode
   ```
6. **Schedule the routine** in crontab:
   ```
   5 0 * * *  cd /opt/efloud-bot && python -m scripts.routines.telegram_digest
   ```
   (5 minutes after midnight UTC — gives the daily aggregator time to
   settle the previous day's CLOSED trades.)
7. **Monitor the first 7 days**:
   - Cron log shows `posted=true` daily.
   - No `posted=false reason=compliance...` blocks (would mean digest
     text drifted into a banned region).
   - No Telegram HTTP 4xx — bad token / wrong chat id / no permission.
8. **Rotate the token quarterly** (BotFather revoke + re-issue).
   Update `.env.production`, restart the cron daemon.

## 7. Engagement + retention tactics (organic only)

Allowed tactics:
- Weekly milestone summary (7-day rolling: total closed, aggregate %, mean win-rate).
- "What changed in the bot this week" (build-in-public, no $ or per-trade).
- Repost of one pre-approved public-blog post (after operator review).
- Monthly Q&A pinned message: "Ask anything; replies when the operator
  has time" — no per-trade advice.

Forbidden tactics:
- Giveaways / contests / "subscribe to win" — these are also regulated
  promotion in many jurisdictions.
- Polls asking "should I take this trade?" — bordering on solicitation.
- TradingView chart reposts with directional overlays — visual signal.

## 8. Acceptance (SD-5)

- [x] `scripts/routines/telegram_digest.py` shipped with 19 hermetic tests
      green (CI py3.11). Aggregate-only, double-gated, compliance-gated.
- [x] `docs/marketing/telegram-community.md` (this file) covers pinned
      welcome, daily template, UTM scheme, anti-signal-service rules,
      operator go-live runbook.
- [x] Customer creds (`EFLOUD_CUSTOMER_TG_*`) read from VPS `.env.production`
      ONLY. Repo references are NAME-only.
- [x] `EFLOUD_TELEGRAM_*` (operator alerter) is structurally isolated —
      regression test asserts SD-5 module never reads those env vars.
- [x] `ccxt.binance` / `BINANCE_*` never imported — regression test asserts.
- [x] `ops/alerter` source tree untouched.
- [x] `scripts.routines.runner.REGISTRY` does NOT gain a `telegram_digest`
      entry — no `make_future_client` coupling to mainnet trading creds.

## 9. Cross-references

- CMP-1 — disclaimer library (`docs/compliance/disclaimer-library.md`)
- CMP-3 — EN banned phrases + perf-pct guard (`scripts/content_compliance.py`)
- SD-2 — repurposing matrix (`docs/marketing/repurposing-matrix.md`)
- GROW-1 — KPI dictionary + CAC gate (`docs/marketing/kpi-dictionary.md`)
- GROW-2 — UTM capture (u2algo-site/server.js)
- T-018 — customer notifier implementation (`engine/notifications/telegram_notifier.py`)

*Downstream: SD-6 (YouTube structure) reuses the same wording + disclaimer
+ UTM scheme; CON-8 (video script compliance) imports the same gate.*