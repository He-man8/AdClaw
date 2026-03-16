---
name: ads-posthog-fetch
description: Fetch live Google Ads and Meta Ads data from PostHog data warehouse via HogQL. Supports campaign metrics, spend breakdowns, ad-hoc queries, and dashboard tile lookups for both platforms.
metadata: {"openclaw":{"emoji":"📊","requires":{"bins":["python3"]}}}
---

# PostHog Ads Fetch (Google + Meta)

You are the PostHog data integration agent for AdClaw. You fetch Google Ads and Meta Ads campaign data from PostHog's data warehouse using HogQL queries.

## Triggers

Activate this skill when the user says any of:
- "get my campaigns" / "list campaigns"
- "what's my ad spend" / "google ads spend" / "meta ads spend"
- "campaign metrics" / "campaign performance"
- "posthog data" / "posthog report"
- "show level spends"
- "how much are we spending on google ads"
- "how much are we spending on meta"
- "check my meta ads" / "meta campaigns"
- "which campaigns are running"
- "compare google vs meta"

## Working Directory

All commands must be run from: `/Users/aiteam1/Code/AdClaw`

## Commands

### All campaigns — Google + Meta (last 7 days)

```bash
cd /Users/aiteam1/Code/AdClaw && python3 posthog_fetch.py
```

### Meta Ads campaigns only

```bash
cd /Users/aiteam1/Code/AdClaw && python3 posthog_fetch.py --meta-only
```

### Google Ads campaigns only

```bash
cd /Users/aiteam1/Code/AdClaw && python3 posthog_fetch.py --google-only
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

## Available Tables in PostHog

### Google Ads (2 accounts: mainaccount, mainaccount2)

| Table | Key Columns |
|-------|-------------|
| `googleads.{account}.campaign` | campaign_id, campaign_name, campaign_status, campaign_budget_amount_micros, campaign_target_cpa_target_cpa_micros |
| `googleads.{account}.ad_group` | ad_group_id, campaign_id, ad_group_name, ad_group_status |
| `googleads.{account}.ad_stats` | campaign_id, ad_group_id, metrics_ctr, metrics_cost_micros, metrics_impressions, metrics_clicks, metrics_conversions, segments_date |

### Meta Ads (4 accounts: mainaccount, chaishots, chaishots4, meta3account)

| Table | Key Columns |
|-------|-------------|
| `{account}metaads_campaigns` | id, name, status, effective_status, objective, daily_budget, budget_remaining |
| `{account}metaads_campaign_stats` | campaign_id, spend, impressions, clicks, ctr, cpc, cpm, frequency, reach, date_start, date_stop, actions (json), conversions (json) |
| `{account}metaads_adsets` | id, name, status, campaign_id, daily_budget, targeting |
| `{account}metaads_adset_stats` | adset_id, spend, impressions, clicks, ctr, frequency, reach, date_start |
| `{account}metaads_ads` | id, name, status, adset_id |
| `{account}metaads_ad_stats` | ad_id, spend, impressions, clicks, ctr, frequency, reach, date_start |

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
- Number of campaigns found per platform and their statuses
- Total spend across all campaigns (broken down by Google vs Meta)
- Top campaigns by spend with CPA, CTR, and frequency
- Any campaigns with high CPA, low CTR, or high frequency (fatigue)
- Note: Meta campaigns show CPA=0 because conversions require JSON extraction from the `actions` column — use ad-hoc HogQL for per-campaign conversion details

## Safety

- All operations are **read-only** (HogQL SELECT queries only)
- No mutations to Google Ads, Meta Ads, or PostHog

## Error Handling

1. Missing env vars: tell user to set `POSTHOG_API_KEY`, `POSTHOG_HOST`, `POSTHOG_PROJECT_ID` in `.env`
2. Auth failure: suggest checking PostHog personal API key
3. No results: note that there may be no recent ad activity in the lookback window
4. Account fetch failures (e.g. chaishots4 400 error) are logged as warnings — remaining accounts still return data
