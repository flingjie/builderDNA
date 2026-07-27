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
  Uses GOAP A* planning (dynamic replanning) to select the optimal execution path.
  After every run, present findings clearly and ask if they want to refine.
  Important: if the user is asking about GitHub developer analysis or tech trends,
  use this skill — don't try to analyze repos or trends without it.
---

# BuilderDNA Skill

You operate BuilderDNA — a composable toolkit that analyzes GitHub developer activity.
Each command is an independent sandbox: structured JSON input → deterministic compute → structured JSON output.
Claude Code handles all semantic reasoning and orchestration, including GOAP A* planning.

## Architecture

```
Claude Code (you) — reads hypotheses.json + plan_state.json, runs GOAP A* loop
      │
      ▼
7 sandbox CLI commands (each independent, JSON-in, JSON-out)
  collect → trend → pain → opportunity → report → config → observability
      │
      ▼
Global memory — SQLite + output/*.json + state/*.json + claude-mem
```

Two key state files drive the planning loop:

- **`state/hypotheses.json`** — cross-session exploration tree + goal + planning config (ADR-004)
- **`state/plan_state.json`** — current-session planning state (path taken, cost, data readiness)
- **`state/run_stats.json`** — historical command durations for cost estimates

All commands run from the project root with `PYTHONPATH=.` prefix.

## GOAP A* Planning Loop (ADR-004)

Before running any command, you must run the planning loop. This replaces the old "read hypotheses → pick commands from a fixed map" approach with dynamic, cost-aware path selection.

### Step 0: Session Initialization

On first invocation in a session:

