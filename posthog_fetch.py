"""
PostHog Ads Integration (Google Ads + Meta Ads)
-------------------------------------------------
Fetches campaign data from PostHog's data warehouse via HogQL queries
and the insights API.

Google Ads tables:
  - googleads.mainaccount.campaign / ad_group / ad_stats
  - googleads.mainaccount2.* — second account (same schema)

Meta Ads tables (4 accounts: mainaccount, chaishots, chaishots4, meta3account):
  - {account}metaads_campaigns — campaign metadata, budget, status
  - {account}metaads_campaign_stats — daily metrics (spend, CTR, frequency, reach)
  - {account}metaads_ad_stats / adset_stats — ad and adset level metrics

Modes:
  python3 posthog_fetch.py                              # all campaigns (last 7 days)
  python3 posthog_fetch.py --query "SELECT ..."         # ad-hoc HogQL
  python3 posthog_fetch.py --insight HhIhTO58           # fetch a dashboard tile
  python3 posthog_fetch.py --days 30                    # change lookback window
  python3 posthog_fetch.py --meta-only                  # Meta Ads campaigns only
  python3 posthog_fetch.py --google-only                # Google Ads campaigns only

All operations are read-only.
"""

import json
import logging
import sys

import requests

from config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30

# ── Google Ads tables in PostHog data warehouse ──────────────
# Both mainaccount and mainaccount2 have the same schema.
GOOGLE_ACCOUNTS = ["mainaccount", "mainaccount2"]

# ── Meta Ads tables in PostHog data warehouse ─────────────────
# 4 Meta ad accounts synced as {account}metaads_* tables.
META_ACCOUNTS = ["mainaccount", "chaishots", "chaishots4", "meta3account"]

# Known dashboard tile short_ids for Google Ads
TILES = {
    "show_spends": "HhIhTO58",       # Google Ads Show Level Spends
    "google_vs_meta": "tm6DhMlX",    # Google Spends vs Meta Spends
    "daily_spend": "U7PODiys",       # Daily Marketing Spend
    "ad_group_funnel": "hmynTGa0",   # Google Ads Ad Group Funnel
    "total_installs": "fIhRgJLL",    # Google Ads Total Installs
    "total_subs": "kw46ESqG",        # Google Ads Total Subs
    "its_pct": "5fKlUPRd",           # Google Ads ITS%
    "retention": "H25J7ZIm",         # Post Sub Streaming Retention
    "renewal_pct": "sG6LsmNC",       # Google Ads Renewal %
}


# ── API helpers ──────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.posthog_api_key}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    host = settings.posthog_host.rstrip("/")
    pid = settings.posthog_project_id
    return f"{host}/api/projects/{pid}{path}"


