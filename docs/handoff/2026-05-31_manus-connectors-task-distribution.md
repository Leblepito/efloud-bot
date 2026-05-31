# Manus Connectors — u2algo / efloud-bot Task Distribution

Date: 2026-05-31
Source checked: https://open.manus.ai/docs/v2/connectors
Scope: Use Manus connectors through the local Hermes Manus MCP bridge for marketing/content automation around efloud-bot/u2algo.

## Key correction

Earlier note said Manus had no native Instagram/Meta-related connector. That is outdated.

Static docs page listed:

- Instagram Creator Marketplace — `9777f7bd-4ca3-431a-98d6-a7ed5221dd81`

After adding `MANUS_API_KEY`, a live `connector.list` call on this account returned more relevant connectors:

- Instagram — `4b899211-fd12-410e-a8d2-264a409cbc78` — builtin; description says it can ideate, plan, and automatically publish Posts, Stories, and Reels.
- Meta Ads Manager — `c073ede4-35a7-4c89-8158-c9b40c489932` — builtin; description says it can analyze performance, recommendations and reporting.

The live account list still did NOT show native YouTube or X/Twitter connectors. For those, route through Zapier, Make, n8n if authorized later, Playwright/My Browser, or another automation connector.

## Relevant connector inventory

### Core orchestration / automation

| Connector | UUID | Use |
|---|---|---|
| Zapier | `433d2fe0-e56d-42b2-8625-9996eab0bb1d` | Bridge to YouTube, X/Twitter, Instagram/Meta, Telegram, webhooks, Google tools if direct connector is missing |
| Make | `f8405590-5602-4fee-bfd6-f221623e6f72` | Scenario-based publishing pipeline; good for multi-step approval/publish flows |
| n8n | `d6b4170a-4001-450d-823a-287dfd9716a7` | Self-hosted or workflow-heavy automation alternative |
| My Browser | `be268223-40b2-4f3c-a907-c12eb1699283` | Browser actions when no API connector exists; use carefully, preferably manual-gated |
| Playwright | `356d5bc1-fb9f-4fa1-babb-05039dc09d63` | Programmatic browser automation / screenshots / web UI flows |
| Apify | `cf19c9d0-5f91-4e7a-af04-593febb5c80c` | Scraping, monitoring, social/research data extraction |
| Firecrawl | `abb9ed36-e693-44ab-be3d-1f5c3bb02294` | Web extraction / content monitoring |

### Content generation / creative production

| Connector | UUID | Use |
|---|---|---|
| OpenAI | `942ea72c-09f6-46f0-b4b3-f9890a6edbc5` | Drafts, captions, structured content, summarization |
| Anthropic | `815b5a30-463e-4662-8da7-081e3b5dfc7d` | Long-form review, compliance rewriting, planning |
| Google Gemini | `4157dedf-1326-4be8-9295-51416c7dba62` | Multimodal analysis, screenshot interpretation |
| OpenRouter | `c55a74cf-a236-4eda-8885-365d336cae4b` | Model routing/fallback |
| Perplexity | `2a574fdc-89ab-4ad7-b334-e2c156201b6f` | Research, web-grounded briefs |
| Grok | `491cde51-195c-4e72-96ea-8d80557c3b58` | X-native style ideation / social tone if useful |
| ElevenLabs | `23181678-c628-4c53-9a77-36778a36bbe5` | Voiceover generation |
| HeyGen | `c183add9-c22c-4199-b7f2-d885571afa3a` | Video/avatar content |
| Kling | `99474cab-58bf-47ae-af0e-43c156703be9` | AI video generation |
| Canva | `c63d86db-4c98-483a-af0c-f94721d7f2a5` | Social creatives, Instagram-ready layouts |
| Flux | `5c305236-d14e-43f7-93ff-b288afd26f09` | Image generation |

### Social / marketing / CRM

| Connector | UUID | Use |
|---|---|---|
| Instagram | `4b899211-fd12-410e-a8d2-264a409cbc78` | Live account connector; description says it can ideate, plan, and automatically publish Instagram Posts, Stories, and Reels. Use this first for Instagram publishing tests, but keep manual approval on. |
| Instagram Creator Marketplace | `9777f7bd-4ca3-431a-98d6-a7ed5221dd81` | Static docs connector; creator/marketplace operations. Use only if account exposes/authorizes it and exact capability matches need. |
| Meta Ads Manager | `c073ede4-35a7-4c89-8158-c9b40c489932` | Live account connector for Meta Ads performance analysis, recommendations, and reporting; not the primary organic publishing path. |
| HubSpot | `b389f747-6221-41aa-9dbb-732a97a02ea6` | CRM, leads, campaign tracking |
| Mailchimp Marketing | `331ff697-8348-4ed7-a596-7df98740fc1f` | Email list / newsletter / waitlist |
| Intercom | `73f5f556-978a-4f8a-85b3-ef2eec4473e5` | Customer support / lead chat |
| Apollo | `bb2a05d0-d728-48eb-b796-9b71e4f9c9ee` | B2B prospecting if needed |
| Close | `9b37aa72-4089-4f25-b774-122860ba61fa` | Sales CRM |

