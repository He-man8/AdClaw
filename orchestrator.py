"""
Orchestrator — runs all agents in sequence
---------------------------------------------
Coordinates: health_check → budget_guardian → copy_writer → content_lab → ad_publisher → morning_brief

Input : sample_data.csv, live Google Ads via Composio, or PostHog data warehouse
Output: paused bleeders, budget shifts, new copy, test hypotheses, staged ads, morning brief

Usage:
  python3 orchestrator.py                  # dry run, sample data
  python3 orchestrator.py --live           # live Google Ads via Composio (dry run publish)
  python3 orchestrator.py --posthog        # live Google Ads via PostHog data warehouse
  python3 orchestrator.py --posthog --publish  # PostHog data + actually publish ads
"""

import sys
from datetime import datetime, timezone

from config import settings
from health_check import load_sample_data as load_health_data, run_health_check
from budget_guardian import load_sample_data as load_guardian_data, run_budget_guardian, print_guardian_report
from copy_writer import load_winners_from_csv, generate_copy_variants, print_copy_report
from content_lab import load_all_ads, run_content_lab
from ad_publisher import run_publisher
from morning_brief import build_brief, deliver_brief


SAMPLE_FILE = "sample_data.csv"


def banner(step: int, title: str) -> None:
    print(f"\n{'━' * 60}")
    print(f"  STEP {step}: {title}")
    print(f"{'━' * 60}")


def run(live: bool = False, posthog: bool = False, dry_run: bool = True) -> None:
    start = datetime.now(timezone.utc)
    mode = "POSTHOG" if posthog else "LIVE" if live else "DRY RUN / SAMPLE DATA"
    print(f"\n🦞  ADCLAW AUTONOMOUS ADS AGENT  —  {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"    Mode: {mode}\n")

    # ── Pre-fetch live data ───────────────────────────────────────
    composio_data = None
    if posthog:
        from posthog_fetch import load_posthog_data
        print("  Fetching live data from Google Ads via PostHog...")
        composio_data = load_posthog_data()
        print(f"  Pulled {len(composio_data['raw'])} campaigns from PostHog.")
    elif live:
        from composio_fetch import load_composio_data
        print("  Fetching live data from Google Ads via Composio...")
        composio_data = load_composio_data()
        print(f"  Pulled {len(composio_data['raw'])} campaigns from Composio.")

    # ── Step 1: Health Check ─────────────────────────────────────
    banner(1, "DAILY HEALTH CHECK")
    if composio_data:
        ads_health = composio_data["health"]
        print(f"  Using {len(ads_health)} ads from Composio.")
    else:
        ads_health = load_health_data(SAMPLE_FILE)
        print(f"  Loaded {len(ads_health)} ads from {SAMPLE_FILE}.")

    health_report = run_health_check(ads_health, live=live)

    danger_ads = health_report["danger"]
    freq_dicts = [
        {
            "ad_id": a["ad_id"],
            "ad_name": a["ad_name"],
            "frequency": a["frequency"],
            "ctr": a["ctr"],
            "cpa": a["cpa"],
        }
        for a in danger_ads
    ]

    # ── Step 2: Budget Guardian ──────────────────────────────────
    banner(2, "AUTO-PAUSE BLEEDERS + SHIFT BUDGET")
    ads_guardian = composio_data["guardian"] if composio_data else load_guardian_data(SAMPLE_FILE)
    guardian_result = run_budget_guardian(ads_guardian, dry_run=dry_run)
    print_guardian_report(guardian_result, ads_guardian)

    guardian_brief = {
        "paused": [
            {
                "ad_name": a.ad_name,
                "cpa": a.cpa,
                "target_cpa": a.target_cpa,
            }
            for a in guardian_result["paused"]
        ],
        "shifts": guardian_result["shifts"],
    }

    # ── Step 3: Copy Generation ──────────────────────────────────
    banner(3, "WRITE NEW AD COPY FROM WINNERS")
    winners = composio_data["copy_writer"] if composio_data else load_winners_from_csv(SAMPLE_FILE)
    variants = generate_copy_variants(winners)
    # Content Lab now owns hypothesis generation — skip copy_writer concepts
    print_copy_report(winners, variants, [])

    # ── Step 4: Content Lab ──────────────────────────────────────
    banner(4, "CONTENT LAB — PATTERN ANALYSIS")
    all_ads = composio_data["content_lab"] if composio_data else load_all_ads(SAMPLE_FILE)
    lab_result = run_content_lab(all_ads)

    # ── Step 5: Upload Staged Ads ────────────────────────────────
    banner(5, "STAGE ADS FOR UPLOAD")
    adset_id = settings.meta_adset_id
    page_id = settings.meta_page_id
    upload_results = run_publisher(
        adset_id=adset_id,
        page_id=page_id,
        dry_run=dry_run,
    )

    # ── Step 6: Morning Brief ────────────────────────────────────
    banner(6, "MORNING BRIEF — DELIVER SUMMARY")

    # load health history for WoW comparison
    import json as _json
    from pathlib import Path as _Path
    _history_path = _Path("output/health_history.json")
    _health_history = _json.loads(_history_path.read_text()) if _history_path.exists() else None

    brief = build_brief(
        frequency_results=freq_dicts,
        guardian_results=guardian_brief,
        copy_variants=variants,
        content_concepts=lab_result.get("hypotheses", []),
        upload_results=upload_results,
        health_report=health_report,
        health_history=_health_history,
    )
    deliver_brief(brief)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    print(f"\n✅  Agent run complete in {elapsed:.1f}s\n")


if __name__ == "__main__":
    live = "--live" in sys.argv
    posthog = "--posthog" in sys.argv
    dry_run = "--publish" not in sys.argv
    run(live=live, posthog=posthog, dry_run=dry_run)
