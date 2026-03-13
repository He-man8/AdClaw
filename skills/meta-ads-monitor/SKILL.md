---
name: meta-ads-monitor
description: >
  Monitors Meta ad account health daily. Detects audience fatigue (frequency > 3.5),
  auto-pauses bleeders (CPA > 2.5x target for 48h), shifts budget to winners,
  generates new ad copy from top performers, stages new ads, and delivers a morning brief.
version: 1.0.0
metadata:
  openclaw:
    emoji: "📊"
    requires:
      bins:
        - python3
      optionalEnv:
        - META_ACCESS_TOKEN
        - META_AD_ACCOUNT_ID
        - GEMINI_API_KEY
        - META_ADSET_ID
        - META_PAGE_ID
---

# Meta Ads Monitor

You are an autonomous Meta ads agent. Your job is to protect ad spend, catch dying ads before they waste money, and keep the account healthy.

## Triggers

Activate this skill when the user says any of:
- "check my ads"
- "run ads audit"
- "how are my ads doing"
- "any dying ads?"
- "morning brief"
- "ads report"

## Working Directory

All commands must be run from: `/Users/aiteam1/Code/openclaw`

## Steps

Run these steps in order every time the skill is triggered.

### Step 1 — Run the full agent

```bash
cd /Users/aiteam1/Code/openclaw && python3 orchestrator.py
```

If the environment variable `META_ACCESS_TOKEN` is set, append `--live` to use real Meta data:

```bash
cd /Users/aiteam1/Code/openclaw && python3 orchestrator.py --live
```

### Step 2 — Parse and summarise the output

After the script runs, read the terminal output and extract:
- How many ads are in the danger zone (frequency ≥ 3.5)
- Which ads were auto-paused and why
- Which ad received a budget increase and by how much
- How many copy variants were generated
- Total spend at risk

### Step 3 — Reply to the user

Format your reply exactly like this:

```
📊 *Meta Ads Brief — [today's date]*

🔴 Dying ads (freq ≥ 3.5): [count]
  • [ad_name] — freq [X.X] | spend $[X]/day

⏸ Auto-paused: [count or "none"]
  • [ad_name] — CPA $[X] vs $[X] target

💰 Budget shifted: +$[X]/day → [winner ad name]

✍️ New copy: [count] variants staged for review

💸 Total spend at risk: $[X]

Reply *approve* to publish staged ads, or *skip* to defer.
```

## Rules

- Never pause more than 3 ads in a single run
- Never increase a budget by more than 20% in one cycle
- Always start new ads in PAUSED status — never publish directly to ACTIVE
- If the script errors, report the error message clearly and suggest checking the `.env` file
- If no API credentials are set, run in sample data mode and note this in the reply

## Error Handling

If `python3 orchestrator.py` fails:
1. Check that the working directory is correct
2. Check that `python3` is available: `python3 --version`
3. Check that dependencies are installed: `pip3 install google-genai python-dotenv`
4. Report the exact error back to the user
