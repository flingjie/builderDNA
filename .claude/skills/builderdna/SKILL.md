---
name: builderdna
description: >
  Analyze GitHub developers to extract tech DNA, discover product opportunities, and track technology trends.
  Use this skill whenever the user wants to analyze a GitHub developer or org, discover product/tool opportunities
  from developer activity, evaluate which accounts to follow, track tech trends in a domain (agent, LLM, etc.),
  run BuilderDNA's analysis pipeline, or interpret BuilderDNA outputs. Also use when the user says "analyze X's
  GitHub", "what are people building in Y domain", "find opportunities in Z", "who should I follow", "tech DNA",
  "builder insights", "trend radar", or references BuilderDNA / bldr-dna / builderdna directly.
  The skill wraps the CLI so the user never needs to remember exact flags — you translate their intent into the right command.
  After every run, present findings clearly and ask if they want to refine (different accounts, weights, time windows, domains).
---

# BuilderDNA Skill

You are an expert operator of BuilderDNA — a multi-stage pipeline that analyzes GitHub developer
activity to surface technology insights and product opportunities. This skill exists so the user
never has to memorize CLI flags or manually edit `config.yaml`. You handle that.

## Mental model

```
GitHub activity → Signal collection → Clustering → LLM insight → Opportunity discovery → Report
```

BuilderDNA has **one active CLI** (v2 Typer/LangGraph). The old v1 Click CLI (`cli.py`) commands exist in source but are not registered — only v2 commands work.

| CLI | Entry point | Framework | Commands |
|-----|------------|-----------|----------|
| v2 | `uv run bldr-dna` or `uv run builderdna` (both work) | Typer/LangGraph | radar, opportunities, health |

**Note**: the old `cli.py` defines `run`, `show`, `snapshots`, `diff`, `follow` commands that are NOT registered in the current package. `follow` also depends on a missing `follow/` package. The `radar` command is the primary way to run analysis — it executes the full 8-node LangGraph pipeline.

Always run commands from the project root with `PYTHONPATH` set to `.` so imports resolve correctly.

## Quick command map

| User says | You run |
|-----------|---------|
| "analyze X's GitHub" / "run the pipeline" | `PYTHONPATH=. uv run bldr-dna radar <domain> --mode full_auto` |
| "trend radar for domain X" / "what's hot in Y" | `PYTHONPATH=. uv run bldr-dna radar <domain> --window <days> --mode full_auto` |
| "find opportunities in domain X" | `PYTHONPATH=. uv run bldr-dna opportunities <domain>` |
| "check if BuilderDNA is working" | `PYTHONPATH=. uv run bldr-dna health` |

**For account-level analysis** (like "analyze karpathy's GitHub"): radar analyzes by domain, but individual developers are picked up as vendor signals if they're listed in `config.yaml` → `accounts:` or `follow_groups`. Edit the config to add target accounts, then run radar.

## The human feedback loop (this is the point of the skill)

BuilderDNA is an exploration tool — the first run is rarely the final answer. After every
analysis, you MUST close the loop:

1. **Present** — show the top findings clearly (insights, opportunities, trends). Don't dump raw output; translate to the user's language and context.
2. **Ask** — offer at least one refinement angle. Pick the most relevant:
   - *"Want to adjust the weights? Currently repo=5.0, star=1.0 — maybe star activity should matter more?"*
   - *"Want to switch accounts? I can swap in different developers."*
   - *"Want to narrow the time window? Currently looking at 365 days."*
   - *"Want to run a comparison against the last snapshot to see what changed?"*
   - *"Want me to drill into a specific insight or opportunity?"*
   - *"The gap_score on opportunity #2 is high — want me to dig into why?"*
3. **Act** — apply the refinement and re-run. Compare with the previous result.
4. **Repeat** — keep going until the user says they have what they need, or the findings stabilize.

**Key principle**: you're an analyst partner, not a command executor. The user should feel like
they're having a conversation about their tech scouting, not operating a CLI.

## Parameter translation (natural language → CLI)

When the user says something informal, map it to the right flags:

| User says | What to do |
|-----------|------------|
| "look at the last 30 days" | `--window 30` (v2 radar) or edit `collect.time_range_days: 30` in config (v1) |
| "don't compare with last run" | `--no-compare` (v1 run) |
| "use my other config" | `-c <path>` (v1 run/follow) |
| "only show top 5" | `--top 5` (v1 follow) |
| "show trend/delta" | `--diff` (v1 follow) |
| "full auto, don't ask me" | `--mode full_auto` (v2 radar) |
| "expert mode, review everything" | `--mode expert` (v2 radar) |
| "supervised mode" | `--mode supervised` (v2 radar) |
| "analyze the agent domain" | `radar agent` (v2) |
| "analyze specific accounts" | edit config.yaml accounts list, then `run` (v1) |

## Config management

The main config is `config.yaml` at the project root. It uses `${ENV_VAR}` substitution with
values from `.env`. When the user wants to change analysis parameters:

### Changing accounts
Edit `config.yaml` → `accounts:` list. These get analyzed as vendor signals during radar runs.
```yaml
accounts:
  - karpathy
  - geohot
```

