"""
Step 3: Auto-Pause Bleeders + Shift Budget to Winners
------------------------------------------------------
- CPA > 2.5x target for 48h consecutive → auto-pause
- Ranks campaigns by efficiency
- Recommends shifting freed budget to top performer
- Max +20% budget increase per 48h (protects Meta learning phase)
- Logs every action with reason + timestamp
"""

import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path


# --- Config ---
CPA_PAUSE_MULTIPLIER = 2.5       # pause if CPA > 2.5x target
PAUSE_WINDOW_HOURS   = 48        # must exceed threshold for this long
MAX_BUDGET_SCALE_PCT = 0.20      # never scale more than 20% per cycle
MAX_PAUSES_PER_RUN   = 3         # safety: never nuke everything at once
STATE_FILE           = Path("state.json")
LOG_FILE             = Path("guardian_log.jsonl")


@dataclass
class AdMetrics:
    ad_id: str
    ad_name: str
    campaign: str
    cpa: float
    target_cpa: float
    spend: float
    daily_budget: float
    ctr: float
    frequency: float
    roas: float = 0.0

    @property
    def cpa_ratio(self) -> float:
        return self.cpa / self.target_cpa if self.target_cpa else 0

    @property
    def is_awareness(self) -> bool:
        return self.target_cpa == 0

    @property
    def is_bleeding(self) -> bool:
        # awareness campaigns have no CPA target — never auto-pause them
        if self.is_awareness:
            return False
        return self.cpa_ratio >= CPA_PAUSE_MULTIPLIER

    @property
    def efficiency_score(self) -> float:
        """Lower CPA ratio + higher CTR = better score. Used to rank winners."""
        cpa_component = max(0, 2.0 - self.cpa_ratio) * 60
        ctr_component = min(self.ctr / 2.0, 1.0) * 40
        return round(cpa_component + ctr_component, 2)


# --- State management (48h tracker) ---

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"ads": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def update_cpa_history(state: dict, ad: AdMetrics) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    if ad.ad_id not in state["ads"]:
        state["ads"][ad.ad_id] = {"cpa_history": [], "status": "active"}

    state["ads"][ad.ad_id]["cpa_history"].append({
        "ts": now,
        "cpa": ad.cpa,
        "target_cpa": ad.target_cpa,
        "is_bleeding": ad.is_bleeding,
    })

    # keep only last 7 days of records
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    state["ads"][ad.ad_id]["cpa_history"] = [
        r for r in state["ads"][ad.ad_id]["cpa_history"] if r["ts"] >= cutoff
    ]
    return state


