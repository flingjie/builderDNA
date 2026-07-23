---
name: builderdna
description: >
  ALWAYS use this skill when the user wants to analyze a GitHub developer or org,
  discover product/tool opportunities from developer activity, track tech trends
  in a domain (agent, LLM, MCP, etc.), or run BuilderDNA's analysis toolkit.
  Use when the user says "analyze X's GitHub", "what are people building in Y",
  "find opportunities in Z", "tech DNA", "builder insights", "trend radar",
  "what should I build", "developer landscape", "tech stack analysis",
  "competitive intelligence for X", or references BuilderDNA/builderdna directly.
  The skill wraps 5 composable CLI commands (collect → trend → pain → opportunity → report)
  so the user never needs to remember flags — you translate intent into the right command chain.
  Reads state/hypotheses.json to track exploration across conversations.
  After every run, present findings clearly and ask if they want to refine.
  Important: if the user is asking about GitHub developer analysis or tech trends,
  use this skill — don't try to analyze repos or trends without it.
---

# BuilderDNA Skill

You operate BuilderDNA — a composable toolkit that analyzes GitHub developer activity.
Each command is an independent sandbox: structured JSON input → deterministic compute → structured JSON output.
Claude Code handles all semantic reasoning and orchestration.

## Architecture

```
Claude Code (you) — reads hypotheses.json, decides what to run, interprets results
      │
      ▼
5 sandbox CLI commands (each independent, JSON-in, JSON-out)
  collect → trend → pain → opportunity → report
      │
      ▼
Global memory — DuckDB + output/*.json + state/*.json + claude-mem
```

All commands run from the project root with `PYTHONPATH=.` prefix.

## Command Map

| User says | You run |
|-----------|---------|
| "collect signals for X" / "pull GitHub data for Y" | `PYTHONPATH=. builderdna collect <domain> --window N` |
| "what's trending in X" / "show me trends" | `PYTHONPATH=. builderdna trend <domain> --data output/signals.json` |
| "what problems are developers having" / "find pain points" | `PYTHONPATH=. builderdna pain <domain> --data output/signals.json` |
| "find opportunities" / "what can I build" | `PYTHONPATH=. builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json` |
| "generate a report" / "format the results" | `PYTHONPATH=. builderdna report --data output/opportunities.json --format md` |

**Command chaining**: commands pass data via JSON files. `collect` produces `signals.json` → `trend` and `pain` consume it → `opportunity` consumes both → `report` consumes any result.

Run `builderdna --help` to see all 5 commands.

## Hypothesis Tree Workflow

The file `state/hypotheses.json` tracks exploration state across conversations. Each node has `status: exploring | validated | pruned`.

**On every analysis session:**
1. **Read** `state/hypotheses.json` — see what's being explored
2. **Run** relevant sandbox commands to gather evidence
3. **Update** node confidence and status based on results
4. **Present** findings with hypothesis state context
5. **Ask** what to explore next — add new nodes or prune dead ends

Example:
```
Read: hyp_001 "Agent Memory needs unified State Engine" is EXPLORING, confidence=0.6
  → Run collect → trend → opportunity for agent domain
  → OpenViking 27k stars, UMP protocol emerging, gap_score=2.3
  → Update hyp_001 confidence 0.6 → 0.85, status → VALIDATED
  → Add hyp_002 "MCP Observability gap" EXPLORING
  → Present: "Agent State Engine validated (gap=2.3). New lead: MCP Observability."
  → Ask: "Deep dive on either?"
```

## User Weights

Read `state/user_weights.json` at session start. Apply `scoring_bias` when interpreting opportunities.
Record feedback in `feedback_log` after each session.

## Schema Reference

`schema.md` documents exact JSON schemas for all 5 command outputs. Read it when you need field names or types.

## Config Management

- **accounts**: in `config.yaml` — developers/orgs to analyze
- **domains**: topic tags for each domain (expand to broaden search)
- **vendors**: domestic/overseas orgs tracked for competitive intelligence
- **embedding**: local Ollama config (pain command only)

Edit `config.yaml` to change accounts or topics. Confirm with user before editing.
`.env` needs: `GITHUB_TOKEN` and optionally `EMBEDDING_BASE_URL`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError` | Prefix with `PYTHONPATH=.` |
| Empty signals | Check `GITHUB_TOKEN` in `.env` |
| No pain clusters | Verify embedding endpoint (`EMBEDDING_BASE_URL`) |
| Rate limited | Wait or reduce window size |
| Import from deleted module | Old code path — verify you're in the refactored worktree |
