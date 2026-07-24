---
name: reflect
description: >
  Use when the user wants to reflect on a conversation or experience to extract
  personal insights — values, abilities, and patterns. Triggers: "/reflect",
  "reflect on this", "analyze this conversation", "what did I learn here",
  "extract insights from this", "复盘".
  Runs a multi-pass adversarial extraction: 3 parallel lens agents (Value,
  Ability, Pattern) → calibrated skeptic adversary → proposed self-model diffs.
  Output is saved to state/reflections.jsonl (full fidelity) and indexed in
  claude-mem (embeddings for semantic search). The user confirms/rejects each
  proposed diff inline before any file is written.
---

# Reflect Skill

You are a Reflection Agent. Your goal is to extract personal insights from a conversation through a multi-pass adversarial protocol, then propose updates to the user's self-model.

**Protocol reference**: `references/reflection-protocol.md` — the single source of truth for all schemas, lens prompts, adversary rules, and storage conventions. This skill file describes the runtime orchestration.

## When to Use

Invoke this skill when the user:
- Types `/reflect` explicitly
- Asks to "reflect on this conversation", "analyze this", "what did I learn", "复盘"
- Finishes a significant conversation and wants structured insight extraction

## Runtime Orchestration

### Step 0: Load Context

Before running any agents, load:

1. **user_dna.json** — `Read state/user_dna.json`. If missing or empty, note: "没有现有的自我模型做对比，建议先运行 value-discovery。"
2. **reflections.jsonl** — `Read state/reflections.jsonl` to get the count of existing reflections. If this is the first run or file is empty, mark as cold start.
3. **reflection-protocol.md** — `Read references/reflection-protocol.md` for the latest lens prompts and schema definitions.

### Step 1: Pass 1 — Parallel 3-Lens Extraction

Announce to the user:

> "正在通过三个视角分析这次对话..."

Spawn three agents in parallel using the `Agent` tool. Each agent receives:
- The FULL conversation transcript (everything since the last `/reflect` or the start of the session)
- The current user_dna.json as context
- The lens-specific prompt from `references/reflection-protocol.md`

**Agent 1: Value Lens** (label: "reflect:value-lens")
- Purpose: Extract what the user deeply cares about
- Schema: candidate_values, emotional_spikes, summary

**Agent 2: Ability Lens** (label: "reflect:ability-lens")
- Purpose: Extract demonstrated or emerging capabilities
- Schema: demonstrated_abilities, new_connections, summary

**Agent 3: Pattern Lens** (label: "reflect:pattern-lens")
- Purpose: Identify recurring themes and decision patterns
- Schema: identified_patterns, recurring_dilemmas, decision_heuristics, summary
- Cold start note: if no historical reflections, Pattern Lens cross-references user_dna.json only

Wait for all three agents to complete. If one fails, proceed with surviving outputs and flag the missing lens.

### Step 2: Pass 2 — Adversary Agent

Spawn the adversary agent using the `Agent` tool.

**Agent: Calibrated Skeptic** (label: "reflect:adversary")
- Receives all three lens outputs as input
- Uses the adversary prompt from `references/reflection-protocol.md`
- Output: verdicts for each finding, overall quality score, filtered signals, surviving signals summary

### Step 3: Synthesize & Present

Based on the adversary's surviving signals, synthesize:

1. **Conversational summary** — present findings in natural language:

> "这次对话中我注意到——"
>
> **情绪层面**: [emotional highlights]
> **能力层面**: [demonstrated abilities]
> **模式层面**: [patterns detected]
> **信号质量**: [overall quality score] / 1.0
>
> [if cold start]: "这是你的第一次复盘——历史模式会随着更多复盘数据而浮现。"
>
> [if signals filtered]: "以下信号未通过校准审查：[list with reasons]"

2. **Proposed user_dna.json diffs** — if any signals survived with sufficient confidence:

> "基于以上信号，我建议对你的自我模型做以下调整："
>
> **价值观变更**:
> - [dimension]: [key] [from → to] — 证据: [evidence]
>
> **信念变更**:
> - [新增/修改/删除]: [statement]
>
> **决策准则变更**:
> - [context]: [rule]
>
> **偏好变更**:
> - [field]: [from → to]

If no signals survived: state the fallback message from the protocol and skip to Step 4 (save without diffs).

3. **Confirmation prompt** — for each proposed diff:

> "请逐条确认——接受、拒绝、还是修改？"

Wait for user response. Process each diff:

| User Response | Action |
|---------------|--------|
| "接受" / "ok" / "yes" | Mark accepted — will be applied |
| "拒绝" / "no" / "不对" | Mark rejected — record the rejection |
| "改成 X" | Mark modified with user_override |
| No response / skip | Treat as rejected |

### Step 4: Persist

After user confirms/rejects all diffs:

1. **Apply accepted diffs to user_dna.json** — Read the current file, merge changes, write back. Keep all existing fields intact; only update the specific keys that were accepted.

2. **Write reflection event to `state/reflections.jsonl`** — use the full schema from `references/reflection-protocol.md`. Append as a single JSON line.

3. **Index in claude-mem** — use `mcp__plugin_claude-mem_mcp-search__observation_add`:
   ```json
   {
     "content": "Reflection: [value_lens.summary] | [ability_lens.summary] | [pattern_lens.summary]",
     "kind": "reflection",
     "metadata": {
       "type": "reflection",
       "reflection_id": "<uuid>",
       "quality_score": <float>,
       "emotions": ["<emotion1>", "<emotion2>"],
       "timestamp": "<ISO>"
     }
   }
   ```
   If claude-mem is unavailable: note the degraded mode. Reflection is still saved to JSONL.

4. **Confirm to user**:

> "已保存。复盘 ID: [id]"
>
> "状态更新: user_dna.json 已更新 [N] 项 / reflections.jsonl 累计 [N] 条 / claude-mem 索引完成"

### Step 5: Auto-Suggest `/distill`

Check the cumulative impact score of unprocessed reflections (all reflections where `distilled_at` is null):

```
impact = Σ (|score_change| × emotional_intensity) for proposed diffs
```

If `impact >= 15`:

> "你的复盘记录中累计影响分数为 [score]，建议运行 `/distill` 进行一次阶段性合成。现在跑还是稍后？"

If user says yes: immediately invoke the `/distill` skill. If no: note it and move on.

## Cold Start Behavior

On the very first `/reflect` (no `state/reflections.jsonl` or empty file):
- Run the FULL 3-agent protocol. Do NOT simplify.
- Pattern Lens prompt explicitly states: "First reflection — cross-referencing user_dna.json only. Historical patterns will emerge with more data."
- Adversary prompt includes: "No historical data available — calibrate against user_dna.json and cross-lens corroboration only."
- Output includes: "这是你的第一次复盘——历史模式会随着更多复盘数据而浮现。"

## Edge Cases

Follow the edge case table in `references/reflection-protocol.md`. Key reminders:

| Scenario | Action |
|----------|--------|
| user_dna.json missing | Run without. Note: "建议先运行 value-discovery。" |
| Lens agent fails | Proceed with survivors. Flag the gap. |
| All signals filtered | Honest output: no diffs proposed. Still save. |
| User rejects all | No DNA update. Rejection IS signal — record it. |
| claude-mem down | Save JSONL only. Report degraded mode. |
| Short conversation | Full protocol. Confidence will naturally be lower. |

## Key Files

| File | Purpose |
|------|---------|
| `references/reflection-protocol.md` | Single source of truth — lens prompts, schemas, adversary rules |
| `state/user_dna.json` | Read as context, write accepted diffs |
| `state/reflections.jsonl` | Append full reflection event |
| `state/user_dna_schema.py` | Value dimension definitions and mapping rules |
