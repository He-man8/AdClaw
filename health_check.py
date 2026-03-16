"""
Health Check Agent — Daily Ad Health Audit
-------------------------------------------
Answers the 5 morning questions:
  1. Am I on track?
  2. What's running?
  3. Who's winning?
  4. Who's bleeding?
  5. Any fatigue?

Upgrades over frequency_monitor.py:
  - Trend detection: flags ads where frequency rose >0.5 over last 3 data points
  - CTR decay: flags ads where CTR dropped >15% vs previous period
  - Outputs structured JSON report to output/health_report.json

Usage:
  python3 health_check.py               # sample data
  python3 health_check.py --live        # live Meta API
"""

import csv
import json
import sys
from dataclasses import dataclass, asdict

from config import settings
from datetime import datetime, timezone
from pathlib import Path


FREQUENCY_DANGER = 3.5
FREQUENCY_WARNING = 3.0
CPA_OVERSPEND_RATIO = 1.2
CTR_DECAY_THRESHOLD = 0.15  # 15% drop = flagged
FREQ_TREND_THRESHOLD = 0.5  # rising 0.5+ over 3 data points

SAMPLE_FILE = "sample_data.csv"
HISTORY_FILE = Path("output/health_history.json")
REPORT_FILE = Path("output/health_report.json")


@dataclass
class AdHealth:
    ad_id: str
    ad_name: str
    campaign: str
    frequency: float
    ctr: float
    cpa: float
    target_cpa: float
    spend: float
    daily_budget: float = 0.0

    @property
    def cpa_ratio(self) -> float:
        return self.cpa / self.target_cpa if self.target_cpa else 0

    @property
    def is_awareness(self) -> bool:
        return self.target_cpa == 0

    @property
    def is_audience_cooked(self) -> bool:
        return self.frequency >= FREQUENCY_DANGER

    @property
    def is_approaching_fatigue(self) -> bool:
        return FREQUENCY_WARNING <= self.frequency < FREQUENCY_DANGER

    @property
    def cpa_already_spiking(self) -> bool:
        return not self.is_awareness and self.cpa_ratio >= CPA_OVERSPEND_RATIO

    @property
    def risk_score(self) -> float:
        freq_weight = (self.frequency / FREQUENCY_DANGER) * 60
        cpa_weight = min(self.cpa_ratio, 2.0) * 40 if not self.is_awareness else 0
        return round(freq_weight + cpa_weight, 1)


# --- History tracking for trend detection ---

def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {"snapshots": []}


def save_history(history: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # keep last 30 snapshots
    history["snapshots"] = history["snapshots"][-30:]
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def record_snapshot(history: dict, ads: list[AdHealth]) -> dict:
    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ads": {
            ad.ad_id: {"frequency": ad.frequency, "ctr": ad.ctr, "cpa": ad.cpa}
            for ad in ads
        },
    }
    history["snapshots"].append(snapshot)
    return history


def detect_frequency_trend(history: dict, ad_id: str) -> dict | None:
    """Check if frequency is rising over the last 3 data points."""
    snapshots = history.get("snapshots", [])
    freq_points = []
    for snap in snapshots[-3:]:
        ad_data = snap.get("ads", {}).get(ad_id)
        if ad_data:
            freq_points.append(ad_data["frequency"])

    if len(freq_points) < 2:
        return None

    delta = freq_points[-1] - freq_points[0]
    if delta >= FREQ_TREND_THRESHOLD:
        return {
            "direction": "rising",
            "from": freq_points[0],
            "to": freq_points[-1],
            "delta": round(delta, 2),
            "points": len(freq_points),
        }
    return None


def detect_ctr_decay(history: dict, ad_id: str, current_ctr: float) -> dict | None:
    """Check if CTR dropped >15% vs the average of prior data points."""
    snapshots = history.get("snapshots", [])
    prior_ctrs = []
    for snap in snapshots[:-1]:  # exclude the one we just recorded
        ad_data = snap.get("ads", {}).get(ad_id)
        if ad_data and ad_data["ctr"] > 0:
            prior_ctrs.append(ad_data["ctr"])

    if not prior_ctrs:
        return None

    avg_prior = sum(prior_ctrs) / len(prior_ctrs)
    if avg_prior == 0:
        return None

    decay_pct = (avg_prior - current_ctr) / avg_prior
    if decay_pct >= CTR_DECAY_THRESHOLD:
        return {
            "prior_avg_ctr": round(avg_prior, 2),
            "current_ctr": round(current_ctr, 2),
            "decay_pct": round(decay_pct * 100, 1),
        }
    return None


# --- Data loading ---

def load_sample_data(filepath: str) -> list[AdHealth]:
    ads = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ads.append(AdHealth(
                ad_id=row["ad_id"],
                ad_name=row["ad_name"],
                campaign=row["campaign"],
                frequency=float(row["frequency"]),
                ctr=float(row["ctr"]),
                cpa=float(row["cpa"]),
                target_cpa=float(row["target_cpa"]),
                spend=float(row["spend"]),
                daily_budget=float(row.get("daily_budget", row["spend"])),
            ))
    return ads


def load_meta_api_data(ad_account_id: str, access_token: str, date_preset: str = "last_7d") -> list[AdHealth]:
    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount

    FacebookAdsApi.init(access_token=access_token)
    account = AdAccount(f"act_{ad_account_id}")

    fields = ["id", "name", "campaign_id", "frequency", "ctr", "cpa", "spend"]
    params = {"date_preset": date_preset, "level": "ad"}
    insights = account.get_insights(fields=fields, params=params)

    ads = []
    for row in insights:
        ads.append(AdHealth(
            ad_id=row.get("ad_id", ""),
            ad_name=row.get("ad_name", ""),
            campaign=row.get("campaign_name", ""),
            frequency=float(row.get("frequency", 0)),
            ctr=float(row.get("ctr", 0)),
            cpa=float(row.get("cost_per_action_type", [{}])[0].get("value", 0)),
            target_cpa=35.0,
            spend=float(row.get("spend", 0)),
        ))
    return ads


