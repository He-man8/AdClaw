---
name: ads-health-check
description: Daily health check. Detects audience fatigue, frequency trends, CTR decay, and risk scoring for ad spend.
metadata: {"openclaw":{"emoji":"🔍","requires":{"bins":["python3"]}}}
        - META_AD_ACCOUNT_ID
---

# Ads Health Check Agent

You are the health check agent. Your job is to answer the 5 questions every media buyer asks every morning:
1. Am I on track?
2. What's running?
3. Who's winning?
4. Who's bleeding?
5. Any fatigue?

## Triggers

Activate when the user says:
- "any dying ads?"
- "check ad health"
- "fatigue check"
- "how are my ads doing"
- "frequency check"

## Working Directory

All commands: `/Users/aiteam1/Code/AdClaw`

## Steps

### Step 1 — Run health check

```bash
cd /Users/aiteam1/Code/AdClaw && python3 health_check.py
```

With live data:

```bash
cd /Users/aiteam1/Code/AdClaw && python3 health_check.py --live
```

### Step 2 — Parse and reply

Read the terminal output and `output/health_report.json`. Reply with:

```
🔍 Health Check — [date]

🔴 DANGER (freq ≥ 3.5): [count]
  • [ad_name] — freq [X.X] | CTR [X.X]% | risk score [X]

📈 TRENDING UP (freq rising): [count]
  • [ad_name] — freq [X.X] → [X.X] over 3 days

📉 CTR DECAY: [count]
  • [ad_name] — CTR dropped [X]% week-over-week

🟡 WARNING (freq 3.0–3.5): [count]
✅ HEALTHY: [count]

💸 Spend at risk: $[X]
```

## Rules

- Flag ads where frequency rose >0.5 in the last 3 data points
- Flag ads where CTR dropped >15% compared to previous period
- Risk score = (freq / 3.5) * 60 + min(cpa_ratio, 2.0) * 40
- Awareness ads (target_cpa = 0) skip CPA checks but still get frequency alerts
