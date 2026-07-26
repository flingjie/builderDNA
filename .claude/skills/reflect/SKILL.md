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
2. **reflections.jsonl** — `Read state/reflections.jsonl`. Parse each line as JSON. Run integrity checks per `references/reflection-protocol.md` (State Integrity section): skip unparseable lines, flag duplicate IDs, verify required fields. Report: "reflections.jsonl: [N] 条, [M] 条损坏已跳过". If file is empty or new, mark as cold start.

   **Check protocol version on load.** If any reflection has `protocol_version` < 6, apply backward compatibility rules from the protocol reference. Missing v3-v6 fields are treated as absent — no error. Note to self: "包含 [K] 条旧版协议记录，部分字段缺失。" This doesn't block anything.
3. **reflection-protocol.md** — `Read references/reflection-protocol.md` for the latest lens prompts and schema definitions.
4. **Unprocessed RAL records** — `Read state/records.jsonl` (if exists). Filter for records where `processed_at` is null. These are daily captures from the `/note` skill. Include them as additional signal sources for all three Lens agents alongside the conversation transcript. Records provide event-level signals (what happened between conversations) that conversation-only analysis misses.

**Tag cross-pollination:** If a record has `value_tags` populated (from note amplify), pass these to the Value Lens as "user self-tagged" signals — they carry higher confidence than purely extracted signals, per the Tag Catalog in `references/reflection-protocol.md`.
5. **Pending action experiments** — Check the most recent reflection event in `reflections.jsonl`. If it contains `action_experiments` with `status: "active"` and `outcome: null`:

Determine age in days since `activated_at`:

| Age | Action |
|-----|--------|
| 0-4 days | Normal ask: "上次复盘你选择了 [N] 个行动实验。试一下了吗？" |
| 5-13 days | Gentle nudge: "你选了 [N] 个行动实验，已经 [年龄] 天了——有试过吗？如果不再相关，可以直接跳过。" |
| 14+ days | Auto-expire: mark `status: "expired"`, note: "已自动归档 [N] 个过期实验。这些可能是当时情绪放大的信号，也可能是真正的线索。如果还想试，说'恢复实验'。" |

> "实验回顾："
>
> | # | 行动规则 | 年龄 | 试了？ | 效果 |
> |---|---------|------|--------|------|
> | 1 | 如果 [trigger], 那么 [action] | 3天 | 是 | 部分有效——[自由回答] |
> | 2 | ... | 3天 | 否 | — |
>
> [if >5 days]: "有些实验已经等了一段时间——没问题，不是每个实验都需要追。直接说'跳过全部'就清掉。"
>
> Record outcomes. Update `outcome` and `status` fields. This feedback loop is how insights become behavioral change.

After agents complete, mark all loaded records with `processed_at: "<ISO>"`.

### Step 0.5: Conversation Preprocessing (long conversations)

Estimate conversation length — count turns or approximate token count.

- **Short** (<40 turns or <5k words): skip preprocessing. Pass the full transcript directly to all Lens agents.
- **Long** (40+ turns or 5k+ words): extract signal-rich excerpts before passing to Lens agents.

For long conversations, spawn a single lightweight preprocessing agent (or do it inline):

**Extraction prompt:**

> "Scan the following conversation of [N] turns and extract the 5-8 most signal-rich exchanges — moments with emotional weight, decisions, trade-offs, unprompted initiations, or flow states. For each excerpt, include a one-line label and the verbatim exchange. Also note any notable shifts in topic or tone between sections."
>
> Output: a condensed signal map — excerpts with labels + brief section notes.

**What Lens agents receive:**
1. The condensed signal map (primary — use this for analysis)
2. The full transcript (reference — available for evidence-checking when a finding needs direct quote verification)

This reduces per-agent context by 50-70% while preserving signal density. If the preprocessing agent fails, fall back to full transcript with a note: "预处理未完成，使用完整对话。"

### Step 1: Pass 1 — Parallel 3-Lens Extraction

