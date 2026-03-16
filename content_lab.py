"""
Content Lab Agent — Pattern Analysis & Test Hypotheses
-------------------------------------------------------
The intelligence layer of AdClaw:
  - Analyzes patterns across ALL historical winners
  - Maintains a growing creative playbook
  - Generates test hypotheses grounded in account data
  - Tracks experiments: hypothesis → test → result → learning

Usage:
  python3 content_lab.py
"""

import csv
import json
from dataclasses import dataclass

from config import settings
from datetime import datetime, timezone
from pathlib import Path


GEMINI_MODEL = "gemini-3.1-pro-preview"
SAMPLE_FILE = "sample_data.csv"
PLAYBOOK_FILE = Path("output/creative_playbook.json")
HYPOTHESES_FILE = Path("output/content_hypotheses.json")
EXPERIMENT_LOG = Path("output/experiment_log.json")


@dataclass
class AdPerformance:
    ad_id: str
    ad_name: str
    campaign: str
    ad_format: str
    ctr: float
    cpa: float
    target_cpa: float
    frequency: float
    spend: float
    headline: str
    body: str
    cta: str

    @property
    def cpa_ratio(self) -> float:
        return self.cpa / self.target_cpa if self.target_cpa else 0

    @property
    def is_winner(self) -> bool:
        if self.target_cpa == 0:
            return self.ctr >= 2.0  # awareness: winning if CTR > 2%
        return self.cpa_ratio <= 1.2  # conversion: CPA within 20% of target

    @property
    def performance_tier(self) -> str:
        if self.target_cpa == 0:
            if self.ctr >= 2.5:
                return "top"
            if self.ctr >= 1.5:
                return "mid"
            return "low"
        if self.cpa_ratio <= 0.8:
            return "top"
        if self.cpa_ratio <= 1.2:
            return "mid"
        return "low"


def load_all_ads(filepath: str) -> list[AdPerformance]:
    ads = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ads.append(AdPerformance(
                ad_id=row["ad_id"],
                ad_name=row["ad_name"],
                campaign=row["campaign"],
                ad_format=row.get("format", "static"),
                ctr=float(row["ctr"]),
                cpa=float(row["cpa"]),
                target_cpa=float(row["target_cpa"]),
                frequency=float(row["frequency"]),
                spend=float(row["spend"]),
                headline=row.get("headline", row["ad_name"]),
                body=row.get("body", ""),
                cta=row.get("cta", "Learn More"),
            ))
    return ads


# --- Pattern Analysis (rule-based, no LLM needed) ---

def analyze_patterns(ads: list[AdPerformance]) -> list[dict]:
    """Extract winning patterns from the data without LLM."""
    winners = [a for a in ads if a.is_winner]
    patterns = []

    if not winners:
        return [{"pattern": "Not enough winner data yet", "evidence": "N/A", "confidence": "low"}]

    # Pattern 1: Format analysis
    format_performance = {}
    for ad in ads:
        fmt = ad.ad_format
        if fmt not in format_performance:
            format_performance[fmt] = {"ctrs": [], "cpas": [], "count": 0}
        format_performance[fmt]["ctrs"].append(ad.ctr)
        if ad.target_cpa > 0:
            format_performance[fmt]["cpas"].append(ad.cpa_ratio)
        format_performance[fmt]["count"] += 1

    best_format = None
    best_ctr = 0
    for fmt, data in format_performance.items():
        avg_ctr = sum(data["ctrs"]) / len(data["ctrs"])
        if avg_ctr > best_ctr:
            best_ctr = avg_ctr
            best_format = fmt

    if best_format:
        patterns.append({
            "pattern": f"{best_format.capitalize()} format has highest average CTR ({best_ctr:.2f}%)",
            "evidence": f"Across {format_performance[best_format]['count']} ads",
            "confidence": "high" if format_performance[best_format]["count"] >= 3 else "medium",
        })

    # Pattern 2: Campaign type analysis
    campaign_winners = {}
    for ad in winners:
        camp = ad.campaign
        if camp not in campaign_winners:
            campaign_winners[camp] = 0
        campaign_winners[camp] += 1

    if campaign_winners:
        best_campaign = max(campaign_winners, key=lambda k: campaign_winners[k])
        patterns.append({
            "pattern": f"{best_campaign} campaigns produce the most winners ({campaign_winners[best_campaign]})",
            "evidence": f"Out of {len(winners)} total winners",
            "confidence": "medium",
        })

    # Pattern 3: Frequency vs performance
    low_freq_winners = [a for a in winners if a.frequency < 2.0]
    high_freq_any = [a for a in ads if a.frequency >= 3.0]
    if low_freq_winners and high_freq_any:
        avg_ctr_low = sum(a.ctr for a in low_freq_winners) / len(low_freq_winners)
        avg_ctr_high = sum(a.ctr for a in high_freq_any) / len(high_freq_any)
        if avg_ctr_low > avg_ctr_high:
            patterns.append({
                "pattern": f"Fresh audiences (freq < 2.0) have {avg_ctr_low:.2f}% CTR vs {avg_ctr_high:.2f}% for fatigued (freq ≥ 3.0)",
                "evidence": f"{len(low_freq_winners)} low-freq winners vs {len(high_freq_any)} high-freq ads",
                "confidence": "high",
            })

    # Pattern 4: Winner copy analysis
    winner_headlines = [a.headline for a in winners if a.headline]
    number_headlines = [h for h in winner_headlines if any(c.isdigit() for c in h)]
    if len(number_headlines) > len(winner_headlines) * 0.4:
        patterns.append({
            "pattern": "Winners disproportionately use specific numbers in headlines",
            "evidence": f"{len(number_headlines)}/{len(winner_headlines)} winner headlines contain numbers",
            "confidence": "medium",
        })

    # Pattern 5: CTA analysis
    winner_ctas = [a.cta.lower() for a in winners if a.cta]
    urgency_ctas = [c for c in winner_ctas if any(w in c for w in ["now", "today", "before", "grab", "get"])]
    if urgency_ctas and len(urgency_ctas) > len(winner_ctas) * 0.5:
        patterns.append({
            "pattern": "Urgency-driven CTAs dominate winners",
            "evidence": f"{len(urgency_ctas)}/{len(winner_ctas)} winner CTAs use urgency words",
            "confidence": "medium",
        })

    return patterns


