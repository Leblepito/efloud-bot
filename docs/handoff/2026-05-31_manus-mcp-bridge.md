# Manus MCP Bridge — Hermes → Manus → Zapier/Make → Social Platforms

Date: 2026-05-31
Scope: Local Hermes Agent integration for u2algo/efloud-bot marketing automation.
Status: Installed and locally verified at MCP tool-discovery level. Real Manus API calls require `MANUS_API_KEY`.

## Why this exists

The user wants to automate a pipeline around efloud-bot/u2algo:

- efloud-bot generates trade signals on Binance.
- TradingView chart screenshots can be captured for signal visuals.
- Content should be created for YouTube, X, Instagram/Meta and Telegram/community.
- Manus should be available from Hermes as an orchestration layer.

Manus v2 is REST API + webhooks. It is not a native MCP server. Therefore a local MCP bridge was created so Hermes can call Manus through normal MCP tools.

## Installed files

Outside the repo, under the default Hermes profile:

- `C:\Users\utkuc\AppData\Local\hermes\mcp-servers\manus\manus_mcp.py`
- `C:\Users\utkuc\AppData\Local\hermes\mcp-servers\manus\run_manus_mcp.sh`
- `C:\Users\utkuc\AppData\Local\hermes\mcp-servers\manus\README.md`

Hermes config changed:

- `C:\Users\utkuc\AppData\Local\hermes\config.yaml`
- Backup before change: `C:\Users\utkuc\AppData\Local\hermes\config.yaml.bak-manus-20260531-134842`

Configured block:

```yaml
mcp_servers:
  manus:
    command: bash
    args:
      - C:/Users/utkuc/AppData/Local/hermes/mcp-servers/manus/run_manus_mcp.sh
    connect_timeout: 60
    timeout: 180
```

## Exposed MCP tools

Hermes will expose these after restart / `/reload-mcp` with the prefix `mcp_manus_*`:

- `mcp_manus_task_create`
- `mcp_manus_task_detail`
- `mcp_manus_task_list_messages`
- `mcp_manus_task_send_message`
- `mcp_manus_task_stop`
- `mcp_manus_task_list`
- `mcp_manus_connector_list`
- `mcp_manus_webhook_create`
- `mcp_manus_webhook_list`
- `mcp_manus_webhook_delete`
- `mcp_manus_website_status`
- `mcp_manus_website_publish`

## Verification already performed

Commands run successfully:

```bash
python3 -m py_compile /c/Users/utkuc/AppData/Local/hermes/mcp-servers/manus/manus_mcp.py
hermes mcp list
hermes mcp test manus
```

Observed result:

- `hermes mcp list`: `manus` enabled.
- `hermes mcp test manus`: connected, 12 tools discovered.
- Direct MCP SDK `list_tools`: returned 12 tools.
- After `MANUS_API_KEY` was added, live `connector_list` succeeded via GET `/v2/connector.list`.
- Live private draft-only `task_create` succeeded and returned private task URL/id.
- Live `task_detail` and `task_list_messages` succeeded after changing those endpoints to GET.

Implementation note:

- `task.create` uses POST.
- `connector.list`, `task.detail`, `task.listMessages`, and `task.list` use GET.

## Manus API key

Status: configured locally in:

`C:\Users\utkuc\AppData\Local\hermes\.env`

The value is intentionally not written here. If rotation is needed, create a new key in the Manus web app:

- https://manus.im
- Settings / API Integration / API Keys

Then replace the local `.env` value:

```env
MANUS_API_KEY=your_manus_api_key_here
```

The bridge intentionally parses only these keys from `.env`:

- `MANUS_API_KEY`
- `MANUS_BASE_URL`
- `MANUS_HTTP_TIMEOUT`

It does not shell-source the whole `.env`, because this local `.env` had at least one non-shell line and shell sourcing broke MCP startup.

## YouTube / Instagram / Meta note

Updated after checking https://open.manus.ai/docs/v2/connectors on 2026-05-31:

- Manus has `Instagram Creator Marketplace` connector: `9777f7bd-4ca3-431a-98d6-a7ed5221dd81`.
- Manus has automation connectors: Zapier `433d2fe0-e56d-42b2-8625-9996eab0bb1d`, Make `f8405590-5602-4fee-bfd6-f221623e6f72`, n8n `d6b4170a-4001-450d-823a-287dfd9716a7`.
- Native YouTube and X/Twitter connectors were not listed; use Zapier/Make/n8n or browser automation for those.
- Verify whether Instagram Creator Marketplace supports the exact publishing action needed; if not, use Zapier/Make/n8n fallback.

Recommended architecture:

```text
Hermes / efloud-bot event
  → Manus MCP task_create
  → Manus uses explicit connector UUIDs
  → Draft assets/copy first
  → Manual approval gate
  → Zapier/Make/n8n or Instagram connector posts to target platforms
```

Flow for connector UUIDs:

1. Authorize desired connectors inside Manus.
2. Run `mcp_manus_connector_list` from Hermes after `MANUS_API_KEY` is configured.
3. Copy the authorized connector UUIDs.
4. Pass them to `mcp_manus_task_create(connectors=["uuid"] )`.

## Important safety notes

- This integration does not touch Binance, bot production config, Docker, VPS, or live trading.
- It only modifies local Hermes default-profile MCP configuration.
- Social posting should remain gated/manual until copy, compliance disclaimers and platform credentials are verified.
- Trading/marketing copy must avoid guaranteed-profit claims and include risk disclaimers.
