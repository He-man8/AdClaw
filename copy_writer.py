"""
Step 4: Write New Ad Copy from Winners
---------------------------------------
- Pulls top performing ads (lowest CPA, highest CTR)
- Extracts their copy patterns (hooks, angles, CTAs)
- Sends to Gemini API to generate 3 variations per winner
- Output: ready-to-upload copy variants saved to generated_copy.json
"""

import csv
import json
from dataclasses import dataclass

from config import settings


GEMINI_MODEL    = "gemini-3.1-pro-preview"
TOP_N_WINNERS   = 3    # analyze top N ads
VARIANTS_PER_AD = 3    # generate N copy variants


@dataclass
class AdWithCopy:
    ad_id: str
    ad_name: str
    campaign: str
    ctr: float
    cpa: float
    target_cpa: float
    headline: str
    body: str
    cta: str

    @property
    def performance_summary(self) -> str:
        return f"CTR {self.ctr:.2f}% | CPA ${self.cpa:.2f} vs target ${self.target_cpa:.2f}"


# --- Copy pulled from the actual ads (stands in for Meta API creative fetch) ---
# In live mode this comes from the Meta API `ad_creative` field.
# For now we read headline/body/cta directly from sample_data.csv.


def load_winners_from_csv(filepath: str, top_n: int = TOP_N_WINNERS) -> list[AdWithCopy]:
    """Load conversion ads ranked by efficiency (low CPA + high CTR). Skips awareness ads."""
    ads = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cpa    = float(row["cpa"])
            target = float(row["target_cpa"])

            # skip awareness ads (no CPA target) and bleeding ads
            if target == 0:
                continue
            if cpa > target * 1.5:
                continue

            ads.append(AdWithCopy(
                ad_id=row["ad_id"],
                ad_name=row["ad_name"],
                campaign=row["campaign"],
                ctr=float(row["ctr"]),
                cpa=cpa,
                target_cpa=target,
                headline=row.get("headline", row["ad_name"]),
                body=row.get("body", ""),
                cta=row.get("cta", "Learn More"),
            ))

    # rank: lower CPA ratio + higher CTR = better
    ads.sort(key=lambda a: (a.cpa / a.target_cpa) - (a.ctr / 10))
    return ads[:top_n]


def build_prompt(winners: list[AdWithCopy]) -> str:
    ads_text = ""
    for i, ad in enumerate(winners, 1):
        ads_text += f"""
Ad {i} — {ad.ad_name} ({ad.performance_summary})
  Headline : {ad.headline}
  Body     : {ad.body}
  CTA      : {ad.cta}
"""

    return f"""You are a direct-response copywriter analyzing winning Meta ads.

Here are the top {len(winners)} performing ads from this account:
{ads_text}

Your task:
1. Identify the shared patterns: hooks, emotional angles, proof elements, CTA styles
2. Generate {VARIANTS_PER_AD} NEW ad copy variants that follow these patterns but with fresh angles
3. Each variant must have: Headline, Body (2-3 sentences max), CTA

Rules:
- Keep the same emotional register as the winners
- Vary the hook type: one curiosity, one social proof, one direct benefit
- Body copy must be punchy — no fluff, no passive voice
- CTAs should create mild urgency without being desperate

Return ONLY a JSON array in this exact format, no markdown fences:
[
  {{
    "variant": 1,
    "hook_type": "curiosity|social_proof|direct_benefit",
    "headline": "...",
    "body": "...",
    "cta": "..."
  }}
]"""


def generate_copy_variants(winners: list[AdWithCopy]) -> list[dict]:
    """Call Gemini API to generate copy variants. Falls back to mock if no API key."""
    if not settings.has_gemini:
        print("  [INFO] No GEMINI_API_KEY found — returning mock variants.")
        return _mock_variants()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_prompt(winners),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)


def _mock_variants() -> list[dict]:
    return [
        {
            "variant": 1,
            "hook_type": "curiosity",
            "headline": "Why Are 10,000 Customers Keeping This a Secret?",
            "body": "It started with one review that went viral. Now everyone's talking about it — "
                    "except the people who already have it. They're just reordering.",
            "cta": "See What the Hype Is About",
        },
        {
            "variant": 2,
            "hook_type": "social_proof",
            "headline": "\"Best Purchase I've Made This Year\" — Jake, verified buyer",
            "body": "Jake's not alone. Over 4,000 five-star reviews and climbing. "
                    "Find out what they all have in common.",
            "cta": "Read the Reviews",
        },
        {
            "variant": 3,
            "hook_type": "direct_benefit",
            "headline": "Skip the Guesswork. Get Results in 3 Weeks.",
            "body": "No complicated setup. No learning curve. "
                    "Just a straightforward solution that works — backed by a 30-day guarantee.",
            "cta": "Start Today",
        },
    ]