# --- Hypothesis Generation ---

def generate_hypotheses_rule_based(ads: list[AdPerformance], patterns: list[dict]) -> list[dict]:
    """Generate test hypotheses without LLM, based on pattern analysis."""
    winners = [a for a in ads if a.is_winner]
    hypotheses = []
    hypothesis_num = 1

    # Get formats in use
    formats_used = set(a.ad_format for a in ads)
    formats_not_tested = {"carousel", "video", "static"} - formats_used

    # Hypothesis from untested formats
    if formats_not_tested:
        fmt = formats_not_tested.pop()
        hypotheses.append({
            "hypothesis": hypothesis_num,
            "pattern_spotted": f"No {fmt} ads tested yet — potential untapped format",
            "test": f"Create a {fmt} version of your best performing ad to test format impact",
            "format": fmt,
            "why_it_will_work": f"Your account has no {fmt} data — testing it fills a blind spot in your creative strategy",
        })
        hypothesis_num += 1

    # Hypothesis from winner patterns
    if winners:
        def winner_sort_key(a: AdPerformance) -> float:
            return a.cpa_ratio if a.target_cpa > 0 else (1 / (a.ctr + 0.01))
        top_winner = min(winners, key=winner_sort_key)
        hypotheses.append({
            "hypothesis": hypothesis_num,
            "pattern_spotted": f"Top performer '{top_winner.ad_name}' uses: \"{top_winner.headline}\"",
            "test": f"Create 3 angle variations of this headline keeping the same structure but changing the specific benefit/proof",
            "format": top_winner.ad_format,
            "why_it_will_work": f"This ad has the best efficiency in the account (CTR {top_winner.ctr:.2f}%, CPA ratio {top_winner.cpa_ratio:.2f}x) — variations should capture similar audiences",
        })
        hypothesis_num += 1

    # Hypothesis from remarketing gap
    remarketing_ads = [a for a in ads if "remarketing" in a.campaign.lower() or "retargeting" in a.campaign.lower()]
    if remarketing_ads:
        avg_freq = sum(a.frequency for a in remarketing_ads) / len(remarketing_ads)
        if avg_freq > 3.0:
            hypotheses.append({
                "hypothesis": hypothesis_num,
                "pattern_spotted": f"Remarketing ads averaging {avg_freq:.1f} frequency — audience fatigue setting in",
                "test": "Refresh remarketing creative with completely new angles — test a testimonial/UGC approach vs current direct-response",
                "format": "video",
                "why_it_will_work": f"High frequency ({avg_freq:.1f}) means the same people are seeing the same ads repeatedly. Fresh creative resets attention.",
            })
            hypothesis_num += 1

    return hypotheses


def generate_hypotheses_llm(ads: list[AdPerformance], patterns: list[dict]) -> list[dict]:
    """Use Gemini to generate deeper hypotheses."""
    if not settings.has_gemini:
        return []

    from google import genai
    from google.genai import types

    winners = [a for a in ads if a.is_winner]
    pattern_text = "\n".join(f"  - {p['pattern']} ({p['confidence']} confidence)" for p in patterns)
    winners_text = "\n".join(
        f"  - {a.ad_name} | {a.ad_format} | CTR {a.ctr:.2f}% | CPA ${a.cpa:.2f} | \"{a.headline}\""
        for a in winners
    )

    prompt = f"""You are a paid media strategist analyzing a Meta ad account.

PATTERNS FOUND:
{pattern_text}

WINNING ADS:
{winners_text}

Based on these patterns and winners, generate 3 specific test hypotheses.
Each must be grounded in the actual data above — no generic advice.

Return ONLY a JSON array:
[
  {{
    "hypothesis": 1,
    "pattern_spotted": "what pattern from above you're building on",
    "test": "the specific ad concept to test — be concrete",
    "format": "static|video|carousel",
    "why_it_will_work": "evidence from the data above"
  }}
]"""

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    text = response.text or "[]"
    return json.loads(text)