# --- Core audit ---

def run_health_check(ads: list[AdHealth], live: bool = False) -> dict:
    history = load_history()
    history = record_snapshot(history, ads)

    danger = []
    warning = []
    healthy = []
    trending_up = []
    ctr_decaying = []

    for ad in ads:
        # categorize by frequency
        if ad.is_audience_cooked:
            danger.append(ad)
        elif ad.is_approaching_fatigue:
            warning.append(ad)
        else:
            healthy.append(ad)

        # trend detection
        trend = detect_frequency_trend(history, ad.ad_id)
        if trend:
            trending_up.append({"ad_id": ad.ad_id, "ad_name": ad.ad_name, **trend})

        # CTR decay
        decay = detect_ctr_decay(history, ad.ad_id, ad.ctr)
        if decay:
            ctr_decaying.append({"ad_id": ad.ad_id, "ad_name": ad.ad_name, **decay})

    danger.sort(key=lambda a: a.risk_score, reverse=True)
    warning.sort(key=lambda a: a.risk_score, reverse=True)

    save_history(history)

    # build report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if live else "sample",
        "total_ads": len(ads),
        "danger": [asdict(a) for a in danger],
        "warning": [asdict(a) for a in warning],
        "healthy": [asdict(a) for a in healthy],
        "trending_up": trending_up,
        "ctr_decaying": ctr_decaying,
        "spend_at_risk": sum(a.spend for a in danger),
        "all_ads": [asdict(a) for a in ads],
    }

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2))

    # print report
    print_health_report(danger, warning, healthy, trending_up, ctr_decaying, ads)

    return report


def print_health_report(
    danger: list[AdHealth],
    warning: list[AdHealth],
    healthy: list[AdHealth],
    trending_up: list[dict],
    ctr_decaying: list[dict],
    all_ads: list[AdHealth],
) -> None:
    print("\n" + "=" * 60)
    print("  DAILY HEALTH CHECK")
    print("=" * 60)

    # DANGER
    if danger:
        print(f"\n🔴  AUDIENCE COOKED (frequency ≥ {FREQUENCY_DANGER})")
        print("-" * 60)
        for ad in danger:
            cpa_str = "Awareness" if ad.is_awareness else f"${ad.cpa:.2f}"
            print(f"  [{ad.ad_id}] {ad.ad_name}")
            print(f"    freq: {ad.frequency:.2f} | CTR: {ad.ctr:.2f}% | CPA: {cpa_str} | risk: {ad.risk_score}")
            if ad.cpa_already_spiking:
                print(f"    ⚠ CPA spiking: ${ad.cpa:.2f} vs target ${ad.target_cpa:.2f}")
    else:
        print("\n✅  No ads in danger zone.")

    # TRENDING UP
    if trending_up:
        print(f"\n📈  FREQUENCY TRENDING UP (rising ≥ {FREQ_TREND_THRESHOLD})")
        print("-" * 60)
        for t in trending_up:
            print(f"  [{t['ad_id']}] {t['ad_name']}  —  freq {t['from']:.2f} → {t['to']:.2f} (+{t['delta']:.2f} over {t['points']} checks)")

    # CTR DECAY
    if ctr_decaying:
        print(f"\n📉  CTR DECAYING (dropped ≥ {CTR_DECAY_THRESHOLD * 100:.0f}%)")
        print("-" * 60)
        for d in ctr_decaying:
            print(f"  [{d['ad_id']}] {d['ad_name']}  —  CTR {d['prior_avg_ctr']:.2f}% → {d['current_ctr']:.2f}% (↓{d['decay_pct']:.1f}%)")

    # WARNING
    if warning:
        print(f"\n🟡  APPROACHING FATIGUE (freq {FREQUENCY_WARNING}–{FREQUENCY_DANGER})")
        print("-" * 60)
        for ad in warning:
            print(f"  [{ad.ad_id}] {ad.ad_name}  |  freq: {ad.frequency:.2f}  |  CTR: {ad.ctr:.2f}%")

    # HEALTHY
    print(f"\n✅  HEALTHY ({len(healthy)} ads, freq < {FREQUENCY_WARNING})")
    print("-" * 60)
    for ad in healthy:
        print(f"  [{ad.ad_id}] {ad.ad_name}  |  freq: {ad.frequency:.2f}  |  CTR: {ad.ctr:.2f}%")

    # SUMMARY
    total_risk = sum(a.spend for a in danger)
    print("\n" + "=" * 60)
    print(f"  SUMMARY")
    print(f"  Danger zone       : {len(danger)}")
    print(f"  Freq trending up  : {len(trending_up)}")
    print(f"  CTR decaying      : {len(ctr_decaying)}")
    print(f"  Warning zone      : {len(warning)}")
    print(f"  Healthy           : {len(healthy)}")
    print(f"  Spend at risk     : ${total_risk:,.0f}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    live = "--live" in sys.argv

    if live:
        print("Pulling live data from Meta Marketing API...")
        settings.require_meta()
        ads = load_meta_api_data(
            ad_account_id=settings.meta_ad_account_id,
            access_token=settings.meta_access_token,
        )
    else:
        print("Using sample data (set META_ACCESS_TOKEN + META_AD_ACCOUNT_ID to go live).\n")
        ads = load_sample_data(SAMPLE_FILE)

    run_health_check(ads, live=live)