Announce to the user:

> "正在通过三个视角分析这次对话..."

Spawn three agents in parallel using the `Agent` tool. Each agent receives:
- The FULL conversation transcript (everything since the last `/reflect` or the start of the session)
- The current user_dna.json as context
- The lens-specific prompt from `references/reflection-protocol.md`

ALL THREE LENS AGENTS now follow a common preprocessing workflow:
1. **Segment (切分)** — break conversation into 2-5 segments by topic/register
2. **Focus (聚焦)** — devote most depth to top 1-2 high-signal segments; don't force findings from thin material
3. **Extract** — extract signals per lens specialty

**Agent 1: Value Lens** (label: "reflect:value-lens")
- Purpose: Extract what the user is pursuing — direction, attraction, energy
- Schema: segments, focus_segments, candidate_values, attraction_signals, emotional_spikes, summary

**Agent 2: Ability Lens** (label: "reflect:ability-lens")
- Purpose: Extract demonstrated and emerging capabilities — what the user is becoming
- Schema: segments, focus_segments, demonstrated_abilities, emerging_edges, new_connections, summary

**Agent 3: Pattern Lens** (label: "reflect:pattern-lens")
- Purpose: Identify recurring patterns, cross-domain connections, energy signature, and abstraction layers (case → pattern → principle)
- Schema: segments, focus_segments, identified_patterns, abstraction_layers, cross_domain_connections, energy_signature, recurring_dilemmas, decision_heuristics, summary
- Cold start note: if no historical reflections, Pattern Lens cross-references user_dna.json only

Wait for all three agents to complete. If one fails, proceed with surviving outputs and flag the missing lens.

### Step 1.5: Validation Gate

Before moving to the adversary, validate each lens output against the schema invariants defined in `references/reflection-protocol.md` (see "Agent Output Validation Gate").