# --- Creative Playbook ---

def load_playbook() -> dict:
    if PLAYBOOK_FILE.exists():
        return json.loads(PLAYBOOK_FILE.read_text())
    return {"patterns": [], "last_updated": None}


def update_playbook(patterns: list[dict]) -> dict:
    playbook = load_playbook()

    existing_patterns = {p["pattern"] for p in playbook["patterns"]}
    for p in patterns:
        if p["pattern"] not in existing_patterns:
            playbook["patterns"].append({
                **p,
                "discovered": datetime.now(timezone.utc).isoformat(),
            })

    playbook["last_updated"] = datetime.now(timezone.utc).isoformat()

    PLAYBOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAYBOOK_FILE.write_text(json.dumps(playbook, indent=2))
    return playbook


# --- Experiment Tracking ---

def load_experiments() -> list[dict]:
    if EXPERIMENT_LOG.exists():
        return json.loads(EXPERIMENT_LOG.read_text())
    return []


def save_experiments(experiments: list[dict]) -> None:
    EXPERIMENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    EXPERIMENT_LOG.write_text(json.dumps(experiments, indent=2))


def _normalize_test(text: str) -> str:
    """Normalize test description for dedup — lowercase, strip punctuation, collapse whitespace."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    # take first 60 chars as fingerprint (LLM rephrasing usually diverges after that)
    return text[:60]


def log_hypotheses_as_experiments(hypotheses: list[dict]) -> list[dict]:
    experiments = load_experiments()
    existing_fingerprints = {_normalize_test(e["test"]) for e in experiments}

    for h in hypotheses:
        fingerprint = _normalize_test(h["test"])
        if fingerprint not in existing_fingerprints:
            experiments.append({
                "hypothesis_id": h["hypothesis"],
                "test": h["test"],
                "format": h["format"],
                "status": "proposed",
                "proposed_at": datetime.now(timezone.utc).isoformat(),
                "result": None,
                "learning": None,
            })
            existing_fingerprints.add(fingerprint)

    save_experiments(experiments)
    return experiments


# --- Main ---

def run_content_lab(ads: list[AdPerformance]) -> dict:
    print("\n" + "=" * 60)
    print("  CONTENT LAB — PATTERN ANALYSIS")
    print("=" * 60)

    # analyze patterns
    patterns = analyze_patterns(ads)
    print(f"\n📖  CREATIVE PLAYBOOK")
    print("-" * 60)
    for p in patterns:
        print(f"  [{p['confidence'].upper()}] {p['pattern']}")
        print(f"         Evidence: {p['evidence']}")

    # update playbook
    playbook = update_playbook(patterns)
    print(f"\n  Playbook: {len(playbook['patterns'])} total patterns tracked")

    # generate hypotheses
    print(f"\n🔬  TEST HYPOTHESES")
    print("-" * 60)

    hypotheses = generate_hypotheses_rule_based(ads, patterns)

    # try LLM hypotheses if available
    llm_hypotheses = generate_hypotheses_llm(ads, patterns)
    if llm_hypotheses:
        # merge, avoiding duplicates by numbering
        next_num = len(hypotheses) + 1
        for h in llm_hypotheses:
            h["hypothesis"] = next_num
            hypotheses.append(h)
            next_num += 1

    for h in hypotheses:
        print(f"\n  Hypothesis {h['hypothesis']} — {h['format'].upper()}")
        print(f"  Pattern  : {h['pattern_spotted']}")
        print(f"  Test     : {h['test']}")
        print(f"  Why      : {h['why_it_will_work']}")

    # save hypotheses
    HYPOTHESES_FILE.parent.mkdir(parents=True, exist_ok=True)
    HYPOTHESES_FILE.write_text(json.dumps(hypotheses, indent=2))

    # track experiments
    experiments = log_hypotheses_as_experiments(hypotheses)
    active = [e for e in experiments if e["status"] == "active"]
    proposed = [e for e in experiments if e["status"] == "proposed"]
    completed = [e for e in experiments if e["status"] == "completed"]

    print(f"\n📊  EXPERIMENT TRACKER")
    print("-" * 60)
    print(f"  Proposed  : {len(proposed)}")
    print(f"  Active    : {len(active)}")
    print(f"  Completed : {len(completed)}")
    if completed:
        last = completed[-1]
        print(f"  Last result: {last['test']} → {last.get('result', 'pending')}")

    print("\n" + "=" * 60 + "\n")

    return {
        "patterns": patterns,
        "hypotheses": hypotheses,
        "experiments": {
            "proposed": len(proposed),
            "active": len(active),
            "completed": len(completed),
        },
    }


if __name__ == "__main__":
    ads = load_all_ads(SAMPLE_FILE)
    run_content_lab(ads)
