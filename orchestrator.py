"""
Orchestrator — runs all 6 steps in sequence
---------------------------------------------
Input : sample_data.csv (or live Meta API)
Output: paused bleeders, budget shifts, new copy, staged ads, morning brief

Usage:
  python3 orchestrator.py               # dry run, sample data
  python3 orchestrator.py --live        # live Meta API + real actions
"""

import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()  # loads .env from current directory

# local modules
from frequency_monitor import load_sample_data as load_freq_data, run_frequency_audit
from budget_guardian    import load_sample_data as load_guardian_data, run_budget_guardian, print_guardian_report
from copy_writer        import load_winners_from_csv, generate_copy_variants, generate_content_concepts, print_copy_report
from ad_publisher       import run_publisher
from morning_brief      import build_brief, deliver_brief


SAMPLE_FILE = "sample_data.csv"


def banner(step: int, title: str) -> None:
    print(f"\n{'━' * 60}")
    print(f"  STEP {step}: {title}")
    print(f"{'━' * 60}")


def run(live: bool = False, dry_run: bool = True) -> None:
    start = datetime.now(timezone.utc)
    print(f"\n🦞  OPENCLAW ADS AGENT  —  {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"    Mode: {'LIVE' if live else 'DRY RUN / SAMPLE DATA'}\n")

    # ── Step 1: Load data ──────────────────────────────────────────
    banner(1, "DAILY HEALTH CHECK — LOAD AD DATA")
    if live:
        from frequency_monitor import load_meta_api_data
        ads_freq = load_meta_api_data(
            ad_account_id=os.environ["META_AD_ACCOUNT_ID"],
            access_token=os.environ["META_ACCESS_TOKEN"],
        )
        print(f"  Pulled {len(ads_freq)} ads from Meta API.")
    else:
        ads_freq = load_freq_data(SAMPLE_FILE)
        print(f"  Loaded {len(ads_freq)} ads from {SAMPLE_FILE}.")

    # ── Step 2: Frequency audit ────────────────────────────────────
    banner(2, "CATCH DYING ADS — FREQUENCY MONITOR")
    run_frequency_audit(ads_freq)

    danger_ads = [a for a in ads_freq if a.is_audience_cooked]
    freq_dicts = [
        {
            "ad_id": a.ad_id,
            "ad_name": a.ad_name,
            "frequency": a.frequency,
            "ctr": a.ctr,
            "cpa": a.cpa,
        }
        for a in danger_ads
    ]

    # ── Step 3: Budget guardian ────────────────────────────────────
    banner(3, "AUTO-PAUSE BLEEDERS + SHIFT BUDGET")
    ads_guardian = load_guardian_data(SAMPLE_FILE)
    guardian_result = run_budget_guardian(ads_guardian, dry_run=dry_run)
    print_guardian_report(guardian_result, ads_guardian)

    # serialise dataclass list for brief
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

    # ── Step 4: Copy generation + content concepts ─────────────────
    banner(4, "WRITE NEW AD COPY FROM WINNERS")
    winners  = load_winners_from_csv(SAMPLE_FILE)
    variants = generate_copy_variants(winners)
    concepts = generate_content_concepts(winners)
    print_copy_report(winners, variants, concepts)

    # ── Step 5: Upload staged ads ──────────────────────────────────
    banner(5, "STAGE ADS FOR UPLOAD")
    adset_id = os.getenv("META_ADSET_ID", "YOUR_ADSET_ID")
    page_id  = os.getenv("META_PAGE_ID",  "YOUR_PAGE_ID")
    upload_results = run_publisher(
        adset_id=adset_id,
        page_id=page_id,
        dry_run=dry_run,
    )

    # ── Step 6: Morning brief ──────────────────────────────────────
    banner(6, "MORNING BRIEF — DELIVER SUMMARY")
    brief = build_brief(
        frequency_results=freq_dicts,
        guardian_results=guardian_brief,
        copy_variants=variants,
        content_concepts=concepts,
        upload_results=upload_results,
    )
    deliver_brief(brief)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    print(f"\n✅  Agent run complete in {elapsed:.1f}s\n")


if __name__ == "__main__":
    live     = "--live"     in sys.argv
    dry_run  = "--live" not in sys.argv   # live mode applies real actions
    run(live=live, dry_run=dry_run)
