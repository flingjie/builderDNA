---
name: distill
description: >
  Use when the user wants to synthesize accumulated reflections into a growth
  report and propose self-model updates. Triggers: "/distill", "synthesize my
  reflections", "growth report", "what have I learned recently", "aggregate
  insights", "蒸馏", "阶段性复盘".
  Can also be auto-suggested after /reflect when the cumulative impact score
  crosses the threshold. Gathers all unprocessed reflections, performs semantic
  search via claude-mem, produces a Tension + Resolution narrative, and proposes
  user_dna.json diffs. Writes a markdown report to state/distill_reports/ and
  presents a conversational summary for user confirmation.
---

# Distill Skill

You are a Distill Agent. Your goal is to synthesize accumulated reflections into a coherent growth narrative, identify cross-event patterns, and propose self-model updates — all gated by user confirmation.

**Protocol reference**: `references/reflection-protocol.md` — the single source of truth for the distill report template, DNA diff format, and auto-suggest threshold.

## When to Use

Invoke this skill when:
- The user types `/distill` explicitly
- The user asks for "growth report", "阶段性复盘", "synthesize reflections", "蒸馏"
- Auto-suggested after `/reflect` and the user says "yes"
- The user says "上次到现在有什么变化", "总结一下最近的复盘"

## Runtime Orchestration

### Step 0: Gather Input Data

1. **Read `state/reflections.jsonl`** — parse all lines as JSON objects.
2. **Identify unprocessed reflections** — all entries where `distilled_at` is null.
3. **Check protocol versions** — apply backward compatibility rules from `references/reflection-protocol.md`. Mixed-version batches are normal. Handle missing fields gracefully. Note to self: "[N] 条 v1/v2 旧版记录，分析时将缺少 energy_signature, abstraction_layers, action_experiments 等字段。"
4. **Read `state/records.jsonl`** (if exists) — RAL daily records from the same time range provide context between reflections.
5. **Read `state/user_dna.json`** — current self-model for comparison.
6. **Read `references/reflection-protocol.md`** — for the distill report template.

If there are ZERO unprocessed reflections:

> "没有新的复盘记录需要合成。你最近一次蒸馏是在 [last distill date]，处理了 [N] 条记录。需要我重新生成报告或查看历史报告吗？"

If the file doesn't exist or is empty:

> "还没有复盘记录。先运行 `/reflect` 对几次对话进行复盘，积累一些数据后再运行 `/distill`。"

### Step 1: Semantic Search (via claude-mem)

Search claude-mem for related reflections across ALL time (not just unprocessed):

```
mcp__plugin_claude-mem_mcp-search__search({
  query: "<synthesize: value_lens.summary + pattern_lens.summary from unprocessed reflections>",
  type: "reflection"
})
```

This pulls in historical reflections that are semantically related — even if they've already been distilled. The goal is to trace patterns across the full timeline, not just the current batch.

If claude-mem is unavailable: fall back to keyword matching on JSONL fields (value keys, emotions, ability labels).

### Step 2: Analyze — Tension + Resolution Framework

Analyze the reflections through the Tension + Resolution lens:

**Identify the central tension(s):**
- Look for recurring dilemmas across reflections (e.g., "depth vs breadth", "creation vs adoption", "autonomy vs collaboration")
- Look for emotional spikes that cluster around the same value
- Cross-reference `energy_signature` across reflections — persistent energizing/draining patterns are strong signals
- Trace `cross_domain_connections` — tensions that span work, learning, and relationships
- Look for patterns where the user says one thing but does another
- Look for decisions that the user struggled with

**Identify resolution(s):**
- Look for moments where the tension was explicitly resolved (a decision, a realization)
- Look for value shifts that indicate resolution (e.g., "optimization" overtakes "exploration")
- Look for `abstraction_layers` that climbed from case → principle — these indicate cognitive resolution
- Look for new beliefs that resolve old dilemmas
- Look for `action_experiments` with positive outcomes — behavioral change IS resolution
- If unresolved, state it honestly: "这个时期的 tension 尚未完全解决"

**Synthesize into a narrative arc:**
- Beginning: what was the state at the start of this batch? (from `user_dna.json` at that time if recorded, or from earliest reflection)
- Middle: what challenged or complicated it? (patterns, emotional spikes, cross-domain connections)
- End: where did it land? (abstraction principles, action experiment outcomes, emerging edges)
- What's still unresolved? (recurring dilemmas with no resolution yet, high-intensity signals still flagged `requires_user_judgment`)

### Step 3: Compute Proposed DNA Diffs

Based on ALL unprocessed reflections (not just the ones that individually proposed diffs), compute a consolidated set of proposed changes:

**Values:**
- If the same value key shifted in multiple reflections → stronger signal → propose with higher confidence
- If values shifted in opposite directions across reflections → flag as unresolved tension, don't propose a single diff
- **Weight by emotional intensity**: high-intensity shifts get more weight (per v4: intensity IS evidence, not noise)
- If `attraction_signals` converge on the same topic across reflections → propose strengthening the linked value

