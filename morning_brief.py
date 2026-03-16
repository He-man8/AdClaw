"""
Morning Brief Agent
--------------------
- Assembles output from all agents into a concise 90-second brief
- Includes: paused ads, budget shifts, fatigue alerts, trending frequency,
  CTR decay, new copy, content hypotheses, WoW comparison, upload queue
- Delivers to Telegram / stdout (OpenClaw captures stdout natively)
"""

import json
import sys
import urllib.request

from config import settings
from datetime import datetime, timezone
from pathlib import Path


BRIEF_LOG = Path("brief_log.jsonl")
HEALTH_REPORT = Path("output/health_report.json")
HEALTH_HISTORY = Path("output/health_history.json")
HYPOTHESES_FILE = Path("output/content_hypotheses.json")


def load_json(path: str | Path) -> dict | list | None:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return None


def _wow_comparison(history: dict) -> dict | None:
    """Week-over-week comparison from health history snapshots."""
    snapshots = history.get("snapshots", [])
    if len(snapshots) < 2:
        return None

    current = snapshots[-1]["ads"]
    # use earliest available as "previous" (best we can do with sample data)
    previous = snapshots[0]["ads"]

    curr_spend = sum(ad.get("cpa", 0) for ad in current.values())
    prev_spend = sum(ad.get("cpa", 0) for ad in previous.values())

    # aggregate CTR
    curr_ctrs = [ad["ctr"] for ad in current.values() if ad.get("ctr", 0) > 0]
    prev_ctrs = [ad["ctr"] for ad in previous.values() if ad.get("ctr", 0) > 0]

    avg_curr_ctr = sum(curr_ctrs) / len(curr_ctrs) if curr_ctrs else 0
    avg_prev_ctr = sum(prev_ctrs) / len(prev_ctrs) if prev_ctrs else 0

    # aggregate CPA (non-zero only, skip awareness)
    curr_cpas = [ad["cpa"] for ad in current.values() if ad.get("cpa", 0) > 0]
    prev_cpas = [ad["cpa"] for ad in previous.values() if ad.get("cpa", 0) > 0]

    avg_curr_cpa = sum(curr_cpas) / len(curr_cpas) if curr_cpas else 0
    avg_prev_cpa = sum(prev_cpas) / len(prev_cpas) if prev_cpas else 0

    def pct_change(curr: float, prev: float) -> str:
        if prev == 0:
            return "N/A"
        change = ((curr - prev) / prev) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.1f}%"

    return {
        "avg_ctr": avg_curr_ctr,
        "avg_ctr_change": pct_change(avg_curr_ctr, avg_prev_ctr),
        "avg_cpa": avg_curr_cpa,
        "avg_cpa_change": pct_change(avg_curr_cpa, avg_prev_cpa),
        "snapshots_compared": len(snapshots),
    }


def build_brief(
    frequency_results: list[dict] | None = None,
    guardian_results: dict | None = None,
    copy_variants: list[dict] | None = None,
    content_concepts: list[dict] | None = None,
    upload_results: list[dict] | None = None,
    health_report: dict | None = None,
    health_history: dict | None = None,
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
            for ad in danger[:5]:
                lines.append(
                    f"  • {ad['ad_name']} | freq {ad['frequency']:.2f} | CTR {ad['ctr']:.2f}%"
                )
            lines.append("")

    # --- trending frequency (from health report) ---
    trending = (health_report or {}).get("trending_up", [])
    if trending:
        lines.append("📈 *FREQUENCY TRENDING UP*")
        for t in trending[:3]:
            lines.append(
                f"  • {t['ad_name']} | freq {t['from']:.2f} → {t['to']:.2f} (+{t['delta']:.2f})"
            )
        lines.append("")

    # --- CTR decay (from health report) ---
    decaying = (health_report or {}).get("ctr_decaying", [])
    if decaying:
        lines.append("📉 *CTR DECAYING*")
        for d in decaying[:3]:
            lines.append(
                f"  • {d['ad_name']} | CTR {d['prior_avg_ctr']:.2f}% → {d['current_ctr']:.2f}% (↓{d['decay_pct']:.1f}%)"
            )
        lines.append("")

    # --- new copy ready ---
    if copy_variants:
        lines.append(f"✍️ *NEW COPY READY* — {len(copy_variants)} variants generated")
        for v in copy_variants[:2]:
            lines.append(f"  • [{v['hook_type']}] \"{v['headline']}\"")
        lines.append("")

    # --- content hypotheses (from Content Lab, replaces old concepts) ---
    if content_concepts:
        lines.append(f"💡 *WHAT TO TEST NEXT* — {len(content_concepts)} hypotheses")
        for c in content_concepts[:3]:
            lines.append(f"  • [{c['format'].upper()}] {c['test']}")
        lines.append("")

    # --- week-over-week ---
    if health_history:
        wow = _wow_comparison(health_history)
        if wow and wow["snapshots_compared"] >= 2:
            lines.append("📊 *WEEK-OVER-WEEK*")
            lines.append(f"  • Avg CTR: {wow['avg_ctr']:.2f}% ({wow['avg_ctr_change']})")
            lines.append(f"  • Avg CPA: ${wow['avg_cpa']:.2f} ({wow['avg_cpa_change']})")
            lines.append(f"  • Data points: {wow['snapshots_compared']} snapshots")
            lines.append("")

    # --- spend at risk ---
    spend_at_risk = (health_report or {}).get("spend_at_risk", 0)
    if spend_at_risk > 0:
        lines.append(f"💸 *Spend at risk: ${spend_at_risk:,.0f}*")
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
    if not settings.has_telegram:
        return False
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
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
        print(message)

    with open(BRIEF_LOG, "a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "brief": message,
        }) + "\n")


if __name__ == "__main__":
    from_pipeline = "--from-pipeline" in sys.argv

    # load all available output files
    health_report = load_json(HEALTH_REPORT)
    health_history = load_json(HEALTH_HISTORY)
    saved_copy = load_json("generated_copy.json") or {}
    copy_variants = saved_copy.get("variants") if isinstance(saved_copy, dict) else saved_copy
    upload_results = load_json("upload_log.json")

    # content hypotheses from Content Lab (replaces old copy_writer concepts)
    content_hypotheses = load_json(HYPOTHESES_FILE)

    # frequency results from health report
    freq_results = None
    if isinstance(health_report, dict):
        freq_results = health_report.get("danger", [])

    brief = build_brief(
        frequency_results=freq_results,
        guardian_results=None,  # populated by orchestrator when in pipeline
        copy_variants=copy_variants,
        content_concepts=content_hypotheses,
        upload_results=upload_results,
        health_report=health_report if isinstance(health_report, dict) else None,
        health_history=health_history if isinstance(health_history, dict) else None,
    )
    deliver_brief(brief)
