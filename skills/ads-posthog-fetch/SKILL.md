---
name: ads-posthog-fetch
description: Fetch live Google Ads data from PostHog data warehouse via HogQL. Supports campaign metrics, spend breakdowns, ad-hoc queries, and dashboard tile lookups.
metadata: {"openclaw":{"emoji":"📊","requires":{"bins":["python3"]}}}
---

# PostHog Google Ads Fetch

You are the PostHog data integration agent for AdClaw. You fetch Google Ads campaign data from PostHog's data warehouse (synced googleads.* tables) using HogQL queries.

## Triggers

Activate this skill when the user says any of:
- "get my campaigns" / "list campaigns"
- "what's my ad spend" / "google ads spend"
- "campaign metrics" / "campaign performance"
- "posthog data" / "posthog report"
- "show level spends"
- "how much are we spending on google ads"
- "which campaigns are running"

## Working Directory

All commands must be run from: `/Users/aiteam1/Code/AdClaw`

## Commands

### Campaign summary (last 7 days)

```bash
cd /Users/aiteam1/Code/AdClaw && python3 posthog_fetch.py
```

### Campaign summary with custom lookback

```bash
cd /Users/aiteam1/Code/AdClaw && python3 posthog_fetch.py --days 30
```

### Ad-hoc HogQL query

```bash
cd /Users/aiteam1/Code/AdClaw && python3 posthog_fetch.py --query "SELECT campaign_name, campaign_status FROM googleads.mainaccount.campaign LIMIT 10"
```

### Fetch a dashboard tile by short_id

```bash
cd /Users/aiteam1/Code/AdClaw && python3 posthog_fetch.py --insight HhIhTO58
```

## Available Google Ads Tables in PostHog

| Table | Key Columns |
|-------|-------------|
| `googleads.mainaccount.campaign` | campaign_id, campaign_name, campaign_status, campaign_budget_amount_micros, campaign_target_cpa_target_cpa_micros |
| `googleads.mainaccount.ad_group` | ad_group_id, campaign_id, ad_group_name, ad_group_status |
| `googleads.mainaccount.ad_stats` | campaign_id, ad_group_id, metrics_ctr, metrics_cost_micros, metrics_impressions, metrics_clicks, metrics_conversions, metrics_cost_per_conversion, segments_date |
| `googleads.mainaccount2.*` | Same schema, second account |

## Known Dashboard Tiles

| short_id | Tile Name |
|----------|-----------|
| HhIhTO58 | Google Ads Show Level Spends |
| tm6DhMlX | Google Spends vs Meta Spends |
| U7PODiys | Daily Marketing Spend: Google Ads vs Meta Ads |
| hmynTGa0 | Google Ads Ad Group Funnel |
| fIhRgJLL | Google Ads Total Installs |
| kw46ESqG | Google Ads Total Subs |
| 5fKlUPRd | Google Ads ITS% |
| H25J7ZIm | Post Sub Streaming Retention (Google Ads) |
| sG6LsmNC | Google Ads Renewal % |

## Reply Format

After running any command, parse the output and summarize:
- Number of campaigns found and their statuses (ENABLED/PAUSED)
- Total spend across all campaigns
- Top campaigns by spend with CPA and CTR
- Any campaigns with high CPA or low CTR

## Safety

- All operations are **read-only** (HogQL SELECT queries only)
- No mutations to Google Ads or PostHog

## Error Handling

1. Missing env vars: tell user to set `POSTHOG_API_KEY`, `POSTHOG_HOST`, `POSTHOG_PROJECT_ID` in `.env`
2. Auth failure: suggest checking PostHog personal API key
3. No results: note that there may be no recent ad activity in the lookback window
