# AdClaw

AdClaw is a Python-based autonomous ads operations workspace. It combines a set of executable "agents" with OpenClaw skill definitions to monitor ad account health, catch fatigue, pause underperformers, reallocate budget, generate new ad creative, stage ads for publishing, and produce a daily operator brief.

The repo is designed to run in three modes:

- `sample`: uses `sample_data.csv` for safe local iteration
- `live` via Composio MCP: fetches read-only Google Ads data
- `live` via PostHog: queries synced Google Ads and Meta Ads warehouse tables

At the center of the system is [`orchestrator.py`](/Users/aiteam1/Code/AdClaw/orchestrator.py), which runs the full workflow end to end.

## New Developer Setup

### 1. Prereqs

- Python 3
- Docker + Docker Compose
- Telegram bot token from BotFather if you want Telegram access
- Optional: Gemini, PostHog, Composio, and Meta credentials for live integrations
- Optional: clone with submodules if you want the vendored project too: `git clone --recurse-submodules ...`

### 2. Clone and install

```bash
git clone <repo-url>
cd AdClaw
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 3. Fill in `.env`

Minimum useful setup:

- `OPENCLAW_GATEWAY_TOKEN`
- `TELEGRAM_BOT_TOKEN`

Live integrations:

- Gemini: `GEMINI_API_KEY`
- PostHog: `POSTHOG_API_KEY`, `POSTHOG_HOST`, `POSTHOG_PROJECT_ID`
- Composio: `COMPOSIO_MCP_URL`, `COMPOSIO_MCP_API_KEY`
- Meta: `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_ADSET_ID`, `META_PAGE_ID`

### 4. Sanity-check locally

```bash
python3 orchestrator.py
```

This is the safe sample-data path and should work even without live credentials.

### 5. Start the Telegram/OpenClaw runtime

```bash
docker compose up -d --build
```

Then pair or allowlist Telegram users in OpenClaw.

- Multiple people can DM the bot if they are paired.
- Multiple people can use the bot in a Telegram group if that group is allowlisted.
- This is separate from `TELEGRAM_CHAT_ID`, which is only for optional outbound Python-side Telegram sends.

After any `.env` change, restart:

```bash
docker compose up -d --build
```

### 6. Run live modes

Google Ads via Composio:

```bash
python3 orchestrator.py --live
```

Google Ads + Meta Ads via PostHog:

```bash
python3 orchestrator.py --posthog
```

### 7. Full live action support

For real pause, budget update, creative creation, and activation flows, this repo also expects an external `social` CLI used by [`ad_publisher.py`](/Users/aiteam1/Code/AdClaw/ad_publisher.py) and [`budget_guardian.py`](/Users/aiteam1/Code/AdClaw/budget_guardian.py). That tool is not installed by `requirements.txt` or the Docker image, so a new developer needs that provisioned separately for full publishing capability.

## What The Repo Contains

There are two main layers:

- Runtime scripts in the repo root that do the actual work
- Skill definitions in [`skills/`](/Users/aiteam1/Code/AdClaw/skills) that describe how an OpenClaw agent should invoke those scripts

In practice, the skills are the operator interface and the Python modules are the execution engine.

## Architecture

The pipeline currently looks like this:

1. Data is loaded from one of three sources:
   - [`sample_data.csv`](/Users/aiteam1/Code/AdClaw/sample_data.csv)
   - [`composio_fetch.py`](/Users/aiteam1/Code/AdClaw/composio_fetch.py) for Google Ads via Composio MCP
   - [`posthog_fetch.py`](/Users/aiteam1/Code/AdClaw/posthog_fetch.py) for Google Ads and Meta Ads via PostHog
2. [`health_check.py`](/Users/aiteam1/Code/AdClaw/health_check.py) scores fatigue and writes a structured health report plus rolling history.
3. [`budget_guardian.py`](/Users/aiteam1/Code/AdClaw/budget_guardian.py) tracks multi-run CPA behavior, pauses "bleeders", and proposes budget shifts.
4. [`copy_writer.py`](/Users/aiteam1/Code/AdClaw/copy_writer.py) analyzes winning ads and generates fresh variants, optionally using Gemini.
5. [`content_lab.py`](/Users/aiteam1/Code/AdClaw/content_lab.py) turns historical performance into reusable patterns, hypotheses, and experiment tracking state.
6. [`ad_publisher.py`](/Users/aiteam1/Code/AdClaw/ad_publisher.py) stages generated ads through a CLI integration, defaulting to paused status.
7. [`morning_brief.py`](/Users/aiteam1/Code/AdClaw/morning_brief.py) compiles outputs into a brief for stdout or Telegram delivery.

The pipeline persists operational state to JSON and JSONL files so later runs can reason over trend and experiment history.

## Data Flow

### Inputs

- Ad metrics from sample CSV, Composio MCP, or PostHog HogQL
- Environment configuration from `.env`
- Optional Gemini API access for copy and hypothesis generation
- Optional Telegram credentials for delivery
- Optional Meta/social CLI tooling for live publishing and pause actions

### Intermediate artifacts

- [`output/health_report.json`](/Users/aiteam1/Code/AdClaw/output/health_report.json)
- [`output/health_history.json`](/Users/aiteam1/Code/AdClaw/output/health_history.json)
- [`generated_copy.json`](/Users/aiteam1/Code/AdClaw/generated_copy.json)
- [`output/creative_playbook.json`](/Users/aiteam1/Code/AdClaw/output/creative_playbook.json)
- [`output/content_hypotheses.json`](/Users/aiteam1/Code/AdClaw/output/content_hypotheses.json)
- [`output/experiment_log.json`](/Users/aiteam1/Code/AdClaw/output/experiment_log.json)
- [`state.json`](/Users/aiteam1/Code/AdClaw/state.json)
- [`guardian_log.jsonl`](/Users/aiteam1/Code/AdClaw/guardian_log.jsonl) when pauses are logged
- [`upload_log.json`](/Users/aiteam1/Code/AdClaw/upload_log.json)
- [`brief_log.jsonl`](/Users/aiteam1/Code/AdClaw/brief_log.jsonl)

### Outputs

- Terminal summaries for each agent
- JSON artifacts for downstream steps
- Optional Telegram brief delivery
- Optional staged or activated ads through external CLI tooling

## Key Files

### Core execution

- [`orchestrator.py`](/Users/aiteam1/Code/AdClaw/orchestrator.py): end-to-end runner for the full ads workflow
- [`config.py`](/Users/aiteam1/Code/AdClaw/config.py): central typed settings layer using `pydantic-settings`

### Analysis and optimization agents

- [`health_check.py`](/Users/aiteam1/Code/AdClaw/health_check.py): fatigue detection, trend detection, CTR decay monitoring, report persistence
- [`budget_guardian.py`](/Users/aiteam1/Code/AdClaw/budget_guardian.py): 48-hour bleed tracking, auto-pause logic, budget reallocation, action logging
- [`copy_writer.py`](/Users/aiteam1/Code/AdClaw/copy_writer.py): winner selection and LLM-driven copy generation with mock fallbacks
- [`content_lab.py`](/Users/aiteam1/Code/AdClaw/content_lab.py): pattern mining, playbook updates, test hypothesis generation, experiment deduplication
- [`morning_brief.py`](/Users/aiteam1/Code/AdClaw/morning_brief.py): assembles a concise operator-facing brief from saved artifacts

### Data connectors

- [`composio_fetch.py`](/Users/aiteam1/Code/AdClaw/composio_fetch.py): read-only MCP client for Google Ads data via Composio
- [`posthog_fetch.py`](/Users/aiteam1/Code/AdClaw/posthog_fetch.py): read-only HogQL and insights client for PostHog-backed Google Ads and Meta Ads data

### Activation and publishing

- [`ad_publisher.py`](/Users/aiteam1/Code/AdClaw/ad_publisher.py): stages generated ads with default `PAUSED` safety behavior

### Older or supporting files

- [`frequency_monitor.py`](/Users/aiteam1/Code/AdClaw/frequency_monitor.py): earlier standalone fatigue monitor; much of its responsibility now lives in `health_check.py`
- [`hello.py`](/Users/aiteam1/Code/AdClaw/hello.py): empty placeholder file
- [`sample_data.csv`](/Users/aiteam1/Code/AdClaw/sample_data.csv): local seed dataset with 15 ads and creative fields

### Skills

Each folder under [`skills/`](/Users/aiteam1/Code/AdClaw/skills) contains a `SKILL.md` that maps user intents to one of the root scripts:

- [`skills/ads-orchestrator/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-orchestrator/SKILL.md)
- [`skills/ads-health-check/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-health-check/SKILL.md)
- [`skills/ads-budget-guardian/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-budget-guardian/SKILL.md)
- [`skills/ads-copywriter/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-copywriter/SKILL.md)
- [`skills/ads-content-lab/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-content-lab/SKILL.md)
- [`skills/ads-publisher/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-publisher/SKILL.md)
- [`skills/ads-morning-brief/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-morning-brief/SKILL.md)
- [`skills/ads-composio-fetch/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-composio-fetch/SKILL.md)
- [`skills/ads-posthog-fetch/SKILL.md`](/Users/aiteam1/Code/AdClaw/skills/ads-posthog-fetch/SKILL.md)

## Environment Variables

Configuration is centralized in [`config.py`](/Users/aiteam1/Code/AdClaw/config.py). The main groups are:

- OpenClaw gateway settings
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_ADSET_ID`, `META_PAGE_ID`
- `COMPOSIO_MCP_URL`, `COMPOSIO_MCP_API_KEY`
- `POSTHOG_API_KEY`, `POSTHOG_HOST`, `POSTHOG_PROJECT_ID`

See [`.env.example`](/Users/aiteam1/Code/AdClaw/.env.example) for a full template.

## Docker And OpenClaw

The container story is built around OpenClaw:

- [`Dockerfile`](/Users/aiteam1/Code/AdClaw/Dockerfile) extends `ghcr.io/openclaw/openclaw:latest` and installs Python dependencies
- [`docker-compose.yml`](/Users/aiteam1/Code/AdClaw/docker-compose.yml) runs:
  - `openclaw-gateway`
  - `openclaw-cli`

Notable mounts:

- repo `skills/` is mounted into OpenClaw's skills directory
- `.openclaw/` is mounted for runtime state
- the repo itself is mounted into the container workspace

This makes the repo both an application and a packaged OpenClaw workspace.

## Design Notes

- Safety-first behavior is baked in:
  - new ads are staged as `PAUSED`
  - budget increases are capped at 20% per cycle
  - auto-pauses are capped at 3 ads per run
  - Composio access is explicitly restricted to read-only tool slugs
- The system prefers graceful degradation:
  - no Gemini key -> mock copy and rule-based hypotheses
  - no Telegram creds -> print brief to stdout
  - no live data creds -> sample data mode
- State matters:
  - `health_check.py` and `budget_guardian.py` only get more useful over repeated runs because they accumulate history

## Suggested Mental Model

If you are new to the codebase, the simplest way to think about it is:

- `posthog_fetch.py` and `composio_fetch.py` bring data in
- `health_check.py` and `budget_guardian.py` protect spend
- `copy_writer.py` and `content_lab.py` generate the next creative moves
- `ad_publisher.py` stages execution
- `morning_brief.py` tells a human what happened
- `orchestrator.py` ties everything together

## Repository Structure

```text
.
├── orchestrator.py
├── config.py
├── health_check.py
├── budget_guardian.py
├── copy_writer.py
├── content_lab.py
├── ad_publisher.py
├── morning_brief.py
├── composio_fetch.py
├── posthog_fetch.py
├── frequency_monitor.py
├── sample_data.csv
├── skills/
├── output/
├── vendor/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Dependencies

The repo currently declares a small Python dependency set in [`requirements.txt`](/Users/aiteam1/Code/AdClaw/requirements.txt):

- `google-genai`
- `python-dotenv`
- `pydantic`
- `pydantic-settings`
- `requests`
- `composio`

Some runtime paths also implicitly expect external tools or libraries that are not pinned here, such as:

- Meta/Facebook Business SDK for `health_check.py --live`
- a `social` CLI used by `budget_guardian.py` and `ad_publisher.py`

## Where To Start

If you want to understand the code quickly, read in this order:

1. [`orchestrator.py`](/Users/aiteam1/Code/AdClaw/orchestrator.py)
2. [`config.py`](/Users/aiteam1/Code/AdClaw/config.py)
3. [`health_check.py`](/Users/aiteam1/Code/AdClaw/health_check.py)
4. [`budget_guardian.py`](/Users/aiteam1/Code/AdClaw/budget_guardian.py)
5. [`copy_writer.py`](/Users/aiteam1/Code/AdClaw/copy_writer.py)
6. [`content_lab.py`](/Users/aiteam1/Code/AdClaw/content_lab.py)
7. [`morning_brief.py`](/Users/aiteam1/Code/AdClaw/morning_brief.py)
8. the relevant `skills/*/SKILL.md`