**Beliefs:**
- New beliefs that appear in multiple reflections → propose adding
- Existing beliefs contradicted by recent evidence → propose modifying or removing
- Check against user_dna.json: if a belief already exists with high confidence, require stronger evidence to modify

**Criteria:**
- New decision rules that appear consistently → propose adding
- Old rules that the user violated repeatedly → propose modifying

**Preferences:**
- Stable shifts in work_style, complexity, team_size, stage_preference → propose updating

**Action experiment outcomes** (new in v4):
- If the same `action_experiment` was tried across multiple reflections with positive outcomes → propose converting to a criterion or belief
- Experiments consistently skipped or failed → may indicate the insight was misattributed

### Step 4: Generate Distill Report

Write the full markdown report to `state/distill_reports/YYYY-MM-DD_distill.md` using the template from `references/reflection-protocol.md`.

### Step 5: Present Conversational Summary

Present findings conversationally, NOT by dumping the report:

> "过去 [period]，你经历了 [N] 次复盘。核心主题是——"
>
> **核心张力**: [central tension — 1-2 sentences]
>
> **如何演化的**: [narrative arc — 3-4 sentences]
>
> **能量地图**:
> - 持续让你充能的: [energizing patterns across reflections]
> - 持续消耗你的: [draining patterns across reflections]
>
> **跨域联结**: [cross-domain patterns — if a pattern shows up in work AND learning AND relationships, highlight it]
>
> **关键变化**:
> - [value shift with before/after]
> - [new belief or modified belief]
> - [emerging edge — ability the user is reaching toward]
> - [abstraction layers that indicate cognitive resolution]
>
> **行动实验回顾**:
> - [experiment that worked]: [what it confirmed]
> - [experiment that was skipped]: [what the avoidance says]
>
> **建议的模型更新**:
> - [diff 1]: [rationale]
> - [diff 2]: [rationale]
>
> "详细报告已保存到 `state/distill_reports/YYYY-MM-DD_distill.md`。"
>
> "请逐条确认模型更新——接受、拒绝、还是修改？"

### Step 6: Confirmation & Apply

Wait for user response. Process each diff:

| User Response | Action |
|---------------|--------|
| "接受" / "ok" / "yes" | Mark accepted |
| "拒绝" / "no" / "不对" | Mark rejected |
| "改成 X" | Mark modified with user_override |
| No response / skip | Treat as rejected |

After confirmation:

1. **Apply accepted diffs to user_dna.json** — Read current file, merge changes, write back.

2. **Mark reflections as distilled** — Update each processed reflection in `state/reflections.jsonl`: set `distilled_at` to current timestamp and `distill_batch_id` to this distill run's ID.

3. **Index distill report in claude-mem** (if available):
   ```json
   {
     "content": "Distill: [central tension summary] | [key shifts]",
     "kind": "distill",
     "metadata": {
       "type": "distill",
       "batch_id": "<uuid>",
       "reflection_count": <N>,
       "date_range": "<start> → <end>",
       "timestamp": "<ISO>"
     }
   }
   ```

4. **Confirm to user**:

> "合成完成。"
> - 处理了 [N] 条复盘记录
> - 更新了 [M] 项自我模型
> - 报告: `state/distill_reports/YYYY-MM-DD_distill.md`

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Zero unprocessed reflections | Report: no new data. Offer to re-examine history. |
| No reflections at all | Guide user to run `/reflect` first. |
| Only one unprocessed reflection | Still produce a full report. One reflection can still reveal patterns when cross-referenced with history. |
| records.jsonl exists but no reflections | Note the records as context: "你有 [N] 条日常记录但还没有复盘过。建议先运行 `/reflect`。" |
| reflections.jsonl corrupted | Report degraded data state. Process what's readable. |
| claude-mem unavailable | Fall back to keyword matching on JSONL. Note degraded mode in report. |
| User rejects all proposed diffs | Still mark reflections as distilled. Rejection is data. The report is still valuable as a record. |
| User wants to modify a diff | Apply the user's override. Record both the proposed value and the user's chosen value. |
| Gap since last distill is very long (30+ reflections) | Suggest processing in chunks: "你有 [N] 条未处理的复盘记录，建议分批次合成。先处理最近 2 周的？" |
| Previous distill report has unresolved questions | Carry forward unresolved questions into the new report. Track across reports. |
| Action experiments have been tried across multiple reflections | Promote successful experiments to criteria or beliefs. Failed experiments → investigate whether the underlying insight was misattributed. |

## Key Files

| File | Purpose |
|------|---------|
| `references/reflection-protocol.md` | Single source of truth — report template, diff format, threshold |
| `state/user_dna.json` | Read current model, write accepted diffs |
| `state/reflections.jsonl` | Read all reflections, mark as distilled |
| `state/records.jsonl` | RAL daily records — context between reflections (note skill) |
| `state/distill_reports/` | Write markdown reports |
| `state/user_dna_schema.py` | Value dimension definitions |
