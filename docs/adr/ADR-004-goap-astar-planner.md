# ADR-004 — GOAP A* Planner in the Skill Layer

**Status**: Accepted
**Date**: 2026-07-27
**Related**: ADR-005 (ADR System Introduction), design session 2026-07-27

## Context

BuilderDNA currently uses a fixed pipeline orchestrated by Claude Code through the `builderdna` skill. The skill reads `state/hypotheses.json`, selects commands based on a hardcoded command map (collect → trend → pain → opportunity → report), and executes them in a predetermined order. This works but has two limitations:

1. **No dynamic path selection**: even when trend data shows low opportunity (gap_score < 1.0), the pipeline still runs pain and opportunity — wasting time and API calls.
2. **No cost-awareness**: the skill doesn't consider that `collect` costs ~200 GitHub API calls while `trend` costs zero — it treats all steps as equal.

Ruflo's GOAP (Goal-Oriented Action Planning) demonstrated that A* search over action spaces can make agent orchestration smarter: pick the cheapest path to the goal, replan when new data changes the situation, and learn from execution history.

## Decision

Implement a **GOAP A* planner in the `builderdna` skill layer** (not in Python). Claude Code performs semantic heuristic search — evaluating `f(n) = g(n) + h(n)` for each candidate action and selecting the optimal next step. The planner uses **dynamic replanning**: execute one step, observe the result, update state, and re-search.

### State Model (Hybrid)

State is a snapshot of the analysis world, combining data readiness, hypothesis progress, and user goals:

```json
{
  "goal": "opportunity_discovery",
  "target_domain": "agent",
  "data_ready": ["signals.json"],
  "data_missing": ["trends.json", "pain_clusters.json", "opportunities.json"],
  "hypotheses_validated": [],
  "hypotheses_exploring": [],
  "user_dna_loaded": true,
  "actions_executed": ["collect"],
  "cost_so_far_s": 45
}
```

### Goals (3 core)

| Goal | Success Condition |
|------|-------------------|
| `trend_radar` | trends.json ready + report rendered |
| `opportunity_discovery` | opportunities.json ready + report rendered + min hypothesis confidence ≥ 0.7 |
| `hypothesis_validation` | target hypothesis status ∈ {validated, pruned} |

### Actions (7 base, coarse-grained)

Each action is a CLI command with preconditions and effects:

| Action | Preconditions | Effects | Avg Cost (s) |
|--------|--------------|---------|---------------|
| `collect(domain, window)` | none | signals.json ready | 45 |
| `trend(domain)` | signals.json ready | trends.json ready | 8 |
| `pain(domain)` | signals.json ready + Ollama available | pain_clusters.json ready | 92 |
| `opportunity()` | trends.json + pain_clusters.json ready | opportunities.json ready | 3 |
| `report(data, format)` | any output file ready | readable report | 1 |
| `config(show)` | none | config snapshot | 1 |
| `observability(domain)` | any analysis complete | mismatch/snapshot/hypothesis diagnostics | 12 |

Costs come from `state/run_stats.json` (historical averages from `RunTelemetry`) with conservative defaults for cold starts.

### Cost Function

- `g(n)` = sum of executed actions' historical average duration from `state/run_stats.json`
- `h(n)` = minimum remaining actions to goal × their average durations
- Semantic adjustment: if the last action's output reveals low opportunity value, manually inflate `h(n)` for downstream actions to encourage early termination

### Dynamic Replanning Loop

```
1. Load state from state/plan_state.json
2. Identify all executable actions (preconditions satisfied)
3. For each: compute f(n) = g(n) + h(n)
4. Select action with lowest f(n)
5. Execute the action (run the CLI command)
6. Read command output, update state
7. Check goal conditions → reached: stop / not reached: goto 2
```

### Storage

- **Planning state**: `state/plan_state.json` — session-level, tracks current state, path taken, cost
- **Hypothesis state**: `state/hypotheses.json` — cross-session, expanded with `goal` field
- **Cost history**: `state/run_stats.json` — historical command durations from telemetry

## Alternatives Considered

### A. Python-layer A* (new `plan` command)
Rejected: BuilderDNA's architecture is "Claude Code does reasoning, Python does deterministic compute." A* search is reasoning — it needs to evaluate semantic output ("gap_score is low, skip the rest") which Python can't do without an LLM.

### B. Hardcoded decision tree
Rejected: a decision tree is just a more complex fixed pipeline. It can't adapt to unexpected output or learn from history.

### C. Pure memory (no plan state file)
Rejected: session interruptions would lose planning progress. A state file enables recovery and audit.

## Consequences

### Positive
- Analysis sessions can skip unnecessary steps when data shows low value
- Cost-aware: the planner knows that `collect` is expensive and `trend` is cheap
- Hypothesis-driven: exploration state directly influences what gets executed
- Observable: `plan_state.json` provides a full audit trail of planning decisions

### Negative
- Added complexity to `builderdna` skill (planning loop vs. simple command map)
- Two new state files to manage (`plan_state.json`, `run_stats.json`)
- Semantic heuristic depends on Claude Code's judgment — quality varies with model capability
- Cold start: no historical cost data until telemetry accumulates

### Follow-up
- Monitor plan quality: log when the planner chose a suboptimal path
- Fine-grained actions: split `collect` into `collect_fast` (90d) and `collect_deep` (365d) once we have enough cost data
- User override: allow the user to force a specific path even when the planner disagrees

## Honest Limits

- A* search is semantic, not algorithmic — Claude Code evaluates heuristics in natural language, not a proven admissible heuristic
- Quality depends on the model: weaker models may make poor planning decisions
- The 3-goal taxonomy may not cover all user intents — new goals will need to be added
- Cost estimates are averages: individual runs may vary significantly (e.g., GitHub rate limiting)

## Verification

1. Check that `state/plan_state.json` is created on session start with valid schema
2. Run a full analysis and verify the planner skips `pain` when trend gap_score is low
3. Check that `state/run_stats.json` accumulates duration data after each command
4. Verify dynamic replanning: after `trend` reveals low opportunity, the planner should terminate early rather than running `pain` + `opportunity`