def run_hogql_query(query: str) -> dict:
    """Run a HogQL query and return {columns, rows}."""
    settings.require_posthog()
    r = requests.post(
        _url("/query/"),
        headers=_headers(),
        json={"query": {"kind": "HogQLQuery", "query": query}},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    return {
        "columns": data.get("columns", []),
        "rows": data.get("results", []),
    }


def get_insight_result(short_id: str) -> dict:
    """Fetch a PostHog insight/tile by short_id."""
    settings.require_posthog()
    r = requests.get(
        _url(f"/insights/?short_id={short_id}&refresh=force_blocking"),
        headers=_headers(),
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    if not results:
        return {"name": short_id, "columns": [], "rows": []}

    insight = results[0]
    name = insight.get("name", short_id)

    # Try to get data from query.source.response (DataVisualizationNode)
    query = insight.get("query", {})
    source = query.get("source", {})
    response = source.get("response", {})
    if response.get("results"):
        return {
            "name": name,
            "columns": response.get("columns", []),
            "rows": response["results"],
        }

    # Fall back to insight.result
    result = insight.get("result", [])
    return {"name": name, "columns": [], "rows": result}


# ── Campaign data queries ────────────────────────────────────

CAMPAIGN_METRICS_QUERY = """
SELECT
    c.campaign_id,
    c.campaign_name,
    c.campaign_status,
    c.campaign_bidding_strategy_type,
    round(toFloat(c.campaign_budget_amount_micros) / 1000000, 2) AS daily_budget,
    round(toFloat(c.campaign_target_cpa_target_cpa_micros) / 1000000, 2) AS target_cpa,
    round(SUM(toFloat(s.metrics_cost_micros)) / 1000000, 2) AS spend,
    SUM(s.metrics_impressions) AS impressions,
    SUM(s.metrics_clicks) AS clicks,
    CASE WHEN SUM(s.metrics_impressions) > 0
         THEN round(SUM(s.metrics_clicks) / SUM(s.metrics_impressions) * 100, 4)
         ELSE 0 END AS ctr,
    round(SUM(s.metrics_conversions), 2) AS conversions,
    CASE WHEN SUM(s.metrics_conversions) > 0
         THEN round(SUM(toFloat(s.metrics_cost_micros)) / 1000000 / SUM(s.metrics_conversions), 2)
         ELSE 0 END AS cpa,
    CASE WHEN SUM(s.metrics_impressions) > 0
         THEN round(SUM(s.metrics_impressions) / COUNT(DISTINCT s.segments_date), 2)
         ELSE 0 END AS avg_daily_impressions,
    COUNT(DISTINCT s.segments_date) AS days_active,
    c.campaign_advertising_channel_type AS channel_type,
    '{account}' AS account
FROM googleads.{account}.ad_stats s
JOIN googleads.{account}.campaign c ON s.campaign_id = c.campaign_id
WHERE s.segments_date >= today() - interval {days} day
GROUP BY
    c.campaign_id, c.campaign_name, c.campaign_status,
    c.campaign_bidding_strategy_type, c.campaign_budget_amount_micros,
    c.campaign_target_cpa_target_cpa_micros, c.campaign_advertising_channel_type
ORDER BY spend DESC
"""


def fetch_campaign_data(days: int = 7) -> list[dict]:
    """
    Fetch campaign-level metrics from all Google Ads accounts
    in PostHog's data warehouse.
    """
    settings.require_posthog()
    all_campaigns = []

    for account in GOOGLE_ACCOUNTS:
        query = CAMPAIGN_METRICS_QUERY.format(account=account, days=days)
        try:
            result = run_hogql_query(query)
            columns = result["columns"]
            for row in result["rows"]:
                campaign = dict(zip(columns, row))
                campaign["platform"] = "google"
                all_campaigns.append(campaign)
        except Exception as e:
            logger.warning("Failed to fetch Google from %s: %s", account, e)

    logger.info("Fetched %d Google campaigns from PostHog", len(all_campaigns))
    return all_campaigns


# ── Meta Ads campaign query ───────────────────────────────────

META_CAMPAIGN_METRICS_QUERY = """
SELECT
    c.id AS campaign_id,
    c.name AS campaign_name,
    c.effective_status AS campaign_status,
    c.objective AS channel_type,
    round(toFloat(coalesce(c.daily_budget, '0')), 2) AS daily_budget,
    0 AS target_cpa,
    round(SUM(toFloat(s.spend)), 2) AS spend,
    SUM(toInt(s.impressions)) AS impressions,
    SUM(toInt(s.clicks)) AS clicks,
    CASE WHEN SUM(toInt(s.impressions)) > 0
         THEN round(SUM(toInt(s.clicks)) * 100.0 / SUM(toInt(s.impressions)), 4)
         ELSE 0 END AS ctr,
    0 AS conversions,
    0 AS cpa,
    CASE WHEN SUM(toInt(s.impressions)) > 0
         THEN round(SUM(toInt(s.impressions)) / COUNT(DISTINCT s.date_start), 2)
         ELSE 0 END AS avg_daily_impressions,
    COUNT(DISTINCT s.date_start) AS days_active,
    round(AVG(toFloat(s.frequency)), 2) AS meta_frequency,
    SUM(toInt(s.reach)) AS meta_reach,
    '{account}' AS account
FROM {account}metaads_campaign_stats s
JOIN {account}metaads_campaigns c ON s.campaign_id = c.id
WHERE s.date_start >= toString(today() - interval {days} day)
GROUP BY c.id, c.name, c.effective_status, c.daily_budget, c.objective
ORDER BY spend DESC
"""


def fetch_meta_campaign_data(days: int = 7) -> list[dict]:
    """
    Fetch campaign-level metrics from all Meta Ads accounts
    in PostHog's data warehouse.
    """
    settings.require_posthog()
    all_campaigns = []

    for account in META_ACCOUNTS:
        query = META_CAMPAIGN_METRICS_QUERY.format(account=account, days=days)
        try:
            result = run_hogql_query(query)
            columns = result["columns"]
            for row in result["rows"]:
                campaign = dict(zip(columns, row))
                campaign["platform"] = "meta"
                all_campaigns.append(campaign)
        except Exception as e:
            logger.warning("Failed to fetch Meta from %s: %s", account, e)

    logger.info("Fetched %d Meta campaigns from PostHog", len(all_campaigns))
    return all_campaigns


# ── Converter helpers (same pattern as composio_fetch.py) ────

def _get(raw: dict, *keys, default=None):
    for k in keys:
        if k in raw:
            return raw[k]
    return default


def _float(raw: dict, *keys, default: float = 0.0) -> float:
    val = _get(raw, *keys, default=default)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def to_ad_health(raw_campaigns: list[dict]) -> list:
    from health_check import AdHealth
    results = []
    for raw in raw_campaigns:
        results.append(AdHealth(
            ad_id=str(_get(raw, "campaign_id", default="unknown")),
            ad_name=str(_get(raw, "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "campaign_name", default="Unknown")),
            frequency=_estimate_frequency(raw),
            ctr=_float(raw, "ctr", default=0.0),
            cpa=_float(raw, "cpa", default=0.0),
            target_cpa=_float(raw, "target_cpa", default=0.0),
            spend=_float(raw, "spend", default=0.0),
            daily_budget=_float(raw, "daily_budget", default=0.0),
        ))
    return results


def to_ad_metrics(raw_campaigns: list[dict]) -> list:
    from budget_guardian import AdMetrics
    results = []
    for raw in raw_campaigns:
        results.append(AdMetrics(
            ad_id=str(_get(raw, "campaign_id", default="unknown")),
            ad_name=str(_get(raw, "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "campaign_name", default="Unknown")),
            cpa=_float(raw, "cpa", default=0.0),
            target_cpa=_float(raw, "target_cpa", default=0.0),
            spend=_float(raw, "spend", default=0.0),
            daily_budget=_float(raw, "daily_budget", default=100.0),
            ctr=_float(raw, "ctr", default=0.0),
            frequency=_estimate_frequency(raw),
            roas=0.0,
        ))
    return results


def to_ad_performance(raw_campaigns: list[dict]) -> list:
    from content_lab import AdPerformance
    results = []
    for raw in raw_campaigns:
        results.append(AdPerformance(
            ad_id=str(_get(raw, "campaign_id", default="unknown")),
            ad_name=str(_get(raw, "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "campaign_name", default="Unknown")),
            ad_format=str(_get(raw, "channel_type", default="UNKNOWN")),
            ctr=_float(raw, "ctr", default=0.0),
            cpa=_float(raw, "cpa", default=0.0),
            target_cpa=_float(raw, "target_cpa", default=0.0),
            frequency=_estimate_frequency(raw),
            spend=_float(raw, "spend", default=0.0),
            headline="(no headline)",
            body="(no body)",
            cta="Learn More",
        ))
    return results


def to_ad_with_copy(raw_campaigns: list[dict]) -> list:
    from copy_writer import AdWithCopy
    results = []
    for raw in raw_campaigns:
        results.append(AdWithCopy(
            ad_id=str(_get(raw, "campaign_id", default="unknown")),
            ad_name=str(_get(raw, "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "campaign_name", default="Unknown")),
            ctr=_float(raw, "ctr", default=0.0),
            cpa=_float(raw, "cpa", default=0.0),
            target_cpa=_float(raw, "target_cpa", default=0.0),
            headline="(no headline)",
            body="(no body)",
            cta="Learn More",
        ))
    return results


def _estimate_frequency(raw: dict) -> float:
    """
    Return ad frequency. Meta provides it natively; for Google Ads we
    estimate from impressions / (clicks * 50).
    """
    if raw.get("platform") == "meta":
        freq = _float(raw, "meta_frequency", default=0)
        if freq > 0:
            return round(freq, 2)
    impressions = _float(raw, "impressions", "avg_daily_impressions", default=0)
    clicks = _float(raw, "clicks", default=0)
    if clicks > 0 and impressions > 0:
        estimated_reach = clicks * 50  # rough: 2% CTR = 50 impressions per clicker
        return round(min(impressions / estimated_reach, 10.0), 2)
    return 1.0


# ── Entry points ─────────────────────────────────────────────

def load_posthog_data(days: int = 7, platform: str = "all") -> dict:
    """Fetch campaign data from PostHog (Google + Meta), return converted dataclass lists.

    Args:
        days: Lookback window in days.
        platform: "all" (default), "google", or "meta".
    """
    raw = []
    if platform in ("all", "google"):
        raw.extend(fetch_campaign_data(days=days))
    if platform in ("all", "meta"):
        raw.extend(fetch_meta_campaign_data(days=days))
    return {
        "health": to_ad_health(raw),
        "guardian": to_ad_metrics(raw),
        "content_lab": to_ad_performance(raw),
        "copy_writer": to_ad_with_copy(raw),
        "raw": raw,
    }


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        if idx + 1 >= len(sys.argv):
            print("Usage: python3 posthog_fetch.py --query \"SELECT ...\"")
            sys.exit(1)
        result = run_hogql_query(sys.argv[idx + 1])
        print(json.dumps(result, indent=2, default=str))

    elif "--insight" in sys.argv:
        idx = sys.argv.index("--insight")
        if idx + 1 >= len(sys.argv):
            print("Usage: python3 posthog_fetch.py --insight <short_id>")
            sys.exit(1)
        result = get_insight_result(sys.argv[idx + 1])
        print(json.dumps(result, indent=2, default=str))

    else:
        days = 7
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            if idx + 1 < len(sys.argv):
                days = int(sys.argv[idx + 1])

        platform = "all"
        if "--meta-only" in sys.argv:
            platform = "meta"
        elif "--google-only" in sys.argv:
            platform = "google"

        data = load_posthog_data(days=days, platform=platform)
        google_count = sum(1 for c in data["raw"] if c.get("platform") == "google")
        meta_count = sum(1 for c in data["raw"] if c.get("platform") == "meta")
        print(f"\nCampaigns fetched: {len(data['raw'])} (Google: {google_count}, Meta: {meta_count})")
        print(f"  Health entries:    {len(data['health'])}")
        print(f"  Guardian entries:  {len(data['guardian'])}")
        print(f"  Content lab:       {len(data['content_lab'])}")
        print(f"  Copy writer:       {len(data['copy_writer'])}")
        print()
        for camp in data["raw"][:15]:
            plat = camp.get("platform", "?")[:6]
            status = camp.get("campaign_status", "?")
            name = camp.get("campaign_name", "?")[:55]
            spend = camp.get("spend", 0)
            cpa = camp.get("cpa", 0)
            ctr = camp.get("ctr", 0)
            print(f"  [{plat:6s}] [{status:8s}] {name:55s}  spend=INR {spend:>10,.2f}  CPA={cpa:>8,.2f}  CTR={ctr:.2f}%")
