---
name: ads-composio-fetch
description: Fetch live Google Ads data via Composio MCP server. Supports ad-hoc queries, direct tool calls, and structured pipeline data fetch.
metadata: {"openclaw":{"emoji":"🔌","requires":{"bins":["python3"]}}}
---

# Composio Google Ads Fetch

You are the data integration agent for AdClaw. You connect to Google Ads via Composio's MCP server to fetch live campaign data.

## Triggers

Activate this skill when the user says any of:
- "get my campaigns" → fetch account data
- "list campaigns" → fetch account data
- "what's my ad spend" → fetch spend data
- "show me campaign X" → fetch specific campaign
- "Google Ads data" → general data fetch
- "connect to Google Ads" → test connection
- "tell me about my google ad campaign" → fetch account overview

## Commands

### Fetch account overview (customer lists + campaigns)

```bash
cd /Users/aiteam1/Code/AdClaw && python3 composio_fetch.py
```

### Fetch a specific campaign by name

```bash
cd /Users/aiteam1/Code/AdClaw && python3 composio_fetch.py --tool GOOGLEADS_GET_CAMPAIGN_BY_NAME --args '{"name": "<campaign_name>"}'
```

### Fetch a specific campaign by ID

```bash
cd /Users/aiteam1/Code/AdClaw && python3 composio_fetch.py --tool GOOGLEADS_GET_CAMPAIGN_BY_ID --args '{"id": "<campaign_id>"}'
```

### Ad-hoc query (LLM-driven tool selection)

```bash
cd /Users/aiteam1/Code/AdClaw && python3 composio_fetch.py --directive "<user message>"
```

Replace `<user message>` with the user's actual request.

## Available Google Ads Tools

| Tool | Arguments | Description |
|------|-----------|-------------|
| `GOOGLEADS_GET_CUSTOMER_LISTS` | `{}` | List all customer/audience lists |
| `GOOGLEADS_GET_CAMPAIGN_BY_NAME` | `{"name": "..."}` | Search campaign by exact name |
| `GOOGLEADS_GET_CAMPAIGN_BY_ID` | `{"id": "..."}` | Get campaign details by ID |

## Reply Format

After running any command, parse the JSON output. The response structure is:
```json
{
  "content": [{"type": "text", "text": "<JSON string with data>"}],
  "isError": false
}
```

Extract the inner `text` field, parse it as JSON, and summarize:
- Number of campaigns/items found
- Key metrics if available (spend, CPA, CTR)
- Any errors or auth issues with clear next steps

## Safety

- All tool execution is gated to **read-only** operations
- Write operations (CREATE, DELETE, UPDATE, etc.) are automatically blocked
- If auth fails, suggest checking the Composio dashboard for connection status

## Error Handling

1. Missing env vars → tell user which vars to set in `.env` (`COMPOSIO_MCP_URL`, `COMPOSIO_MCP_API_KEY`)
2. Auth failure → suggest checking Composio dashboard + reconnecting Google Ads
3. No results → note that the account may have no active campaigns
4. Network error → suggest retrying or checking connectivity
