"""
Step 6: Morning Brief Assembler
---------------------------------
- Assembles output from all previous steps into a concise brief
- Prints to stdout — OpenClaw reads this and delivers it via
  WhatsApp / Telegram / Slack natively (no manual delivery needed)
- 90 seconds to read. Reply "approved" to publish staged ads.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BRIEF_LOG = Path("brief_log.jsonl")


def load_json(path: str) -> list[dict] | None:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return None


def build_brief(
    frequency_results: list[dict] | None = None,
    guardian_results: dict | None = None,
    copy_variants: list[dict] | None = None,
    content_concepts: list[dict] | None = None,
    upload_results: list[dict] | None = None,
) -> str:
    today = datetime.now(timezone.utc).strftime("%a %d %b %Y")
    lines = [f"📊 *DAILY ADS BRIEF — {today}*", ""]

    # --- paused ads ---
    paused = (guardian_results or {}).get("paused", [])
    if paused:
        lines.append("🔴 *AUTO-PAUSED*")
        for ad in paused:
            lines.append(
                f"  • {ad['ad_name']} | CPA ${ad['cpa']:.2f} vs ${ad['target_cpa']:.2f} target"
            )
        lines.append("")

    # --- budget shifts ---
    shifts = (guardian_results or {}).get("shifts", [])
    if shifts:
        lines.append("💰 *BUDGET SHIFTED*")
        for s in shifts:
            lines.append(
                f"  • +${s['shift_amount']:.0f}/day → {s['ad_name']} (score: {s['efficiency_score']})"
            )
        lines.append("")

    # --- frequency alerts ---
    if frequency_results:
        danger = [a for a in frequency_results if a.get("frequency", 0) >= 3.5]
        if danger:
            lines.append("⚠️ *FATIGUE ALERTS* (freq > 3.5)")
            for ad in danger[:3]:
                lines.append(
                    f"  • {ad['ad_name']} | freq {ad['frequency']:.2f} | CTR {ad['ctr']:.2f}%"
                )
            lines.append("")

    # --- new copy ready ---
    if copy_variants:
        lines.append(f"✍️ *NEW COPY READY* — {len(copy_variants)} variants generated")
        for v in copy_variants[:2]:
            lines.append(f"  • [{v['hook_type']}] \"{v['headline']}\"")
        lines.append("")

    # --- content concepts ---
    if content_concepts:
        lines.append(f"💡 *WHAT TO TEST NEXT* — {len(content_concepts)} hypotheses")
        for c in content_concepts:
            lines.append(f"  • [{c['format'].upper()}] {c['test']}")
        lines.append("")

    # --- upload queue ---
    if upload_results:
        staged = [r for r in upload_results if r.get("status") == "PAUSED"]
        if staged:
            lines.append(f"📦 *UPLOAD QUEUE* — {len(staged)} ads staged, awaiting approval")
            lines.append("  Reply *approved* to publish all staged ads.")
            lines.append("")

    lines.append("_Reply *approved* to publish · *skip* to defer_")
    return "\n".join(lines)


def _send_telegram(message: str) -> bool:
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Telegram error] {e}")
        return False


def deliver_brief(message: str) -> None:
    sent = _send_telegram(message)
    if sent:
        print("  [OK] Brief sent to Telegram")
    else:
        # fallback: print to stdout (OpenClaw captures this)
        print(message)

    # audit log
    with open(BRIEF_LOG, "a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "brief": message,
        }) + "\n")


if __name__ == "__main__":
    saved         = load_json("generated_copy.json") or {}
    copy_variants = saved.get("variants") if isinstance(saved, dict) else saved
    concepts      = saved.get("concepts") if isinstance(saved, dict) else None
    upload_results = load_json("upload_log.json")

    brief = build_brief(
        frequency_results=None,    # populated by orchestrator
        guardian_results=None,     # populated by orchestrator
        copy_variants=copy_variants,
        content_concepts=concepts,
        upload_results=upload_results,
    )
    deliver_brief(brief)