def build_concepts_prompt(winners: list[AdWithCopy]) -> str:
    ads_text = ""
    for i, ad in enumerate(winners, 1):
        ads_text += f"""
Ad {i} — {ad.ad_name} ({ad.performance_summary})
  Headline : {ad.headline}
  Body     : {ad.body}
  CTA      : {ad.cta}
"""

    return f"""You are a paid media strategist analyzing the top performing ads in a Meta account.

Here are the {len(winners)} best performing ads:
{ads_text}

Analyze these winners deeply and return 3 content test hypotheses — specific things to test next
based on what these ads reveal about what resonates with this audience.

For each hypothesis:
- Name the pattern you spotted in the winners
- State the specific test to run
- Explain why it should work given the evidence

Return ONLY a JSON array, no markdown fences:
[
  {{
    "hypothesis": 1,
    "pattern_spotted": "one sentence — what pattern do the winners share",
    "test": "one sentence — the specific ad concept or angle to test",
    "format": "static|video|carousel",
    "why_it_will_work": "one sentence — grounded in the winner data"
  }}
]"""


def generate_content_concepts(winners: list[AdWithCopy]) -> list[dict]:
    """Spot patterns across winners and suggest what to test next."""
    if not settings.has_gemini:
        print("  [INFO] No GEMINI_API_KEY found — returning mock concepts.")
        return _mock_concepts()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_concepts_prompt(winners),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)


def _mock_concepts() -> list[dict]:
    return [
        {
            "hypothesis": 1,
            "pattern_spotted": "UGC-style ads with a real person narrating their own transformation outperform polished brand creative 2:1 on CTR.",
            "test": "Film a 15-second phone-quality video of a customer saying exactly what changed for them — no script, no branding, just the result.",
            "format": "video",
            "why_it_will_work": "Your two lowest-CPA ads are both UGC formats; the audience trusts peers over brands.",
        },
        {
            "hypothesis": 2,
            "pattern_spotted": "Headlines that open with a specific timeframe ('3 weeks', '60 days') consistently outperform vague benefit claims.",
            "test": "Run a static ad with headline: 'Most people see a difference in 18 days. Here's why.' against your current control.",
            "format": "static",
            "why_it_will_work": "Specificity creates credibility — your top performers all use concrete numbers, not adjectives.",
        },
        {
            "hypothesis": 3,
            "pattern_spotted": "Carousel ads with a before/after or step-by-step reveal structure haven't been tested yet despite high engagement on demo video.",
            "test": "Build a 4-card carousel: Card 1 = the problem, Cards 2-3 = the process, Card 4 = the result + CTA.",
            "format": "carousel",
            "why_it_will_work": "Your Product Demo video (CTR 1.75%, CPA $28.97) shows this audience responds to 'how it works' content — carousel extends that dwell time.",
        },
    ]


def print_copy_report(winners: list[AdWithCopy], variants: list[dict], concepts: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("  COPY WRITER REPORT")
    print("=" * 60)

    print(f"\n📊  WINNERS ANALYZED")
    print("-" * 60)
    for ad in winners:
        print(f"  [{ad.ad_id}] {ad.ad_name}  |  {ad.performance_summary}")
        print(f"    Hook: \"{ad.headline}\"")

    print(f"\n✍️   GENERATED VARIANTS ({len(variants)} new ads)")
    print("-" * 60)
    for v in variants:
        print(f"\n  Variant {v['variant']} — {v['hook_type'].upper()}")
        print(f"  Headline : {v['headline']}")
        print(f"  Body     : {v['body']}")
        print(f"  CTA      : {v['cta']}")

    print(f"\n\n💡  CONTENT CONCEPTS — WHAT TO TEST NEXT ({len(concepts)} hypotheses)")
    print("-" * 60)
    for c in concepts:
        print(f"\n  Hypothesis {c['hypothesis']} — {c['format'].upper()}")
        print(f"  Pattern  : {c['pattern_spotted']}")
        print(f"  Test     : {c['test']}")
        print(f"  Why      : {c['why_it_will_work']}")

    print("\n" + "=" * 60 + "\n")

    out_path = "generated_copy.json"
    with open(out_path, "w") as f:
        json.dump({"variants": variants, "concepts": concepts}, f, indent=2)
    print(f"  Saved to {out_path} — ready for ad_publisher.py\n")


if __name__ == "__main__":
    winners  = load_winners_from_csv("sample_data.csv")
    variants = generate_copy_variants(winners)
    concepts = generate_content_concepts(winners)
    print_copy_report(winners, variants, concepts)
