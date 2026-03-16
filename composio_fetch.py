"""
Composio Google Ads Integration — MCP Protocol
------------------------------------------------
Connects to Google Ads via Composio's MCP server using JSON-RPC
over Streamable HTTP (SSE responses).

Modes:
  python3 composio_fetch.py                                    # fetch customer lists
  python3 composio_fetch.py --directive "list all campaigns"   # LLM agent mode
  python3 composio_fetch.py --tool GET_CAMPAIGN_BY_ID --args '{"id": "123"}'

All tool execution is gated to read-only operations.
"""

import json
import logging
import sys
from typing import Any

import requests

from config import settings

logger = logging.getLogger(__name__)

# ── Read-only safety gate ────────────────────────────────────────────

BLOCKED_VERBS = {"CREATE", "ADD", "REMOVE", "DELETE", "UPDATE", "INSERT", "MODIFY"}


def is_read_only(slug: str) -> bool:
    """Return True if the tool slug is a read-only operation."""
    parts = slug.upper().replace("-", "_").split("_")
    return not any(verb in parts for verb in BLOCKED_VERBS)


# ── MCP client ───────────────────────────────────────────────────────

_request_id = 0


def _next_id() -> int:
    global _request_id
    _request_id += 1
    return _request_id


def mcp_call(tool_name: str, arguments: dict | None = None) -> Any:
    """
    Call a Composio MCP tool via JSON-RPC over Streamable HTTP.

    The response is SSE — we parse the first `data:` line containing
    a `result` key and return that value.
    """
    settings.require_composio()

    if not is_read_only(tool_name):
        raise PermissionError(
            f"Blocked write operation: {tool_name}. "
            "Only read-only Google Ads tools are allowed."
        )

    body = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments or {}},
    }
    headers = {
        "x-api-key": settings.composio_mcp_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    r = requests.post(settings.composio_mcp_url, headers=headers, json=body, timeout=30)
    r.raise_for_status()

    # Parse SSE response — find first data: line with a result
    for line in r.text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            if "result" in payload:
                return payload["result"]
            if "error" in payload:
                error = payload["error"]
                msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                raise RuntimeError(f"MCP error: {msg}")

    raise RuntimeError("No data in Composio MCP response")


# ── Tool map (Gemini function names → Composio slugs) ────────────────

TOOL_MAP = {
    "googleads_get_campaign_by_id": "GOOGLEADS_GET_CAMPAIGN_BY_ID",
    "googleads_get_campaign_by_name": "GOOGLEADS_GET_CAMPAIGN_BY_NAME",
    "googleads_get_customer_lists": "GOOGLEADS_GET_CUSTOMER_LISTS",
}


# ── High-level fetch functions ────────────────────────────────────────

def get_customer_lists() -> Any:
    """Fetch all Google Ads customer/audience lists."""
    return mcp_call("GOOGLEADS_GET_CUSTOMER_LISTS")


def get_campaign_by_id(campaign_id: str) -> Any:
    """Fetch a single campaign by ID."""
    return mcp_call("GOOGLEADS_GET_CAMPAIGN_BY_ID", {"id": campaign_id})


def get_campaign_by_name(name: str) -> Any:
    """Fetch a campaign by name."""
    return mcp_call("GOOGLEADS_GET_CAMPAIGN_BY_NAME", {"name": name})


# ── LLM-driven tool execution (directive agent) ──────────────────────

def interpret_directive(directive: str) -> dict:
    """
    Use Gemini to interpret a natural-language directive, pick the right
    Google Ads tool, and execute it via the Composio MCP server.
    """
    from google import genai

    settings.require_composio()

    gemini_client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""You are a Google Ads data assistant. The user wants:

"{directive}"

Available read-only tools:
- GOOGLEADS_GET_CAMPAIGN_BY_ID: Fetch full details of a Google Ads campaign by its campaign ID. Args: {{"id": "<campaign_id>"}}
- GOOGLEADS_GET_CAMPAIGN_BY_NAME: Search for a Google Ads campaign by its name. Args: {{"name": "<campaign_name>"}}
- GOOGLEADS_GET_CUSTOMER_LISTS: List all Google Ads customer/audience lists. Args: {{}}

Pick the best tool and construct the arguments. Respond with ONLY valid JSON:
{{"slug": "TOOL_SLUG", "arguments": {{...}}}}

IMPORTANT RULES:
- For general requests about campaigns or ads (e.g. "tell me about my campaigns", "how are my ads"), use GOOGLEADS_GET_CUSTOMER_LISTS with {{}} — this returns account-level data including campaigns.
- For requests about a specific campaign by name, use GOOGLEADS_GET_CAMPAIGN_BY_NAME.
- For requests about a specific campaign by ID, use GOOGLEADS_GET_CAMPAIGN_BY_ID.
- ALWAYS pick a tool. Do NOT respond with slug: null.
"""

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    try:
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        selection = json.loads(text)
    except (json.JSONDecodeError, AttributeError) as e:
        return {"tool_results": [], "error": f"LLM response parse error: {e}"}

    slug = selection.get("slug")
    if not slug:
        return {"tool_results": [], "error": "LLM did not select a tool"}

    arguments = selection.get("arguments", {})

    try:
        result = mcp_call(slug, arguments)
        return {"tool_results": [result], "error": None}
    except Exception as e:
        return {"tool_results": [], "error": str(e)}


# ── Pipeline data fetch (used by orchestrator.py --live) ──────────────

def fetch_campaign_data() -> list[dict]:
    """
    Fetch campaign data from Google Ads via Composio MCP.
    Calls GET_CUSTOMER_LISTS to get account-level data.
    """
    settings.require_composio()

    try:
        result = mcp_call("GOOGLEADS_GET_CUSTOMER_LISTS")
        logger.info("Customer lists response: %s", result)

        # Normalize to list of dicts
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            # Check for nested data
            data = result.get("data", result.get("content", result))
            if isinstance(data, list):
                return data
            return [data]
        return [result] if result else []
    except Exception as e:
        logger.error("Failed to fetch campaign data: %s", e)
        return []


# ── Dataclass converters ─────────────────────────────────────────────

def _get(raw: dict, *keys, default=None):
    """Try multiple key names, return first match or default."""
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
    """Convert raw campaign data to AdHealth dataclass instances."""
    from health_check import AdHealth

    results = []
    for raw in raw_campaigns:
        results.append(AdHealth(
            ad_id=str(_get(raw, "id", "campaign_id", "resourceName", default="unknown")),
            ad_name=str(_get(raw, "name", "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "name", "campaign_name", default="Unknown")),
            frequency=_float(raw, "frequency", default=1.0),
            ctr=_float(raw, "ctr", "clickThroughRate", default=0.0),
            cpa=_float(raw, "cpa", "costPerConversion", "cost_per_conversion", default=0.0),
            target_cpa=_float(raw, "target_cpa", "targetCpa", "target_cpa_micros", default=0.0),
            spend=_float(raw, "spend", "cost", "costMicros", "amount_spent", default=0.0),
            daily_budget=_float(raw, "daily_budget", "budget", "budgetAmountMicros", default=0.0),
        ))
    return results


def to_ad_metrics(raw_campaigns: list[dict]) -> list:
    """Convert raw campaign data to AdMetrics dataclass instances."""
    from budget_guardian import AdMetrics

    results = []
    for raw in raw_campaigns:
        results.append(AdMetrics(
            ad_id=str(_get(raw, "id", "campaign_id", "resourceName", default="unknown")),
            ad_name=str(_get(raw, "name", "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "name", "campaign_name", default="Unknown")),
            cpa=_float(raw, "cpa", "costPerConversion", "cost_per_conversion", default=0.0),
            target_cpa=_float(raw, "target_cpa", "targetCpa", default=0.0),
            spend=_float(raw, "spend", "cost", "costMicros", default=0.0),
            daily_budget=_float(raw, "daily_budget", "budget", "budgetAmountMicros", default=100.0),
            ctr=_float(raw, "ctr", "clickThroughRate", default=0.0),
            frequency=_float(raw, "frequency", default=1.0),
            roas=_float(raw, "roas", "returnOnAdSpend", default=0.0),
        ))
    return results


def to_ad_performance(raw_campaigns: list[dict]) -> list:
    """Convert raw campaign data to AdPerformance dataclass instances."""
    from content_lab import AdPerformance

    results = []
    for raw in raw_campaigns:
        results.append(AdPerformance(
            ad_id=str(_get(raw, "id", "campaign_id", "resourceName", default="unknown")),
            ad_name=str(_get(raw, "name", "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "name", "campaign_name", default="Unknown")),
            ad_format=str(_get(raw, "ad_format", "type", "advertisingChannelType", default="UNKNOWN")),
            ctr=_float(raw, "ctr", "clickThroughRate", default=0.0),
            cpa=_float(raw, "cpa", "costPerConversion", default=0.0),
            target_cpa=_float(raw, "target_cpa", "targetCpa", default=0.0),
            frequency=_float(raw, "frequency", default=1.0),
            spend=_float(raw, "spend", "cost", "costMicros", default=0.0),
            headline=str(_get(raw, "headline", default="(no headline)")),
            body=str(_get(raw, "body", "description", default="(no body)")),
            cta=str(_get(raw, "cta", "callToAction", default="Learn More")),
        ))
    return results


def to_ad_with_copy(raw_campaigns: list[dict]) -> list:
    """Convert raw campaign data to AdWithCopy dataclass instances."""
    from copy_writer import AdWithCopy

    results = []
    for raw in raw_campaigns:
        results.append(AdWithCopy(
            ad_id=str(_get(raw, "id", "campaign_id", "resourceName", default="unknown")),
            ad_name=str(_get(raw, "name", "campaign_name", default="Unknown Campaign")),
            campaign=str(_get(raw, "name", "campaign_name", default="Unknown")),
            ctr=_float(raw, "ctr", "clickThroughRate", default=0.0),
            cpa=_float(raw, "cpa", "costPerConversion", default=0.0),
            target_cpa=_float(raw, "target_cpa", "targetCpa", default=0.0),
            headline=str(_get(raw, "headline", default="(no headline)")),
            body=str(_get(raw, "body", "description", default="(no body)")),
            cta=str(_get(raw, "cta", "callToAction", default="Learn More")),
        ))
    return results


# ── Entry point for orchestrator ─────────────────────────────────────

def load_composio_data() -> dict:
    """Fetch all campaign data, return converted dataclass lists."""
    raw = fetch_campaign_data()
    return {
        "health": to_ad_health(raw),
        "guardian": to_ad_metrics(raw),
        "content_lab": to_ad_performance(raw),
        "copy_writer": to_ad_with_copy(raw),
        "raw": raw,
    }


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if "--directive" in sys.argv:
        idx = sys.argv.index("--directive")
        if idx + 1 >= len(sys.argv):
            print("Usage: python3 composio_fetch.py --directive \"<your request>\"")
            sys.exit(1)
        directive = sys.argv[idx + 1]
        result = interpret_directive(directive)
        print(json.dumps(result, indent=2, default=str))

    elif "--tool" in sys.argv:
        idx = sys.argv.index("--tool")
        if idx + 1 >= len(sys.argv):
            print("Usage: python3 composio_fetch.py --tool TOOL_SLUG [--args '{...}']")
            sys.exit(1)
        tool_slug = sys.argv[idx + 1]
        args = {}
        if "--args" in sys.argv:
            args_idx = sys.argv.index("--args")
            if args_idx + 1 < len(sys.argv):
                args = json.loads(sys.argv[args_idx + 1])
        try:
            result = mcp_call(tool_slug, args)
            print(json.dumps(result, indent=2, default=str))
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2))

    else:
        result = get_customer_lists()
        print(json.dumps(result, indent=2, default=str))
