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
  The skill wraps 7 composable CLI commands (collect → trend → pain → opportunity → report → config → observability)
  so the user never needs to remember flags — you translate intent into the right command chain.
  Reads state/hypotheses.json to track exploration across conversations.
  Uses goal-driven short-circuit pipeline to select the optimal execution path.
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
Claude Code (you) — reads hypotheses.json, maps intent → commands via short-circuit pipeline
      │
      ▼
7 sandbox CLI commands (each independent, JSON-in, JSON-out)
  collect → trend → pain → opportunity → report → config → observability
      │
      ▼
Global memory — SQLite + output/*.json + state/*.json + claude-mem
```

The pipeline is driven by a single state file and one principle:

- **`state/hypotheses.json`** — cross-session exploration tree. Tracked hypotheses influence domain and topic choices across sessions.
- **Principle**: the command dependency graph is almost linear (branch factor 1-2). A full search algorithm (A*) adds complexity without improving decisions over a simple goal → commands mapping with short-circuit rules. See ADR-006 for the rationale.

All commands run from the project root with `PYTHONPATH=.` prefix.

## Goal-Driven Short-Circuit Pipeline (ADR-006)

### Step 1: Determine Goal

Infer the goal from the user's request:

| User says | Goal |
|-----------|------|
| "what's trending in X" / "show me trends" / "trend radar" | `trend_radar` |
| "find opportunities in X" / "what can I build" / "analyze X" | `opportunity_discovery` |
| "check my hypothesis" / "validate X" / "is Y true" | `hypothesis_validation` |
| Anything with a specific hypothesis ID or node name | `hypothesis_validation` |
| Default (unclear intent) | `opportunity_discovery` |

If `hypothesis_validation`: identify which hypothesis node(s) are the target. If none specified, use the highest-confidence `exploring` node.

### Step 2: Goal → Commands

Each goal maps to a fixed ordered command sequence, respecting the dependency graph. Always execute `trend` before `pain` (8s vs 92s — cheap data informs the expensive decision).

| Goal | Required | Optional (after short-circuit check) |
|------|----------|--------------------------------------|
| `trend_radar` | collect → trend → report | — |
| `opportunity_discovery` | collect → trend → report | pain → opportunity (both, or neither) |
| `hypothesis_validation` | collect → observability | trend (if you want supporting evidence) |

**Command templates** (always prefix with `PYTHONPATH=.`):

| Command | Template |
|---------|----------|
| collect | `PYTHONPATH=. uv run builderdna collect {domain} --window {window} --output output/signals.json` |
| trend | `PYTHONPATH=. uv run builderdna trend {domain} --data output/signals.json --output output/trends.json` |
| pain | `PYTHONPATH=. uv run builderdna pain {domain} --data output/signals.json --output output/pain_clusters.json` |
| opportunity | `PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json --output output/opportunities.json` |
| report | `PYTHONPATH=. uv run builderdna report --data {data_file} --format md` |
| config | `PYTHONPATH=. uv run builderdna config --show` |
| observability | `PYTHONPATH=. uv run builderdna observability --all --domain {domain}` |

Substitute `{domain}` with the target domain, `{window}` with 365 (default) or user-specified value.

### Step 3: Short-Circuit Check (the only decision point)

After required commands complete, check whether to run optional ones:

**Trend signal check** (for `opportunity_discovery`):
- Read `output/trends.json`
- If ALL topics have `gap_score < 1.0` AND no topics have rising velocity:
  → Ask: "Trend data shows low opportunity signals in this domain. Skip pain + opportunity analysis and just report trends?"
- If user agrees → skip pain + opportunity, go to report
- If ANY topic has `gap_score >= 1.0` or rising velocity → proceed with optional commands

**Cost budget check** (all goals):
- Track wall-clock time across all commands
- If cumulative time exceeds 5 minutes → ask whether to continue or stop

**Hypothesis check** (for `hypothesis_validation`):
- If target hypothesis reached `validated` or `pruned` → stop immediately

### Step 4: After Commands Complete

1. Run `report` to generate the final output (if not already done)
2. Read command outputs, update hypothesis confidence in `state/hypotheses.json`
3. Present findings clearly, referencing hypothesis state
4. Ask: "Want to refine with observability diagnostics?" → if yes, run `observability`
5. Ask what to explore next

## Hypothesis Tree Workflow

The file `state/hypotheses.json` tracks exploration state across conversations. Each node has `status: exploring | validated | pruned`.

**On every analysis session:**
1. **Read** `state/hypotheses.json` — see what's being explored
2. **Parse** user intent → goal (Step 1 above)
3. **Execute** goal's command sequence (Step 2-3 above)
4. **Update** node confidence and status based on results
5. **Present** findings with hypothesis state context
6. **Ask** what to explore next — add new nodes or prune dead ends

Example:
```
Read: hyp_001 "Agent Memory needs unified State Engine" is EXPLORING, confidence=0.6
  → Goal: opportunity_discovery, domain: agent
  → Required: collect → trend
  → collect done (45s), signals.json ready
  → trend reveals: "Agent State Engine" gap_score=2.3, velocity=rising
  → Short-circuit check: gap >= 1.0 → proceed with optional
  → Update hyp_001 confidence 0.6 → 0.7
  → pain → opportunity → report
  → Present: "Agent State Engine validated (gap=2.3). New lead: MCP Observability."
  → Ask: "Deep dive on either?"
```

## User Weights

Read `state/user_weights.json` at session start. Apply `scoring_bias` when interpreting opportunities.
Record feedback in `feedback_log` after each session.

## User DNA (Value Discovery Integration)

BuilderDNA now integrates with the `value-discovery` Skill for personalized analysis.

**On every session start:**
1. Check if `state/user_dna.json` exists and has non-empty values (check `values.environment.ranking` has entries).
2. **If missing or empty:** This is a first-time user. BEFORE running `collect`, trigger the `value-discovery` Skill:
   - Say: "在开始分析之前，我想先了解你的偏好——这样分析结果会更贴合你。我们花5-8分钟快速聊一下？"
   - If user agrees → invoke `value-discovery` skill, then continue with collect.
   - If user declines → proceed without personalization (no `--user-dna` flag).
3. **If exists:** Ask: "我之前已经了解过你的偏好，要不要更新一下？" 
   - If yes → invoke `value-discovery` skill for an incremental update.
   - If no → use existing DNA.

**When User DNA is available, pass it to commands:**
```bash
# Collect with personalization
PYTHONPATH=. uv run builderdna collect <domain> --window N --user-dna state/user_dna.json --output output/signals.json

# Opportunity with personalized scoring
PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json --user-dna state/user_dna.json
```

**When presenting results:**
- If personalized: mention "已根据你的价值偏好做了个性化排序" and highlight the `alignment_reason` on top opportunities.
- Show both `gap_score` (客观市场机会) and `personalized_score` (对你的匹配度) side by side.
- If a high-gap opportunity has low personalization, flag it: "这个市场机会很大，但和你的偏好不太匹配——要不要了解一下？"

The `--user-dna` flag is optional on both `collect` and `opportunity` — omitting it gives objective/unpersonalized results (backward compatible).

## Observability — Self-Iteration Check

After running a full analysis pipeline, optionally run diagnostics. **For interactive observability sessions, invoke the `observability` skill** — it handles result interpretation and user interaction.

```bash
# Run all observability checks for the domain
PYTHONPATH=. uv run builderdna observability --all --domain <domain>
```

This runs three checks:
1. **Mismatch detection** — compares current behavior patterns against User DNA, flags potential value drift
2. **Snapshot comparison** — validates past prediction snapshots against today's data
3. **Hypothesis pruning** — checks for stale hypotheses that should be reviewed or retired

**When to trigger:** After every 3-5 complete analysis runs, or when the user mentions "check my predictions", "validate assumptions", "任何东西变了吗", "我之前猜的对不对". Results are written to `output/observability_check_<domain>.json`.

## Schema Reference

`schema.md` documents exact JSON schemas for all 7 command outputs. Read it when you need field names or types.

## Builder's Lens — 深度项目分析

When the user wants "builder 视角", "从开发者角度分析", "值得借鉴的做法", "commit 历史分析", or wants to learn from a successful project's approach, read `references/builder-lens.md` and apply its 10-dimension framework.

This is a **qualitative, Claude-driven analysis** — no sandbox command covers it. Use `gh api` to fetch commit history, releases, PRs, and contributor stats, then interpret the patterns across 10 dimensions: value quantification, versioning strategy, platform coverage, README architecture, benchmark credibility, commit discipline, core IP positioning, contributor gradient, development cadence, and brand personality.

**When to use**: after trending discovery or deep-dive, when the user sees a standout project and wants to understand *how* it was built, not just *what* it does.

## Reference Files

Read these when needed:

| File | When to Read | Content |
|------|-------------|---------|
| `references/builder-lens.md` | Before builder's perspective analysis | 10-dimension methodology for analyzing project success patterns |
| `schema.md` | Before reading command outputs | JSON schemas for all 7 commands |
| `state/hypotheses.json` | Session start | Exploration state tree |
| `docs/adr/` | Architecture understanding | All architecture decision records |
| `docs/adr/ADR-006-short-circuit-pipeline.md` | Understanding the pipeline | Goal-driven short-circuit design rationale |

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
| Pain keeps getting skipped | Trend gap_scores are low — try broadening domain topics in config.yaml first |
