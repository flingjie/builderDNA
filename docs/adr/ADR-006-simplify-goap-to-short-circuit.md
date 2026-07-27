# ADR-006 — Replace GOAP A* with Goal-Driven Short-Circuit Pipeline

**Status**: Accepted
**Date**: 2026-07-27
**Supersedes**: ADR-004 (GOAP A* Planner in Skill Layer)
**Related**: ADR-005 (ADR System Introduction)

## Context

ADR-004 introduced a GOAP A* planner in the builderdna skill layer. After implementation and review, analysis of the actual action dependency graph revealed that the A* search framework was providing no measurable benefit over a simpler approach, while adding significant maintenance burden:

- **Branch factor is effectively 1**: The 7-command dependency graph is almost fully linear. At each step, usually only 1 action can meaningfully advance toward the goal.
- **The only real decision point** is after `trend` completes: should we run `pain` (92s, requires Ollama) or skip to `report`? This is a single if-condition, not a search problem.
- **The heuristic was non-admissible**: h(n) used "count remaining actions × avg cost" with LLM-driven semantic adjustments. An A* with a non-admissible heuristic loses its optimality guarantee — it ceases to be A* in any meaningful sense.
- **Cost data was too noisy**: action durations vary by 10-60× due to GitHub rate limiting, Ollama availability, and window size. Average costs don't provide reliable discrimination between action choices.
- **plan_state.json required synchronization**: session initialization, action catalog, cost tracking, and goal conditions had to stay consistent across the skill file, the state file, and the ADR. Every command addition meant touching 4+ places.

The framework was providing structural overhead without structural benefit — a classic case of mismatch between problem complexity and solution complexity.

## Decision

Replace the GOAP A* planning loop with a **Goal-Driven Short-Circuit Pipeline**:

1. **Goal → commands mapping**: Each of 3 goals maps to a fixed ordered command sequence. Trends always precede pain (8s vs 92s — cheap data informs the expensive decision). No search needed — the dependency chain IS the plan.

2. **Short-circuit rules**: Exactly 3 checks replace the A* heuristic and semantic adjustment:
   - **Trend signal**: if `trend` shows all `gap_score < 1.0` and no rising velocity → ask user whether to skip `pain` + `opportunity`
   - **Cost budget**: if cumulative time exceeds 5 minutes → ask whether to continue
   - **Hypothesis resolved**: if target hypothesis reaches `validated` or `pruned` → stop

3. **No session state file**: Session state (which files exist, what's been run) is derived from the filesystem and in-session memory. No `plan_state.json` to manage.

4. **No cost tracking**: `run_stats.json` and `persist_run_stats()` are removed. The fixed ordering of `trend` before `pain` (cheap-before-expensive) provides the same cost-aware behavior without statistical overhead.

### Before (ADR-004)

```
~140 lines of planning loop:
  Session Init (6 steps) → Goal Determination → WHILE loop:
    search executable actions → compute f(n)=g(n)+h(n) for each →
    semantic adjustment → select min f(n) → execute →
    update plan_state.json + run_stats.json + hypotheses.json →
    check stop condition → loop
  + Command Map Fallback (15 lines, duplicate)
  + plan_state.json (88 lines)
  + run_stats tracking (telemetry.py)
```

### After (ADR-006)

```
~30 lines of pipeline:
  Goal Determination → required commands (fixed) →
  trend signal check → optional commands or skip →
  report → present findings
```

### What stays the same

- Goal taxonomy (trend_radar, opportunity_discovery, hypothesis_validation)
- Hypothesis tracking in `state/hypotheses.json`
- Observability integration
- User DNA personalization
- All 7 CLI commands
- The fundamental workflow: collect → analyze → report

## Alternatives Considered

### Keep GOAP A* but fix the heuristic
Rejected: Even with a provably admissible heuristic (which would require formalizing LLM judgment into a mathematical bound), the branch factor of 1-2 means the search adds no value. The algorithm isn't the problem — the search space is.

### Remove ALL planning (just run collect→trend→pain→opportunity→report every time)
Rejected: Some users only want trends, not opportunities. Some domains have low signal where running pain (92s + Ollama requirement) is wasteful. Goal-driven execution is worth keeping — the short-circuit is the right mechanism.

### Keep plan_state.json as a simpler audit trail
Rejected: The audit trail value is low — it's just a log of which commands ran in what order. If we need this later, a simple JSONL log is more appropriate. Not worth the synchronization overhead for now.

## Consequences

### Positive
- Skill file ~70 lines shorter, no Fallback duplication
- `plan_state.json` and `run_stats.json` removed — 2 fewer state files
- `persist_run_stats()` removed from telemetry.py
- Every command addition now touches 1 place (the command template table) instead of 4
- User behavior is predictable: same goal → same command sequence, every session
- Short-circuit rules are explicit in the skill, not hidden in heuristic adjustments
- ADR-004 preserved as historical record (Superseded), not lost

### Negative
- No per-domain cost optimization (e.g., if pain is faster for domain X than Y, the pipeline won't adapt automatically)
- No learning from execution history to reorder commands
- One less piece of the system that "learns from itself" — but the learning was noisy enough to be net-negative

### Follow-up
- If future commands create a genuine branch factor (3+ executable actions at a step), revisit planning
- If action costs become stable and discriminative (e.g., pain drops from 92s to 2s after infrastructure improvements), reconsider cost awareness

## Honest Limits

- The short-circuit pipeline assumes the dependency graph is roughly linear. If we add commands that break this (e.g., multiple alternative data sources with different costs/quality), it won't adapt.
- The trend signal check (gap_score < 1.0) is a heuristic threshold — some domains may have legitimately low gap_scores that still represent real opportunities. The user can override by saying "run pain anyway."
- This is a simplification, not an improvement in decision quality. We're removing structure that wasn't earning its keep — the decisions stay the same.

## Verification

```bash
# 1. Verify builderdna skill no longer references plan_state or GOAP A*
grep -c "plan_state\|GOAP A\*\|run_stats\|action_catalog" .claude/skills/builderdna/SKILL.md
# Expected: 0

# 2. Verify telemetry.py no longer has persist_run_stats
grep -c "persist_run_stats\|run_stats" observability/telemetry.py
# Expected: 0

# 3. Verify ADR-004 is marked Superseded
grep "Superseded" docs/adr/ADR-004-goap-astar-planner.md

# 4. Verify ADR index has new entries
grep "ADR-006" docs/adr/README.md
```
