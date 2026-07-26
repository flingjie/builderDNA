---
name: observability
description: >
  Use this skill when the user wants to run self-iteration diagnostics on
  BuilderDNA's past analyses — validation of predictions against new data,
  behavior mismatch detection, hypothesis pruning. Also use when the user says
  "check my predictions", "validate assumptions", "anything changed?", "verify
  past analysis", "我之前猜的对不对", "任何东西变了吗", "验证一下之前的预测",
  or references observability directly.
  This skill wraps the `builderdna observability` CLI command (3 checks:
  mismatch detection, snapshot comparison, hypothesis pruning) and interprets
  the JSON results. Auto-suggest after every 3-5 analysis pipeline runs.
  The observability command is the 7th sandbox command in BuilderDNA's toolkit
  (built from observability/behavior.py, snapshot.py, hypothesis.py).
---

# Observability Skill

You run BuilderDNA's self-iteration diagnostics — validating past predictions, detecting value drift, and pruning stale hypotheses.

## When to Use

- User explicitly asks to check predictions, validate assumptions, or verify past analysis
- After every 3-5 complete analysis runs (collect → trend → pain → opportunity)
- When hypotheses haven't been reviewed in 30+ days
- User mentions drift, contradiction, or "anything changed?"

## Command

```bash
# Run all three checks
PYTHONPATH=. uv run builderdna observability --all --domain <domain>

# Run individual checks
PYTHONPATH=. uv run builderdna observability --mismatches   # behavior drift
PYTHONPATH=. uv run builderdna observability --snapshots    # prediction validation
PYTHONPATH=. uv run builderdna observability --prune        # hypothesis staleness
```

The `--domain` flag defaults to `agent`. Use whatever domain the user is analyzing.

Results are written to `output/observability_check_<domain>.json`. Read this file to interpret results.

## The Three Checks

### 1. Mismatch Detection (`--mismatches`)

Compares observed behavior patterns against values stated in `state/user_dna.json`. Flags when actual command usage diverges from stated preferences.

**Output**: list of mismatches, each with:
- `dimension`: which value dimension shows a gap (environment, activity, output, reward)
- `stated`: what user_dna.json says
- `observed`: what behavior data shows
- `strength`: how significant the gap is

**What to do with a mismatch**:
- If `strength` is high: ask the user — "我注意到你之前的偏好是 [stated]，但最近的行为更像是 [observed]。要不要更新你的 User DNA，还是这只是暂时的情况？"
- If low: note it and move on.

### 2. Snapshot Comparison (`--snapshots`)

Compares past prediction snapshots (trend predictions, opportunity forecasts) against today's actual data to validate how accurate past analyses were.

**Output**: list of comparisons, each with:
- `snapshot_id` and its date
- Top predicted items vs. what actually happened
- Hit/miss stats

**What to surface**:
- High-accuracy predictions: "你之前的 [domain] 预测准确率很高——[X]/[Y] 条命中。"
- Major misses: "[prediction] 当时预测会大涨，但实际没发生。可能的原因：[reason based on new data]"
- Domain shifts: "前一次分析整体判断偏保守/激进——当前市场变化比预期快/慢。"

### 3. Hypothesis Pruning (`--prune`)

Checks `state/hypotheses.json` for nodes that should be reviewed or retired:
- Stale hypotheses (no updates in >30 days)
- Contradicted hypotheses (recent evidence conflicts)
- Low-confidence hypotheses that haven't been investigated

**Output**: pruning proposals for flagged nodes, each with `action: "prune"` and a reason.

**What to do**:
- Present flagged hypotheses to the user with reasons
- Let the user decide: keep, prune, or update
- Apply accepted prunes via `HypothesisManager` in the Python code

## Interpreting Results

After running `--all`, read `output/observability_check_<domain>.json` and present findings conversationally:

```
观测报告: [domain]

**行为一致性**: [summary of mismatches — all clear, or flag specific drifts]
**预测验证**: [summary of snapshot accuracy — hit rate, key misses]
**假设清理**: [N] 条假设需要回顾, [M] 条建议修剪

[Ask user about each actionable item]
```

## Configuration

Observability thresholds are in `config.yaml`:

```yaml
observability:
  mismatch_threshold: 7       # events before auto-suggesting a mismatch check
  expiry_days: 30             # days after last update before pruning eligibility
  min_comparison_age_days: 90 # days before a prediction snapshot is eligible for validation
  predictions_dir: predictions # directory for prediction snapshots
```

## Auto-Suggest Logic

After running a full analysis pipeline (collect → trend → pain → opportunity), track a run counter. Every 3-5 runs, offer:

> "你已经跑了 [N] 次分析，要不要运行一次 observability 检查？——验证之前的预测、检查偏好是否有漂移。"

Don't auto-run without asking — the user may not want to spend the API calls on metadata.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Empty observability output | No prediction snapshots exist yet. Run at least one full pipeline first. |
| `ModuleNotFoundError` | Prefix with `PYTHONPATH=.` |
| No hypotheses file | `state/hypotheses.json` doesn't exist — the user hasn't explored hypotheses yet |
| Mismatch count = 0 | Behavior aligns with stated values. This is good news. |
| Many pruning candidates | Suggest a hypothesis review session — the user may want to archive old explorations |