def has_been_bleeding_48h(state: dict, ad_id: str) -> bool:
    """Returns True if every recorded CPA check in the last 48h was bleeding."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=PAUSE_WINDOW_HOURS)).isoformat()
    history = state.get("ads", {}).get(ad_id, {}).get("cpa_history", [])
    recent = [r for r in history if r["ts"] >= cutoff]
    if len(recent) < 2:
        return False   # need at least 2 data points
    return all(r["is_bleeding"] for r in recent)


# --- Action logger ---

def log_action(action: str, ad: AdMetrics, reason: str, extra: dict | None = None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "ad_id": ad.ad_id,
        "ad_name": ad.ad_name,
        "campaign": ad.campaign,
        "reason": reason,
        **(extra or {}),
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"  [LOG] {action} | {ad.ad_name} | {reason}")


# --- Core logic ---

def decide_pauses(ads: list[AdMetrics], state: dict) -> list[AdMetrics]:
    """Return ads that should be paused this run."""
    to_pause = []
    for ad in ads:
        if state.get("ads", {}).get(ad.ad_id, {}).get("status") == "paused":
            continue
        if ad.is_bleeding and has_been_bleeding_48h(state, ad.ad_id):
            to_pause.append(ad)

    # safety cap
    to_pause.sort(key=lambda a: a.cpa_ratio, reverse=True)
    return to_pause[:MAX_PAUSES_PER_RUN]


def recommend_budget_shifts(
    ads: list[AdMetrics],
    paused: list[AdMetrics],
    state: dict,
) -> list[dict]:
    """
    Freed budget from paused ads → distribute across top 3 performers,
    weighted by efficiency score. Never exceed +20% per ad per cycle.
    """
    freed = sum(a.daily_budget for a in paused)
    if freed == 0:
        return []

    paused_ids = {a.ad_id for a in paused}
    active = [
        a for a in ads
        if a.ad_id not in paused_ids
        and state.get("ads", {}).get(a.ad_id, {}).get("status") != "paused"
        and not a.is_bleeding
    ]

    if not active:
        return []

    # rank by efficiency, take top 3
    active.sort(key=lambda a: a.efficiency_score, reverse=True)
    top_performers = active[:3]

    # weight distribution by efficiency score
    total_score = sum(a.efficiency_score for a in top_performers)
    if total_score == 0:
        return []

    shifts = []
    remaining_freed = freed

    for ad in top_performers:
        if remaining_freed <= 0:
            break

        weight = ad.efficiency_score / total_score
        proposed_shift = freed * weight
        max_increase = ad.daily_budget * MAX_BUDGET_SCALE_PCT
        shift_amount = min(proposed_shift, max_increase, remaining_freed)

        if shift_amount < 1:  # skip trivial amounts
            continue

        new_budget = ad.daily_budget + shift_amount
        remaining_freed -= shift_amount

        shifts.append({
            "ad_id": ad.ad_id,
            "ad_name": ad.ad_name,
            "campaign": ad.campaign,
            "current_budget": ad.daily_budget,
            "shift_amount": round(shift_amount, 2),
            "new_budget": round(new_budget, 2),
            "efficiency_score": ad.efficiency_score,
            "weight_pct": round(weight * 100, 1),
            "reason": f"Efficiency score {ad.efficiency_score} ({weight * 100:.0f}% weight). Freed ${freed:.2f}/day total.",
        })

    return shifts


def apply_actions(
    paused: list[AdMetrics],
    shifts: list[dict],
    state: dict,
    dry_run: bool = True,
) -> None:
    """
    Apply pauses + budget shifts.
    dry_run=True: just print what would happen (safe default).
    dry_run=False: call social-flow CLI (requires live credentials).
    """
    for ad in paused:
        state["ads"][ad.ad_id]["status"] = "paused"
        log_action(
            action="PAUSED",
            ad=ad,
            reason=f"CPA ${ad.cpa:.2f} vs target ${ad.target_cpa:.2f} ({ad.cpa_ratio:.1f}x) for 48h+",
            extra={"spend": ad.spend},
        )
        if not dry_run:
            subprocess.run(
                ["social", "marketing", "pause", "--ad-id", ad.ad_id],
                check=True,
            )

    for shift in shifts:
        if not dry_run:
            subprocess.run(
                [
                    "social", "marketing", "budget", "update",
                    "--ad-id", shift["ad_id"],
                    "--daily-budget", f"{shift['new_budget']:.2f}",
                ],
                check=True,
            )


def run_budget_guardian(ads: list[AdMetrics], dry_run: bool = True) -> dict:
    state = load_state()

    # update history for all ads
    for ad in ads:
        state = update_cpa_history(state, ad)

    paused = decide_pauses(ads, state)
    shifts = recommend_budget_shifts(ads, paused, state)

    apply_actions(paused, shifts, state, dry_run=dry_run)
    save_state(state)

    return {"paused": paused, "shifts": shifts, "state": state}


def print_guardian_report(result: dict, ads: list[AdMetrics]) -> None:
    paused = result["paused"]
    shifts = result["shifts"]
    state  = result["state"]

    print("\n" + "=" * 60)
    print("  BUDGET GUARDIAN REPORT")
    print("=" * 60)

    if paused:
        print(f"\n🔴  AUTO-PAUSED ({len(paused)} ads)")
        print("-" * 60)
        for ad in paused:
            print(f"  [{ad.ad_id}] {ad.ad_name}")
            print(f"    CPA: ${ad.cpa:.2f}  vs  Target: ${ad.target_cpa:.2f}  ({ad.cpa_ratio:.1f}x)")
            print(f"    Spend: ${ad.spend:.0f}/day  |  Freed budget: ${ad.daily_budget:.0f}/day")
    else:
        print("\n✅  No ads met the 48h bleed threshold — nothing paused.")

    if shifts:
        print(f"\n💰  BUDGET REALLOCATION")
        print("-" * 60)
        for s in shifts:
            print(f"  Winner: [{s['ad_id']}] {s['ad_name']}")
            print(f"    Budget: ${s['current_budget']:.0f} → ${s['new_budget']:.0f}  (+${s['shift_amount']:.0f}/day)")
            print(f"    Reason: {s['reason']}")

    # efficiency ranking
    active_ads = [
        a for a in ads
        if state.get("ads", {}).get(a.ad_id, {}).get("status") != "paused"
    ]
    active_ads.sort(key=lambda a: a.efficiency_score, reverse=True)

    print(f"\n📊  CAMPAIGN EFFICIENCY RANKING (active ads)")
    print("-" * 60)
    for i, ad in enumerate(active_ads, 1):
        status = "🏆" if i == 1 else f" {i}."
        bleeding = " ⚠ BLEEDING" if ad.is_bleeding else ""
        print(f"  {status} [{ad.ad_id}] {ad.ad_name}")
        print(f"     Score: {ad.efficiency_score}  |  CPA: ${ad.cpa:.2f}  |  CTR: {ad.ctr:.2f}%{bleeding}")

    print("=" * 60 + "\n")


# --- Sample data loader ---

def load_sample_data(filepath: str) -> list[AdMetrics]:
    ads = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ads.append(AdMetrics(
                ad_id=row["ad_id"],
                ad_name=row["ad_name"],
                campaign=row["campaign"],
                cpa=float(row["cpa"]),
                target_cpa=float(row["target_cpa"]),
                spend=float(row["spend"]),
                daily_budget=float(row.get("daily_budget", row["spend"])),
                ctr=float(row["ctr"]),
                frequency=float(row["frequency"]),
            ))
    return ads


if __name__ == "__main__":
    ads = load_sample_data("sample_data.csv")
    result = run_budget_guardian(ads, dry_run=True)
    print_guardian_report(result, ads)