**Quick checks (do inline, don't spawn agents for this):**

1. **Parse JSON** — each agent output must be valid JSON. If malformed, try extracting the JSON substring between first `{` and last `}`.
2. **Check required fields** — `segments` (non-empty), `focus_segments` (non-empty), `summary` (non-empty string). Per-lens field checks per the protocol.
3. **Sanity check** — do `segments` labels correspond to actual conversation topics? Do evidence quotes appear in the transcript?
4. **Classify each lens**: `passed` | `degraded` (partial data) | `failed`

**Degraded mode rules:**

| Survivors | Action |
|-----------|--------|
| 3/3 | Proceed normally |
| 2/3 | Proceed. Tell adversary which lens failed; relax cross-corroboration thresholds |
| 1/3 | Proceed with heavy caveat. Report to user which lenses failed. |
| 0/3 | Abort. Report: "本轮复盘无法完成——所有分析视角均未返回有效结果。" Save minimal event with `status: "aborted"`. |

If validation falls back to partial JSON or degraded mode, note it in the reflection event's `adversary_verdict`.

### Step 2: Pass 2 — Adversary Agent

Spawn the adversary agent using the `Agent` tool.

**Agent: Calibrated Skeptic** (label: "reflect:adversary")
- Receives all three lens outputs as input
- Uses the adversary prompt from `references/reflection-protocol.md`
- Three roles:
  1. **Truth calibration** — verify claims are evidence-supported (don't penalize emotional intensity)
  2. **Meaning expansion** — offer alternative framings and perspective switches for each finding
  3. **Action concretization** — generate testable action experiments from surviving signals
- Output: verdicts (each with optional alternative_framing, perspective_switch), action_experiments, deep_dive_candidates, filtered_signals, overall_quality_score, surviving_signals_summary

### Step 3: Synthesize & Present

Based on the adversary's surviving signals, synthesize:

1. **Conversational summary** — present findings in natural language:

> "这次对话中我注意到——"
>
> **信号切分**: [segments overview — which parts of the conversation had the strongest signals]
> **情绪层面**: [emotional highlights + attraction signals]
> **能力层面**: [demonstrated abilities + emerging edges]
> **模式层面**: [patterns detected + abstraction layers (case → pattern → principle)]
> **能量地图**: [energizing vs. draining activities]
> **跨域联结**: [cross-domain connections]
> **信号质量**: [overall quality score] / 1.0
>
> [if cold start]: "这是你的第一次复盘——历史模式会随着更多复盘数据而浮现。"
>
> [if signals filtered]: "以下信号未通过校准审查：[list with reasons]"
>
> [if alternative framings available]: "以下发现存在多种理解方式：[list alternative perspectives]"

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

3. **Action experiments** — present the adversary's concretized action rules:

> "以下是基于本轮发现的行动实验——请在接下来一周尝试："
>
> | 洞察 | 行动规则 | 验证方式 |
> |------|---------|---------|
> | [insight] | 如果[trigger]，那么[action] | [how_to_verify] |
>
> "每个实验都很小，不会打乱你的节奏。选 1-2 个最感兴趣的试试就好。"
>
> Ask the user: "想试试哪些行动实验？还是全部跳过？"

Wait for user response. Track which experiments they select.

4. **Confirmation prompt** — for each proposed diff:

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

2. **Mark loaded records as processed** — Update `state/records.jsonl`: for all records loaded in Step 0 (those with `processed_at: null`), set `processed_at: "<ISO>"` and `linked_reflection_id: "<this reflection's id>"`.

3. **Save selected action experiments** — append to `state/reflections.jsonl` as part of the reflection event. Selected experiments have `status: "active"`, `activated_at: <ISO>`, `expires_at: <ISO + 14 days>`, `outcome: null`. Unselected experiments have `status: "skipped"`. If user picks "跳过全部", all are `skipped`.

4. **Write reflection event to `state/reflections.jsonl`** — use the full schema from `references/reflection-protocol.md`. Append as a single JSON line.

5. **Index in claude-mem** — use `mcp__plugin_claude-mem_mcp-search__observation_add`:
   ```json
   {
     "content": "Reflection: [value_lens.summary] | [ability_lens.summary] | [pattern_lens.summary]",
     "kind": "reflection",
     "metadata": {
       "type": "reflection",
       "reflection_id": "<uuid>",
       "quality_score": <float>,
       "emotions": ["<emotion1>", "<emotion2>"],
       "attraction_signals": ["<topic1>", "<topic2>"],
       "records_loaded": <N>,
       "action_experiments_selected": <N>,
       "timestamp": "<ISO>"
     }
   }
   ```
   If claude-mem is unavailable: note the degraded mode. Reflection is still saved to JSONL.

6. **Confirm to user**:

> "已保存。复盘 ID: [id]"
>
> "状态更新: user_dna.json 已更新 [N] 项 / reflections.jsonl 累计 [N] 条 / claude-mem 索引完成"
>
> [If action experiments selected]: "[N] 个行动实验已记录，下次复盘时会回检。"

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
| Lens agent fails | Validation gate classifies as `failed`. Proceed per degraded mode rules (2/3 → relaxed, 1/3 → caveat, 0/3 → abort). |
| All three lenses fail | Abort with minimal event. Report to user. |
| All signals filtered | Honest output: no diffs proposed. Still save. |
| User rejects all | No DNA update. Rejection IS signal — record it. |
| claude-mem down | Save JSONL only. Report degraded mode. |
| JSONL file has corrupt lines | Skip unparseable lines. Report count. If >50% corrupt, recommend manual recovery. |
| JSONL file missing | Create new file. Not an error. |
| Short conversation | Full protocol. Confidence will naturally be lower. |

## Key Files

| File | Purpose |
|------|---------|
| `references/reflection-protocol.md` | Single source of truth — lens prompts, schemas, adversary rules |
| `state/user_dna.json` | Read as context, write accepted diffs |
| `state/reflections.jsonl` | Append full reflection event |
| `models/user_dna_schema.py` | Value dimension definitions and mapping rules |
