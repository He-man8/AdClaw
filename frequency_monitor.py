"""
Step 2: Catch Dying Ads Before CPA Spikes
------------------------------------------
Pulls daily frequency by ad. Frequency > 3.5 means the audience is cooked
and CTR is about to drop. Flag and alert before the CPA pain hits.
"""

import csv
from dataclasses import dataclass


FREQUENCY_DANGER = 3.5      # audience fatigue threshold
FREQUENCY_WARNING = 3.0     # early warning zone
CPA_OVERSPEND_RATIO = 1.2   # flag if CPA is already > 20% over target


@dataclass
class AdMetrics:
    ad_id: str
    ad_name: str
    campaign: str
    frequency: float
    ctr: float
    cpa: float
    target_cpa: float
    spend: float

    @property
    def cpa_ratio(self) -> float:
        return self.cpa / self.target_cpa if self.target_cpa else 0

    @property
    def is_audience_cooked(self) -> bool:
        return self.frequency >= FREQUENCY_DANGER

    @property
    def is_approaching_fatigue(self) -> bool:
        return FREQUENCY_WARNING <= self.frequency < FREQUENCY_DANGER

    @property
    def cpa_already_spiking(self) -> bool:
        return self.cpa_ratio >= CPA_OVERSPEND_RATIO

    @property
    def risk_score(self) -> float:
        """Higher = more urgent. Combines frequency + CPA signals."""
        freq_weight = (self.frequency / FREQUENCY_DANGER) * 60
        cpa_weight = min(self.cpa_ratio, 2.0) * 40
        return round(freq_weight + cpa_weight, 1)


def load_sample_data(filepath: str) -> list[AdMetrics]:
    ads = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ads.append(AdMetrics(
                ad_id=row["ad_id"],
                ad_name=row["ad_name"],
                campaign=row["campaign"],
                frequency=float(row["frequency"]),
                ctr=float(row["ctr"]),
                cpa=float(row["cpa"]),
                target_cpa=float(row["target_cpa"]),
                spend=float(row["spend"]),
            ))
    return ads


def is_awareness(ad: AdMetrics) -> bool:
    """Awareness ads have no CPA target — skip conversion logic for them."""
    return ad.target_cpa == 0


def load_meta_api_data(ad_account_id: str, access_token: str, date_preset: str = "last_7d") -> list[AdMetrics]:
    """
    Swap sample data for live Meta data.
    Requires: pip install facebook-business
    """
    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount

    FacebookAdsApi.init(access_token=access_token)
    account = AdAccount(f"act_{ad_account_id}")

    fields = ["id", "name", "campaign_id", "frequency", "ctr", "cpa", "spend"]
    params = {"date_preset": date_preset, "level": "ad"}
    insights = account.get_insights(fields=fields, params=params)

    # NOTE: target_cpa would come from your own config/DB — not Meta API
    ads = []
    for row in insights:
        ads.append(AdMetrics(
            ad_id=row.get("ad_id", ""),
            ad_name=row.get("ad_name", ""),
            campaign=row.get("campaign_name", ""),
            frequency=float(row.get("frequency", 0)),
            ctr=float(row.get("ctr", 0)),
            cpa=float(row.get("cost_per_action_type", [{}])[0].get("value", 0)),
            target_cpa=35.0,   # replace with your per-ad target
            spend=float(row.get("spend", 0)),
        ))
    return ads


def run_frequency_audit(ads: list[AdMetrics]) -> None:
    danger = [a for a in ads if a.is_audience_cooked]
    warning = [a for a in ads if a.is_approaching_fatigue]
    healthy = [a for a in ads if not a.is_audience_cooked and not a.is_approaching_fatigue]

    danger.sort(key=lambda a: a.risk_score, reverse=True)
    warning.sort(key=lambda a: a.risk_score, reverse=True)

    print("\n" + "=" * 60)
    print("  DAILY FREQUENCY AUDIT — DYING ADS DETECTOR")
    print("=" * 60)

    # --- DANGER ZONE ---
    if danger:
        print(f"\n🔴  AUDIENCE COOKED (frequency ≥ {FREQUENCY_DANGER}) — PAUSE THESE NOW")
        print("-" * 60)
        for ad in danger:
            cpa_str  = "Awareness (no CPA target)" if is_awareness(ad) else f"₹{ad.cpa:.2f}"
            cpa_note = "" if is_awareness(ad) else (
                f"  ⚠ CPA already spiking (₹{ad.cpa:.2f} vs target ₹{ad.target_cpa:.2f})"
                if ad.cpa_already_spiking else ""
            )
            print(f"  [{ad.ad_id}] {ad.ad_name}")
            print(f"    Campaign   : {ad.campaign}")
            print(f"    Frequency  : {ad.frequency:.2f}  |  CTR: {ad.ctr:.2f}%  |  CPA: {cpa_str}")
            print(f"    Spend      : ₹{ad.spend:.0f}  |  Risk Score: {ad.risk_score}")
            if cpa_note:
                print(f"   {cpa_note}")
            print()
    else:
        print("\n✅  No ads in danger zone today.\n")

    # --- WARNING ZONE ---
    if warning:
        print(f"🟡  APPROACHING FATIGUE (frequency {FREQUENCY_WARNING}–{FREQUENCY_DANGER}) — WATCH THESE")
        print("-" * 60)
        for ad in warning:
            print(f"  [{ad.ad_id}] {ad.ad_name}  |  freq: {ad.frequency:.2f}  |  CTR: {ad.ctr:.2f}%  |  CPA: ${ad.cpa:.2f}")
        print()

    # --- HEALTHY ---
    print(f"✅  HEALTHY ({len(healthy)} ads, frequency < {FREQUENCY_WARNING})")
    print("-" * 60)
    for ad in healthy:
        print(f"  [{ad.ad_id}] {ad.ad_name}  |  freq: {ad.frequency:.2f}  |  CTR: {ad.ctr:.2f}%")

    # --- SUMMARY ---
    total_spend_at_risk = sum(a.spend for a in danger)
    print("\n" + "=" * 60)
    print(f"  SUMMARY")
    print(f"  Ads in danger zone  : {len(danger)}")
    print(f"  Ads in warning zone : {len(warning)}")
    print(f"  Healthy ads         : {len(healthy)}")
    print(f"  Spend at risk today : ${total_spend_at_risk:,.0f}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    import os

    use_live = os.getenv("META_ACCESS_TOKEN") and os.getenv("META_AD_ACCOUNT_ID")

    if use_live:
        print("Pulling live data from Meta Marketing API...")
        ads = load_meta_api_data(
            ad_account_id=os.environ["META_AD_ACCOUNT_ID"],
            access_token=os.environ["META_ACCESS_TOKEN"],
        )
    else:
        print("Using sample data (set META_ACCESS_TOKEN + META_AD_ACCOUNT_ID to go live).")
        ads = load_sample_data("sample_data.csv")

    run_frequency_audit(ads)