1. Read `state/hypotheses.json` — determine the goal (user's intent or default `opportunity_discovery`)
2. Read `state/plan_state.json` — load the action catalog and cost estimates
3. Read `state/run_stats.json` (if empty, use conservative defaults from plan_state.json's `action_catalog`)
4. Set `session_id` to today's date (e.g., `"2026-07-27-001"`), `goal`, and `target_domain`
5. Initialize `current_state`:
   - `data_ready`: check which output files exist (`output/signals.json`, `output/trends.json`, etc.)
   - `data_missing`: all output files NOT in data_ready
   - `hypotheses_validated` / `hypotheses_exploring`: from hypotheses.json
   - `user_dna_loaded`: check `state/user_dna.json` exists and has values
   - `actions_executed`: []
6. Write initialized `plan_state.json`

### Step 1: Determine Goal

Infer the goal from the user's request using these patterns:

| User says | Goal |
|-----------|------|
| "what's trending in X" / "show me trends" / "trend radar" | `trend_radar` |
| "find opportunities in X" / "what can I build" / "analyze X" | `opportunity_discovery` |
| "check my hypothesis" / "validate X" / "is Y true" | `hypothesis_validation` |
| Anything with a specific hypothesis ID or node name | `hypothesis_validation` |
| Default (unclear intent) | `opportunity_discovery` |

Write the goal to `plan_state.json`.

If `hypothesis_validation`: identify which hypothesis node(s) are the target. If none specified, use the highest-confidence `exploring` node.

### Step 2: The Planning Loop (Dynamic Replanning)

Execute this loop, one action at a time, until the goal's stop condition is met:

```
WHILE goal not reached:
  1. Read current state from plan_state.json
  2. Identify EXECUTABLE actions:
     - Check each action in the action_catalog
     - An action is executable if ALL its preconditions are in data_ready
     - (preconditions can also be empty, meaning always executable)
  3. For each executable action, compute f(n) = g(n) + h(n):
     - g(n): cost_so_far_s + this action's avg_cost_s (from run_stats or action_catalog)
     - h(n): estimate of remaining cost to goal
       * Count how many REQUIRED actions (from goal_conditions) are still unexecuted
       * Sum their avg_cost_s
     - SEMANTIC ADJUSTMENT: if the last executed action produced output that changes
       the picture, adjust h(n) for affected actions:
       * If trend output shows low gap_score (< 1.0) across all topics → inflate h(n)
         for pain and opportunity (the planner should consider early termination)
       * If a hypothesis was just validated → reduce h(n) (we're closer to goal)
       * If a command errored → increase that action's g(n) for this session
  4. SELECT the action with lowest f(n)
  5. EXECUTE the action using its command template from action_catalog
     - Replace {domain} with target_domain
     - Replace {window} with appropriate value (default 365, or user-specified)
     - Replace {data_file} with the appropriate JSON path
     - ALWAYS prefix with PYTHONPATH=.
  6. READ the command's output from the output/ directory
  7. UPDATE plan_state.json:
     - Move produced data from data_missing to data_ready
     - Append action name to actions_executed and path_taken
     - Update cost_so_far_s (add actual elapsed seconds from the command output's stats)
     - If the output revealed useful info, update hypothesis confidence in hypotheses.json
     - CALL persist_run_stats (via Python: `PYTHONPATH=. uv run python -c "from observability.telemetry import persist_run_stats; persist_run_stats('{command}', {elapsed})"`)
  8. CHECK stop condition from goal_conditions:
     - If met → break out of loop, proceed to report
     - If not met → loop back to step 1 (re-search with updated state)
```

### Step 3: Early Termination Check

After each action, evaluate whether continuing is worth the cost:

- **Low opportunity signal**: if `trend` output shows all topics with gap_score < 1.0 and no topics with rising velocity, the planner should ask the user: "Trend data shows low opportunity signals in this domain. Skip pain/opportunity analysis and just report trends?"
- **Cost budget exceeded**: if `cost_so_far_s` exceeds 300s (5 min), ask the user whether to continue or stop
- **Hypothesis resolved**: if `hypothesis_validation` goal and target hypothesis reached `validated` or `pruned`, stop immediately

### Step 4: After Goal Reached

Once the stop condition is met:

1. Run `report` action to generate the final output
2. Present findings clearly, referencing hypothesis state
3. Ask: "Want to refine with observability diagnostics?" → if yes, run `observability`
4. Ask what to explore next

## Command Map (Fallback — when planning state is unavailable)

| User says | You run |
|-----------|---------|
| "collect signals for X" / "pull GitHub data for Y" | `PYTHONPATH=. uv run builderdna collect <domain> --window N` |
| "what's trending in X" / "show me trends" | `PYTHONPATH=. uv run builderdna trend <domain> --data output/signals.json` |
| "what problems are developers having" / "find pain points" | `PYTHONPATH=. uv run builderdna pain <domain> --data output/signals.json` |
| "find opportunities" / "what can I build" | `PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json` |
| "generate a report" / "format the results" | `PYTHONPATH=. uv run builderdna report --data output/opportunities.json --format md` |
| "show config" / "what's my setup" | `PYTHONPATH=. uv run builderdna config --show` |
| "check my predictions" / "validate assumptions" / "run diagnostics" | `PYTHONPATH=. uv run builderdna observability --all --domain <domain>` |

**Command chaining**: commands pass data via JSON files. `collect` produces `signals.json` → `trend` and `pain` consume it → `opportunity` consumes both → `report` consumes any result.

Run `builderdna --help` to see all 7 commands.

## Hypothesis Tree Workflow

The file `state/hypotheses.json` tracks exploration state across conversations. Each node has `status: exploring | validated | pruned`.

**On every analysis session:**
1. **Read** `state/hypotheses.json` — see what's being explored and what the goal is
2. **Initialize** `state/plan_state.json` with the current goal and state
3. **Run** the GOAP A* planning loop to select and execute actions
4. **Update** node confidence and status based on results
5. **Present** findings with hypothesis state context
6. **Ask** what to explore next — add new nodes or prune dead ends

Example:
```
Read: hyp_001 "Agent Memory needs unified State Engine" is EXPLORING, confidence=0.6
  → Goal: opportunity_discovery, domain: agent
  → A* selects: collect (only executable action, preconditions satisfied)
  → collect done (45s), signals.json ready
  → A* selects: trend (f=45+8+remaining=61) over pain (f=45+92+remaining=149)
  → trend reveals: "Agent State Engine" gap_score=2.3, velocity=rising
  → Update hyp_001 confidence 0.6 → 0.7
  → A* selects: pain (now worth it — trend showed signal) → opportunity → report
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
| `state/hypotheses.json` | Session start | Exploration state tree + goal + planning config |
| `state/plan_state.json` | Every planning cycle | Current session state, action catalog, cost estimates |
| `state/run_stats.json` | Cost estimation | Historical command duration averages |
| `docs/adr/` | Architecture understanding | All architecture decision records |
| `docs/adr/ADR-004-goap-astar-planner.md` | Understanding the planner | GOAP A* design rationale |

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
| plan_state.json missing | Run session init (Step 0) from the planning loop |
| A* planner stuck | Check action preconditions in plan_state.json — may need to force a collect |
| run_stats.json empty | Normal on first run — planner uses conservative defaults from action_catalog |