### Storage / project / publishing infrastructure

| Connector | UUID | Use |
|---|---|---|
| Google Drive | `f8900a57-4bd7-46cc-83a3-5ebd2420a817` | Store screenshots, video files, scripts, post archives |
| Gmail | `9444d960-ab7e-450f-9cb9-b9467fb0adda` | Email approvals / summaries / team alerts |
| Google Calendar | `dd5abf31-7ad3-4c0b-9b9a-f0a576645baf` | Content calendar |
| Airtable | `d669ca60-22cf-4e16-93d4-845071f9216c` | Content pipeline DB / approvals / asset registry |
| Notion | `9c27c684-2f4f-4d33-8fcf-51664ea15c00` | Editorial workspace / research notes |
| Linear | `982c169d-0c89-4dbd-95fd-30b49cc2f71e` | Engineering work items |
| GitHub | `bbb0df76-66bd-4a24-ae4f-2aac4750d90b` | Repo issues/PRs/content templates |
| Supabase | `84ab78ef-139c-48ff-acd4-cba718b8a484` | App DB access through Manus |
| Supabase API | `86a04f98-35cf-4099-9044-ab851a473cf5` | API-level Supabase operations |
| Vercel | `a50c5d31-af5e-4e01-a992-057663a7ee1f` | Frontend deploys |
| Cloudflare | `119e6b13-c2e3-48db-b568-f82191de6b4e` | DNS/CDN/workers |
| Cloudflare API | `80bca437-287e-4407-adf0-1a0b298528e5` | API-level CF automation |
| Webflow | `1d489fb9-0601-4ea7-9942-b866657178c1` | Marketing site CMS if used |
| Wix | `d0fa4acf-7cf6-4402-bd84-82a850342a79` | Site builder alternative |

### Analytics / monitoring / market data

| Connector | UUID | Use |
|---|---|---|
| PostHog | `89dac2c3-74d0-4f94-86d1-0ee6c4566193` | Funnel/product analytics |
| Sentry | `838d5e1c-7dd4-4782-9429-c459126707c7` | Error monitoring |
| Ahrefs | `305b3b49-32ce-4b2b-a355-3492fe85d17f` | SEO research |
| Similarweb | `700c656f-b4a4-4e39-a886-a20782d99b6f` | Competitive traffic research |
| Polygon.io | `376008de-cd2a-4bfb-93aa-2652b8585c8e` | Market data research, not direct Binance execution |
| Metabase | `9fe14dac-4288-4371-91a8-86a36051a865` | Dashboard/reporting |

## Recommended task distribution

### Lane A — Signal capture and source-of-truth packaging

Owner: efloud-bot backend / local code, not Manus.

Inputs:

- efloud-bot signal event
- trade horizon config: scalp / orta / uzun
- symbol, timeframe, direction, entry, SL, TP levels, confidence, risk disclaimers
- TradingView chart screenshot path or URL

Output:

- A single JSON content job object, e.g. `content_job.created`.
- Store in local DB / Supabase / file queue.
- Do NOT auto-publish from the trading process. Keep publishing decoupled from trade execution.

Suggested connectors later:

- Supabase / Supabase API for content job DB
- Google Drive for assets

### Lane B — Chart screenshot and visual interpretation

Owner: Hermes + Manus task, gated.

Recommended connectors:

- Playwright: `356d5bc1-fb9f-4fa1-babb-05039dc09d63`
- My Browser: `be268223-40b2-4f3c-a907-c12eb1699283`
- Google Gemini: `4157dedf-1326-4be8-9295-51416c7dba62`
- OpenAI or Anthropic for final text summary

Tasks:

1. Open TradingView chart for symbol/timeframe.
2. Capture screenshot.
3. Analyze visible structure: trend, SMC zone, invalidation, risk note.
4. Return structured output only — no posting.

### Lane C — Compliant copywriting package

Owner: Hermes + Manus + compliance gate.

Recommended connectors:

- OpenAI: `942ea72c-09f6-46f0-b4b3-f9890a6edbc5`
- Anthropic: `815b5a30-463e-4662-8da7-081e3b5dfc7d`
- Google Gemini: `4157dedf-1326-4be8-9295-51416c7dba62`
- Notion/Airtable for draft tracking

Tasks:

Produce variants:

- X short post
- Instagram caption
- Telegram community signal/commentary
- YouTube Shorts title/description
- Long-form market note for u2algo.com/blog or newsletter

Mandatory guardrails:

- Include “yatırım tavsiyesi değildir”.
- Avoid guaranteed-profit language.
- Frame as research / algorithmic trading infrastructure.
- Do not imply managed funds or guaranteed signals.

### Lane D — Video / image asset generation

Owner: Manus creative task, gated.

Recommended connectors:

- Canva: `c63d86db-4c98-483a-af0c-f94721d7f2a5`
- HeyGen: `c183add9-c22c-4199-b7f2-d885571afa3a`
- Kling: `99474cab-58bf-47ae-af0e-43c156703be9`
- Flux: `5c305236-d14e-43f7-93ff-b288afd26f09`
- ElevenLabs: `23181678-c628-4c53-9a77-36778a36bbe5`
- Google Drive: `f8900a57-4bd7-46cc-83a3-5ebd2420a817`

Tasks:

1. Convert screenshot + caption into branded u2algo visual.
2. Generate short video / voiceover if required.
3. Save artifacts to Google Drive or local repo artifact folder.
4. Return asset URLs and metadata.

### Lane E — Social publishing

Owner: Make/Zapier/n8n first; direct connectors only after verifying exact capability.

Recommended connectors:

- Zapier: `433d2fe0-e56d-42b2-8625-9996eab0bb1d`
- Make: `f8405590-5602-4fee-bfd6-f221623e6f72`
- n8n: `d6b4170a-4001-450d-823a-287dfd9716a7`
- Instagram Creator Marketplace: `9777f7bd-4ca3-431a-98d6-a7ed5221dd81` (verify if it supports the desired publishing action)

Tasks:

- X/Twitter: likely through Zapier/Make/n8n or browser automation.
- YouTube: likely through Zapier/Make/n8n using YouTube Data API integration.
- Instagram organic posts/Reels/Stories: use live `Instagram` connector `4b899211-fd12-410e-a8d2-264a409cbc78` first, with manual approval.
- Meta ads reporting/optimization: use `Meta Ads Manager` connector `c073ede4-35a7-4c89-8158-c9b40c489932`.
- Instagram Creator Marketplace: secondary/special-purpose path if exposed in account and needed.
- Telegram: likely direct bot API in efloud-bot/Hermes, or Zapier/Make if desired.

Safety:

- Phase 1: draft-only.
- Phase 2: manual approval required.
- Phase 3: limited auto-post for non-trade educational posts only.
- Trade signal posts should remain manual-gated until compliance and platform policy are proven.

### Lane F — CRM / community / funnel

Owner: Manus + CRM connector + website.

Recommended connectors:

- HubSpot: `b389f747-6221-41aa-9dbb-732a97a02ea6`
- Mailchimp Marketing: `331ff697-8348-4ed7-a596-7df98740fc1f`
- Intercom: `73f5f556-978a-4f8a-85b3-ef2eec4473e5`
- Airtable: `d669ca60-22cf-4e16-93d4-845071f9216c`
- Notion: `9c27c684-2f4f-4d33-8fcf-51664ea15c00`

Tasks:

- Capture waitlist/lead forms from u2algo.com.
- Route high-intent leads to CRM.
- Archive published posts and campaign metrics.
- Feed community FAQ/content ideas back to the editorial queue.

## Initial Manus connector sets by workflow

### Draft only / safe default

Use for first real API tests:

```json
[
  "942ea72c-09f6-46f0-b4b3-f9890a6edbc5",
  "815b5a30-463e-4662-8da7-081e3b5dfc7d",
  "f8900a57-4bd7-46cc-83a3-5ebd2420a817"
]
```

### Visual content draft

```json
[
  "4157dedf-1326-4be8-9295-51416c7dba62",
  "c63d86db-4c98-483a-af0c-f94721d7f2a5",
  "f8900a57-4bd7-46cc-83a3-5ebd2420a817"
]
```

### Social publishing bridge, manual-gated

```json
[
  "433d2fe0-e56d-42b2-8625-9996eab0bb1d",
  "f8405590-5602-4fee-bfd6-f221623e6f72",
  "d6b4170a-4001-450d-823a-287dfd9716a7",
  "9777f7bd-4ca3-431a-98d6-a7ed5221dd81"
]
```

## Next implementation steps

1. Add `MANUS_API_KEY` to local Hermes `.env`.
2. Restart Hermes or run `/reload-mcp`.
3. Run `mcp_manus_connector_list` to verify the authorized connectors available to this account.
4. Authorize minimum connectors in Manus web app:
   - OpenAI or Anthropic
   - Google Drive
   - Make or Zapier
   - Canva or HeyGen/Kling if video/visual generation will be tested
   - Instagram connector `4b899211-fd12-410e-a8d2-264a409cbc78` if Instagram workflow is desired
   - Meta Ads Manager if ad analytics/reporting is desired
5. Create first test Manus task as draft-only, no publishing.
6. Build efloud-bot content job queue separately from live trading execution.
7. Add approval gate before any social posting.

## Secret handling

Do not commit API keys. Do not put keys into repo docs.

Preferred local path:

`C:\Users\utkuc\AppData\Local\hermes\.env`

```env
MANUS_API_KEY=your_manus_api_key_here
```

If the key is pasted into a chat, treat it as temporary secret material: write it to `.env`, do not echo it back, do not save it to memory, and do not include it in repo files.
