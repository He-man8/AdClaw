"""
Step 5: Upload Ads Directly to Meta Ads Manager
-------------------------------------------------
- Reads generated_copy.json from copy_writer.py
- Creates ad creative + ad via social-flow CLI
- New ads start PAUSED by default — agent notifies you for approval
- Reply "approved" to activate
"""

import json
import subprocess
from pathlib import Path

from config import settings


COPY_FILE      = Path("generated_copy.json")
UPLOAD_LOG     = Path("upload_log.json")
DEFAULT_STATUS = "PAUSED"   # safety: always start paused, activate after review


def load_copy(filepath: Path = COPY_FILE) -> list[dict]:
    if not filepath.exists():
        raise FileNotFoundError(
            f"{filepath} not found. Run copy_writer.py first."
        )
    data = json.loads(filepath.read_text())
    # support both flat list and {"variants": [...], "concepts": [...]}
    return data["variants"] if isinstance(data, dict) else data


def load_upload_log() -> list[dict]:
    if UPLOAD_LOG.exists():
        return json.loads(UPLOAD_LOG.read_text())
    return []


def save_upload_log(log: list[dict]) -> None:
    UPLOAD_LOG.write_text(json.dumps(log, indent=2))


def publish_ad(
    variant: dict,
    adset_id: str,
    page_id: str,
    dry_run: bool = True,
) -> dict:
    """
    Creates a creative + ad via social-flow CLI.
    dry_run=True: prints the commands without executing.
    """
    creative_cmd = [
        "social", "marketing", "creative", "create",
        "--page-id",  page_id,
        "--headline", variant["headline"],
        "--body",     variant["body"],
        "--cta",      variant["cta"],
    ]
    ad_cmd_template = [
        "social", "marketing", "ad", "create",
        "--adset-id",    adset_id,
        "--creative-id", "{creative_id}",   # filled after creative creation
        "--status",      DEFAULT_STATUS,
    ]

    result = {
        "variant": variant["variant"],
        "hook_type": variant["hook_type"],
        "headline": variant["headline"],
        "status": DEFAULT_STATUS,
        "adset_id": adset_id,
        "creative_id": None,
        "ad_id": None,
        "dry_run": dry_run,
    }

    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(creative_cmd)}")
        result["creative_id"] = "creative_mock_id"
        result["ad_id"] = f"ad_mock_{variant['variant']}"
    else:
        # create creative, capture returned creative_id
        creative_out = subprocess.run(
            creative_cmd, capture_output=True, text=True, check=True
        )
        creative_data = json.loads(creative_out.stdout)
        creative_id = creative_data["id"]
        result["creative_id"] = creative_id

        # create ad using the new creative
        ad_cmd = [c if c != "{creative_id}" else creative_id for c in ad_cmd_template]
        ad_out = subprocess.run(
            ad_cmd, capture_output=True, text=True, check=True
        )
        ad_data = json.loads(ad_out.stdout)
        result["ad_id"] = ad_data["id"]

    return result


def activate_ad(ad_id: str, dry_run: bool = True) -> None:
    """Activate a staged ad after human approval."""
    if dry_run or ad_id.startswith("ad_mock_"):
        print(f"  [DRY RUN] Would activate {ad_id} → ACTIVE")
        print(f"  [ACTIVATED] {ad_id} (simulated — no live API credentials)")
        return

    subprocess.run(
        ["social", "marketing", "ad", "update",
         "--ad-id", ad_id, "--status", "ACTIVE"],
        check=True,
    )
    print(f"  [ACTIVATED] {ad_id}")


def run_publisher(
    adset_id: str = "YOUR_ADSET_ID",
    page_id: str  = "YOUR_PAGE_ID",
    dry_run: bool = True,
) -> list[dict]:
    variants = load_copy()
    log      = load_upload_log()
    results  = []

    print("\n" + "=" * 60)
    print("  AD PUBLISHER")
    print("=" * 60)
    print(f"  Mode     : {'DRY RUN — no changes made' if dry_run else 'LIVE'}")
    print(f"  Ad Set   : {adset_id}")
    print(f"  Variants : {len(variants)}")
    print("-" * 60)

    for v in variants:
        result = publish_ad(v, adset_id, page_id, dry_run=dry_run)
        results.append(result)
        log.append(result)

        status_icon = "🟡" if result["status"] == "PAUSED" else "🟢"
        print(f"\n  {status_icon} Variant {v['variant']} — {v['hook_type'].upper()}")
        print(f"    Headline   : {v['headline']}")
        print(f"    Ad ID      : {result['ad_id']}")
        print(f"    Status     : {result['status']} (awaiting approval)")

    save_upload_log(log)

    print(f"\n  Staged {len(results)} ads — all PAUSED pending approval.")
    print(f"  To activate, run: python3 ad_publisher.py --activate <ad_id>")
    print("=" * 60 + "\n")

    return results


if __name__ == "__main__":
    import sys

    live = "--live" in sys.argv

    # simple activate flow: python3 ad_publisher.py --activate <ad_id>
    if len(sys.argv) >= 3 and sys.argv[1] == "--activate":
        activate_ad(sys.argv[2], dry_run=not live)
    else:
        run_publisher(
            adset_id=settings.meta_adset_id,
            page_id=settings.meta_page_id,
            dry_run=not live,
        )
