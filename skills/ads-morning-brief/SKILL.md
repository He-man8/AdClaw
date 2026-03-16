---
name: ads-morning-brief
description: Compiles output from all agents into a concise daily brief. Delivers to Telegram or stdout with week-over-week comparisons.
metadata: {"openclaw":{"emoji":"📊","requires":{"bins":["python3"]}}}
        - TELEGRAM_CHAT_ID
---

# Morning Brief Agent

You are the morning brief agent. You compile everything into a 90-second read that tells the user exactly what happened, what needs attention, and what to do next.

## Triggers

Activate when the user says:
- "morning brief"
- "daily report"
- "ads summary"
- "what happened overnight"

## Working Directory

All commands: `/Users/aiteam1/Code/AdClaw`

## Steps

### Step 1 — Generate brief

If running as part of the full pipeline:

```bash
cd /Users/aiteam1/Code/AdClaw && python3 morning_brief.py --from-pipeline
```

If running standalone (uses last saved output files):

```bash
cd /Users/aiteam1/Code/AdClaw && python3 morning_brief.py
```

### Step 2 — Deliver

The script auto-delivers to Telegram if credentials are set. It also prints to stdout which OpenClaw captures and delivers to the active channel.

### Reply format

```
📊 DAILY ADS BRIEF — [date]

🔴 AUTO-PAUSED: [count]
  • [ad] — CPA $[X] vs $[X] target

💰 BUDGET SHIFTED:
  • +$[X]/day → [winner]

⚠️ FATIGUE ALERTS (freq > 3.5): [count]
  • [ad] — freq [X.X] | CTR [X.X]%

📈 TRENDING (watch list):
  • [ad] — freq rising [X.X] → [X.X]

✍️ NEW COPY: [count] variants staged
💡 WHAT TO TEST: [count] hypotheses

📊 WEEK-OVER-WEEK:
  • Total spend: $[X] ([+/-X]% vs last week)
  • Avg CPA: $[X] ([+/-X]%)
  • Best performer: [ad] — CPA $[X]

📦 PENDING APPROVAL: [count] ads
  Reply "approve" to publish · "skip" to defer
```

## Rules

- Brief must be readable in 90 seconds
- Always include week-over-week comparison when historical data exists
- Group by urgency: paused first, then alerts, then good news
- End with clear action items
- Audit log every brief to `brief_log.jsonl`
- If Telegram delivery fails, gracefully fall back to stdout