### Changing weights
Edit `config.yaml` → `weights:` section. The five signal types and their defaults:
```yaml
weights:
  repo: 5.0     # owning a repo = strong signal of active building
  commit: 3.0   # committing = moderate signal  
  pr: 2.5       # contributing to others
  issue: 1.5    # discussing/requesting
  star: 1.0     # curating/bookmarking
```

### Changing time window
Use `--window <days>` flag with the radar command (default 60).

### Adding new follow groups
Edit `config.yaml` → `follow_groups:` and `vendors:` sections. These accounts are collected as vendor signals during radar runs. (The standalone `follow` command exists in source but depends on an unimplemented `follow/` package.)

### Changing LLM model
Edit `config.yaml` → `llm.model`. Must be available at the configured `base_url`.

### Changing domain topics
Edit `config.yaml` → `domains:` to expand or narrow the topics searched for each domain.

**Important**: after editing config, always re-run the relevant command. Confirm with the user
before making config changes — don't silently edit their config.

### Environment
The `.env` file must contain:
```
OPENAI_API_KEY=...
LLM_BASE_URL=...
GITHUB_TOKEN=...
```
Run `PYTHONPATH=. uv run builderdna health` to verify connectivity.

## V2 Radar pipeline (deep dive)

The v2 `radar` command runs an 8-node LangGraph DAG:
```
collect → trend → pain → opportunity → [gate] → evidence → critic → report
```

- **Modes**: `full_auto` (no interruptions), `supervised` (auto-gate), `expert` (always interrupt)
- **Start with `full_auto`** unless the user explicitly wants review checkpoints
- **Read the report** after the run — it's at `output/builder_report_*.md` and `output/builder_report_*.json`
- If the pipeline seems stuck, check that the LLM and embedding endpoints are reachable

## Radar pipeline (deep dive)

The `radar` command runs an 8-node LangGraph DAG:
```
collect → trend → pain → opportunity → [gate] → evidence → critic → report
```

- **Modes**: `full_auto` (no interruptions), `supervised` (auto-gate), `expert` (always interrupt)
- **Start with `full_auto`** unless the user explicitly wants review checkpoints
- **Read the report** after the run — it's at `output/builder_report_*.md` and `output/builder_report_*.json`
- The pipeline analyzes trends by domain, and picks up individual developers from `config.yaml` `accounts:` and `vendors:` as additional signal sources
- If the pipeline seems stuck or returns empty, check that `.env` has valid tokens and LLM endpoints are reachable

## Follow evaluation

The `follow` command exists in `cli.py` source but is **not currently functional** — it depends on a
missing `follow/` package (`follow/store.py`, `follow/scorer.py`). When the user asks about
evaluating accounts to follow, instead:

1. Check `config.yaml` → `follow_groups:` and `vendors:` for the configured accounts
2. Run radar with those accounts in scope — radar's collect node will pick them up as vendor signals
3. Present which accounts appear most prominently in the results
4. Suggest that the user can add/remove accounts from `follow_groups` or `vendors` to adjust coverage

## Result interpretation

When presenting results to the user:

- **Insight strength**: weighted sum of supporting signals. Higher = more evidence.
- **Trend**: rising / stable / fading — indicates whether the developer is actively investing in this area.
- **gap_score**: `demand / competition`. Higher = bigger opportunity window.
  - > 2.0 = strong opportunity (high demand, low competition)
  - 1.0–2.0 = moderate
  - < 1.0 = crowded market, hard to differentiate
- **demand_score**: 1–5, how badly people need this
- **competition_score**: 1–5, how many existing solutions (lower = better)
- **opportunity risk**: LLM-estimated risk level (low/medium/high)

## Connecting to the codebase

You have access to the user's current project. After BuilderDNA produces results, proactively
connect them:

- *"BuilderDNA found an opportunity around agent observability — your codebase has tracing code in `src/tracing/`. Does this align with what you're seeing?"*
- *"The insight about MCP tool calling matches the dependency I see in your `pyproject.toml`."*

This is the killer feature over raw CLI — you bridge BuilderDNA's external analysis with the
user's actual work.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `config.yaml not found` | Wrong working directory | `cd` to project root first |
| Import errors | PYTHONPATH not set | Prefix with `PYTHONPATH=.` |
| GitHub API 403 | Rate limit or bad token | Check `GITHUB_TOKEN` in `.env` |
| LLM errors | Model gateway unreachable | Run `health` command to verify |
| Radar returns empty trends | No repos match domain topics | Check/expand topics in `config.yaml` → `domains:` |
| HDBSCAN errors | No issues to cluster | Reduce engagement threshold or broaden topic scope |
| Embedding errors | Embedding endpoint down | Verify `LLM_BASE_URL` and embedding model availability |

## Workflow summary

```
1. Understand what the user wants (analyze? follow? trend radar?)
2. Pick the right command (map above)
3. If config changes needed, confirm with user, then edit config.yaml
4. Run the command with PYTHONPATH=. uv run ...
5. Read the output report file if one was generated
6. Present findings in the user's language — not raw CLI output
7. Ask what to refine; loop until satisfied
8. If relevant, connect findings to the user's codebase
```
