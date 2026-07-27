---
name: optimize
description: Read diagnostics from SandboxResult outputs, generate improvement proposals, apply user-confirmed changes, and verify.
---

# optimize Skill

Diagnose → Propose → Apply → Verify loop. This skill reads the most recent
SandboxResult output, extracts actionable diagnostics, generates concrete
proposals, gets user confirmation, applies changes, re-runs the affected
command, and verifies improvement.

## Triggers

"优化分析", "improve the analysis", "fix low confidence", "/optimize",
"提升", "优化"

## Architecture

```
User: "/optimize"
       │
       ▼
1. DISCOVER — find the most recent SandboxResult JSON in output/
       │
       ▼
2. DIAGNOSE — extract + present diagnostics (data_quality, confidence, parameter_sensitivity)
       │
       ▼
3. BOOTSTRAP — check state/bootstrap.json for prior successful patterns
       │
       ▼
4. PROPOSE — generate one proposal per actionable diagnostic, write to output/proposals/
       │
       ▼
5. CONFIRM — present proposals to user one at a time, wait for accept/reject/skip
       │
       ▼
6. APPLY — for accepted proposals, edit config.yaml or determine re-run flags
       │
       ▼
7. VERIFY — re-run affected command(s), compare new vs old diagnostics
       │
       ▼
8. RECORD — if improvement confirmed, record to state/bootstrap.json
```

## Step 1: Discover

Look in `output/` for the most recently modified `.json` file that is a
SandboxResult (has a `command` field). Read it and identify:
- `command` (collect, trend, pain, opportunity)
- `domain`
- `diagnostics` (data_quality, confidence, parameter_sensitivity)
- `stats`

If no SandboxResult found, ask user which command output to optimize.

## Step 2: Diagnose

Present diagnostics in a human-readable table:

```
## Diagnostics: {command} ({domain})

### Data Quality
- Coverage gaps: N (list key ones)
- Sample size warning: yes/no
- Noise sources: N
- API issues: N

### Confidence
- Low confidence items: N
  - item_name (confidence=0.X): reason
```

Sort issues by severity. For each, note whether it's fixable by parameter
change vs. requires more data.

### Parameter Sensitivity

Run `generate_parameter_sensitivity(result)` from observability/diagnostics.py
to get parameter tuning hints. Present alongside raw diagnostics as suggested fixes.

## Step 3: Bootstrap

Read `state/bootstrap.json`. For the current `domain` + `command`, check:
- Have there been prior high-quality runs?
- What topics/windows/parameters were used in those successful runs?
- Are there specific topic refinements that previously improved confidence?

Present bootstrap context: "This domain has N prior high-quality runs.
Previously successful: [summary]."

## Step 4: Propose

For each actionable diagnostic, generate ONE proposal. A proposal has:

```json
{
  "id": "prop_YYYYMMDD_HHMMSS_NNN",
  "created_at": "ISO8601",
  "source_diagnostics": {
    "command": "trend",
    "diagnostic_type": "confidence.low_confidence_items",
    "issue": "topic 'rust-embedded' has only 2 supporting repos"
  },
  "proposed_changes": [
    {
      "target": "config.domains.agent.topics",
      "action": "append",
      "current_value": "...",
      "proposed_value": "...",
      "rationale": "Adding more specific topic variants may match more repos"
    }
  ],
  "expected_impact": {
    "metric": "coverage_gaps",
    "current": 3,
    "expected": 1,
    "basis": "bootstrap: similar refinement resolved gaps"
  },
  "risk": "low",
  "status": "pending"
}
```

Risk levels:
- **low**: Changing a topic string in config (non-destructive, easy to revert)
- **medium**: Changing window or rate limit (affects all topics, moderate blast radius)
- **high**: Removing topics or changing domain config (may lose signal)

Write proposals to `output/proposals/prop_YYYYMMDD_HHMMSS.json`.

### Proposal generation rules

| Diagnostic | Proposal Type |
|-----------|---------------|
| data_quality.coverage_gaps | Append broader topic synonyms, or broaden window |
| data_quality.sample_size_warning | Broaden topic list, extend window, or add vendor accounts |
| data_quality.api_issues (rate-limited) | Increase rate_limit_margin by 10-20 |
| data_quality.noise_sources (too many repos) | Narrow topic to more specific terms |
| confidence.low_confidence_items (low evidence) | Add more specific subtopics, extend time window |
| confidence.low_confidence_items (velocity noise) | Extend window so velocity has more history |

## Step 5: Confirm

Present proposals one at a time. For each:

```
## Proposal 1/3: Fix coverage gaps for 'rust-embedded'

**Problem**: topic 'rust-embedded' matched only 2 repos

**Fix**: Add 'rust-embedded-framework', 'embedded-rust', 'no-std' to topics

**Expected**: coverage gaps: 3 → 1 (bootstrap: similar fix worked for 'go-agent')

**Risk**: Low — adding topics is non-destructive

**Accept?** (a)ccept / (r)eject / (s)kip
```

Wait for user response after each proposal before presenting the next.

## Step 6: Apply

For accepted proposals:
- **config.yaml edits**: Use Edit to modify config.yaml precisely.
- **CLI flag adjustments**: Store adjusted flag values for re-run.
- **Track changes**: Keep a list of (proposal_id, change, file, old, new).

## Step 7: Verify

1. Run `uv run pytest tests/ -v` first — if tests fail, do NOT re-run.
2. Re-run the affected command with adjusted config/flags.
3. Read the new SandboxResult output.
4. Use `compare_diagnostics(old_result, new_result)` to detect changes.
5. Present before/after comparison.

If improvement: mark proposal `applied`.
If regression: mark `failed` and suggest rollback.
If no change: mark `applied` (still a valid attempt).

## Step 8: Record

For proposals marked `applied`:
1. Update the proposal JSON status.
2. Call `record_bootstrap(result, quality="high")`.
3. Summarize: "N proposals accepted, M applied successfully."

## Rollback

If regression: revert config.yaml change, mark proposal `failed`, suggest alternative.

## Edge Cases

- **No diagnostics issues**: "All diagnostics look clean — no optimization needed."
- **No prior bootstrap data**: "First optimization for this domain — each accepted proposal builds knowledge."
- **Both coverage gaps AND noise**: Prioritize noise (narrow broad topics), then gap filling.
- **Proposal file exists**: Append sequence number suffix.
- **Tests fail after config edit**: Revert immediately, mark `failed`.
