# Reflection Protocol Reference

Shared protocol specification for the `/reflect` and `/distill` skills. **Single source of truth** — both skills reference this file for schemas, lens definitions, adversary rules, and storage conventions.

---

## Architecture Overview

```
/reflect (single conversation → extraction)
  │
  ├─ Load context: user_dna.json + reflections.jsonl
  ├─ Pass 1: Parallel 3-Lens Extraction
  │   ├─ Value Lens Agent
  │   ├─ Ability Lens Agent
  │   └─ Pattern Lens Agent
  ├─ Pass 2: Adversary Agent (Calibrated Skeptic)
  ├─ Pass 3: Synthesize & Present Diffs
  └─ User confirms/rejects → write reflections.jsonl + claude-mem

/distill (cross-reflection synthesis → growth report)
  │
  ├─ Gather unprocessed reflections
  ├─ Semantic search via claude-mem
  ├─ Produce Tension + Resolution narrative
  ├─ Propose user_dna.json diffs
  ├─ Write markdown report to state/distill_reports/
  └─ User confirms/rejects → update user_dna.json
```

---

## The Three Lenses (Pass 1)

Run all three in parallel. Each receives the FULL conversation transcript as input, plus the current user_dna.json as context.

### Value Lens

**Prompt:**

> You are a Value Extraction Agent. Analyze the following conversation and extract what the user deeply cares about.
>
> Focus on:
> - What they defend or argue for
> - What they sacrifice time or attention for
> - What triggers emotional spikes (excitement, frustration, pride)
> - What they choose when given trade-offs
>
> Current self-model context (from user_dna.json): [insert values]
>
> Output structured JSON:
> ```json
> {
>   "candidate_values": [
>     {
>       "key": "autonomy|collaboration|stability|competition|creation|exploration|optimization|execution|devtools|end_user|infrastructure|knowledge|growth|mastery|recognition|wealth",
>       "dimension": "environment|activity|output|reward",
>       "evidence": "direct quote or behavioral observation from the conversation",
>       "confidence": 0.0-1.0,
>       "direction": "strengthen|weaken|new"
>     }
>   ],
>   "emotional_spikes": [
>     {
>       "emotion": "excitement|frustration|pride|anxiety|curiosity|satisfaction|disappointment",
>       "trigger": "what caused it",
>       "intensity": 1-10,
>       "value_linked": "which value key this emotion connects to"
>     }
>   ],
>   "summary": "one-sentence synthesis of what this conversation reveals about the user's values"
> }
> ```

### Ability Lens

**Prompt:**

> You are an Ability Detection Agent. Analyze the following conversation and extract demonstrated or emerging capabilities.
>
> Focus on:
> - What they built, designed, or analyzed
> - What connections they made that show depth
> - What frameworks or mental models they applied
> - What they taught or explained to others
> - What complexity they navigated comfortably
>
> Current self-model context (from user_dna.json): [insert values/preferences]
>
> Output structured JSON:
> ```json
> {
>   "demonstrated_abilities": [
>     {
>       "ability": "short label, e.g. system_design, code_architecture, strategic_thinking",
>       "evidence": "direct quote or behavioral observation",
>       "level": "emerging|developing|mastered",
>       "confidence": 0.0-1.0
>     }
>   ],
>   "new_connections": [
>     "description of a novel link the user made between concepts"
>   ],
>   "summary": "one-sentence synthesis of the user's demonstrated capabilities"
> }
> ```

### Pattern Lens

**Prompt:**

> You are a Pattern Recognition Agent. Analyze the following conversation for recurring themes, decision patterns, and behavioral motifs.
>
> Focus on:
> - Repeated phrases or framing devices
> - Similar dilemmas to past reflections (cross-reference provided history)
> - Consistent approaches to problems
> - Recurring tensions or trade-offs
> - Decision-making heuristics the user applies
>
> Cross-reference data:
> - Current self-model (user_dna.json): [insert full model]
> - Historical reflections (if available): [insert search results from claude-mem]
> - If this is the first reflection: state "First reflection — cross-referencing user_dna.json only. Historical patterns will emerge with more data."
>
> Output structured JSON:
> ```json
> {
>   "identified_patterns": [
>     {
>       "pattern": "short label, e.g. learns_by_deconstructing, favors_depth_over_breadth",
>       "evidence": "direct quote or behavioral observation from THIS conversation",
>       "historical_links": ["reflection_id or 'none' for new patterns"],
>       "confidence": 0.0-1.0
>     }
>   ],
>   "recurring_dilemmas": [
>     "description of a tension that shows up repeatedly"
>   ],
>   "decision_heuristics": [
>     "description of an implicit rule the user applies"
>   ],
>   "summary": "one-sentence synthesis of the patterns detected"
> }
> ```

---

## Adversary Agent (Pass 2)

Runs AFTER all three lens agents complete. Receives all three lens outputs as input.

### Calibrated Skeptic Posture

The adversary does NOT simply filter everything. It weights its skepticism based on the finding's **emotional intensity** — the primary signal of impact.

**Calibration rules:**
- High emotional intensity (8-10) → aggressive scrutiny. Demand multiple corroborating signals.
- Medium emotional intensity (4-7) → moderate scrutiny. Look for at least one corroborating signal.
- Low emotional intensity (1-3) → light scrutiny. Default to "survive unless clearly contradicted."

**Corroboration sources:**
1. Another lens agent found the same or related signal
2. user_dna.json shows a consistent value pattern
3. Historical reflections (if available) show the same pattern
4. The evidence quote is specific and behavioral (not vague)

### Adversary Prompt

> You are a Calibrated Skeptic Agent. Review the following extraction outputs and challenge each finding.
>
> Your job is NOT to dismiss everything. It is to calibrate: **the higher the claimed impact, the more evidence required.**
>
> For each finding, determine:
> 1. Does the evidence actually support this claim?
> 2. Are there alternative explanations for the observed behavior?
> 3. Is this finding corroborated across lenses or contradicted?
> 4. If emotional intensity is high but evidence is thin — flag as "emotionally real but insufficiently grounded."
>
> Inputs:
> - Value Lens output: [insert]
> - Ability Lens output: [insert]
> - Pattern Lens output: [insert]
> - Current user_dna.json: [insert]
>
> Output structured JSON:
> ```json
> {
>   "verdicts": [
>     {
>       "finding": "reference to which lens finding",
>       "survives": true|false,
>       "adjusted_confidence": 0.0-1.0,
>       "reasoning": "why it survived or was filtered",
>       "requires_user_judgment": true|false,
>       "user_question": "if requires_user_judgment, the question to ask the user"
>     }
>   ],
>   "overall_quality_score": 0.0-1.0,
>   "filtered_signals": [
>     {
>       "signal": "what was filtered",
>       "reason": "insufficient corroboration|contradicted_by_model|weak_evidence|alternative_explanation_more_likely"
>     }
>   ],
>   "surviving_signals_summary": "one-sentence synthesis of what survived and why it matters"
> }
> ```

### All-Signals-Filtered Fallback

If the adversary filters ALL signals:

> "本轮复盘没有发现足够置信度的信号。这不代表对话没有价值——可能只是因为这次对话更多是探索性的，而非决策性的。No proposed diffs."

Still save the reflection event to JSONL with `user_decisions: {accepted: [], rejected: []}`. This IS signal — future adversary agents can learn from what gets filtered.

---

## Result Synthesizer (Pass 3 — inline in `/reflect`)

After the adversary produces surviving signals, Claude (in the main conversation) synthesizes them into:

1. **Conversational summary** — "Here's what I noticed in this conversation..."
2. **Proposed user_dna.json diffs** — specific, evidence-linked changes
3. **Confirmation prompt** — immediate inline, user confirms/rejects each diff

---

## Reflection Event Schema (`state/reflections.jsonl`)

Each line is a JSON object:

```json
{
  "id": "uuid",
  "timestamp": "ISO 8601",
  "session_id": "optional conversation identifier",
  "source": "one-line summary of what the conversation was about",
  
  "value_lens": {
    "candidate_values": [
      {"key": "creation", "dimension": "activity", "evidence": "...", "confidence": 0.8, "direction": "strengthen"}
    ],
    "emotional_spikes": [
      {"emotion": "excitement", "trigger": "...", "intensity": 8, "value_linked": "creation"}
    ],
    "summary": "..."
  },
  
  "ability_lens": {
    "demonstrated_abilities": [
      {"ability": "system_design", "evidence": "...", "level": "developing", "confidence": 0.7}
    ],
    "new_connections": ["linked X to Y"],
    "summary": "..."
  },
  
  "pattern_lens": {
    "identified_patterns": [
      {"pattern": "learns_by_deconstructing", "evidence": "...", "historical_links": [], "confidence": 0.75}
    ],
    "recurring_dilemmas": ["tradeoff between depth and breadth"],
    "decision_heuristics": ["prefers data-driven validation over intuition"],
    "summary": "..."
  },
  
  "adversary_verdict": {
    "surviving_signals": [
      {"finding": "ref", "survives": true, "adjusted_confidence": 0.85, "reasoning": "..."}
    ],
    "filtered_signals": [
      {"signal": "...", "reason": "insufficient_corroboration"}
    ],
    "overall_quality_score": 0.7,
    "surviving_signals_summary": "..."
  },
  
  "proposed_dna_diffs": {
    "values": {
      "environment": {
        "scores": {
          "autonomy": {"from": 7, "to": 8, "evidence": "...", "confidence": 0.8}
        }
      }
    },
    "beliefs": [
      {"statement": "...", "confidence": 0.85, "action": "add", "evidence": "..."}
    ],
    "criteria": [
      {"decision_context": "技术选型", "rule": "...", "action": "add"}
    ]
  },
  
  "user_decisions": {
    "accepted": ["diff_reference_1"],
    "rejected": ["diff_reference_2"],
    "modified": [
      {"diff": "diff_reference_3", "user_override": "actual value the user chose"}
    ]
  },
  
  "distilled_at": null,
  "distill_batch_id": null
}
```

---

## DNA Diff Format

When proposing changes to user_dna.json, use this format:

```json
{
  "values": {
    "<dimension: environment|activity|output|reward>": {
      "scores": {
        "<key>": {
          "from": <current_score_or_null_if_new>,
          "to": <proposed_score>,
          "evidence": "<quote or behavioral observation>",
          "confidence": 0.0-1.0
        }
      },
      "ranking": ["<proposed new ranking>"]
    }
  },
  "beliefs": [
    {
      "statement": "<belief text>",
      "confidence": 0.0-1.0,
      "action": "add|remove|modify",
      "previous": "<previous statement if modify>",
      "evidence": "<supporting evidence>"
    }
  ],
  "criteria": [
    {
      "decision_context": "<context>",
      "rule": "<rule text>",
      "action": "add|remove|modify",
      "evidence": "<supporting evidence>"
    }
  ],
  "preferences": {
    "<field>": {"from": "<current>", "to": "<proposed>", "evidence": "..."}
  }
}
```

---

## Distill Report Template

Written to `state/distill_reports/YYYY-MM-DD_distill.md`.

```markdown
# Growth Report — [date range]

## Executive Summary
[2-3 sentence overview of the period's key shifts]

## Central Tension
[The primary conflict or dilemma that dominated this period]

## Resolution
[How the tension was resolved — or why it's still unresolved]

## Value Evolution
| Value | Before | After | Evidence |
|-------|--------|-------|----------|
| ... | ... | ... | ... |

## Emerging Patterns
- **[pattern name]**: [description with cross-reflection evidence]
- ...

## Demonstrated Growth
- **[ability]**: [from level → to level, with evidence]

## Proposed Self-Model Updates
- [diff 1]: [rationale]
- [diff 2]: [rationale]

## Unresolved Questions
- [questions the data raises but can't answer yet]

## Reflection Stats
- Reflections processed: N
- Overall quality score: X
- Time range: [start] → [end]
```

---

## Auto-Suggest Threshold (`/distill`)

After each `/reflect`, check if the user should be nudged to run `/distill`:

**Formula: Cumulative Impact Score**

```
impact = Σ (|score_change| × emotional_intensity) for all proposed diffs across unprocessed reflections
```

Nudge when `impact >= 15` (calibratable threshold — roughly equivalent to 3 moderate-value shifts or 1-2 high-intensity shifts).

**Nudge message:**

> "你的复盘记录中积累了 [N] 条未处理的信号，累计影响分数为 [score]。建议运行 `/distill` 进行一次阶段性合成。现在跑还是稍后？"

If the user declines, wait until the next `/reflect` completes before suggesting again.

---

## claude-mem Integration

**Purpose**: semantic search across historical reflections (NOT primary storage).

**What gets embedded**:
- `observation_add` per reflection event with: id, timestamp, value_lens.summary, ability_lens.summary, pattern_lens.summary, emotional_spikes, tags
- Metadata: `{type: "reflection", reflection_id: "uuid", quality_score: float}`

**Primary storage**: `state/reflections.jsonl` — full fidelity. This is the source of truth.

**Fallback**: If claude-mem is unavailable, `/distill` falls back to date-range queries on JSONL. Degraded but functional.

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| user_dna.json missing or empty | `/reflect` runs without self-model context. Report notes: "没有现有的自我模型做对比，建议先运行 value-discovery。" |
| One lens agent fails/returns empty | Surviving lenses proceed. Adversary runs on available signals. Report flags the missing lens. |
| Adversary filters ALL signals | Don't force survival. Output: "本轮复盘没有发现足够置信度的信号。这不代表对话没有价值——可能只是因为这次对话更多是探索性的，而非决策性的。" |
| Proposed diff conflicts with current user_dna.json | Flag explicitly: "你之前认为[旧值]，这次信号建议[新值]。这可能代表成长，也可能代表这次对话的情绪强度放大了信号。你怎么看？" |
| reflections.jsonl corrupted/unreadable | `/reflect` creates new file. `/distill` reports: "无法读取部分历史记录，本次合成仅基于可读取的 X 条记录。" |
| claude-mem unavailable | Both skills work without semantic search. `/distill` falls back to date-range queries on JSONL. |
| User rejects ALL proposed diffs | No update to user_dna.json. Reflection saved with rejection record. This IS signal for future adversary calibration. |
| Conversation too short/low-signal | KEEP the multi-pass protocol. Extraction confidence will naturally be lower. Adversary will flag thin evidence. Output is honest about signal quality. |
| First reflection (cold start) | Full 3-agent protocol. Pattern Lens and Adversary cross-reference user_dna.json only (no historical reflections). Output notes: "这是你的第一次复盘——历史模式会随着更多复盘数据而浮现。" |
| Emotion intensity but no clear value link | Adversary flags: "情绪信号真实但无法映射到具体价值——建议用户自行确认。" Survives with `requires_user_judgment: true`. |

---

## `state/` File Map

| File | Purpose | Writer | Reader |
|------|---------|--------|--------|
| `state/user_dna.json` | User cognitive model | value-discovery, `/distill` | All skills |
| `state/reflections.jsonl` | Full reflection event log | `/reflect` | `/distill` |
| `state/distill_reports/` | Distill markdown reports | `/distill` | User (readable) |
| `state/user_dna_schema.py` | Pydantic schema contract | (read-only reference) | All skills |

---

## Protocol Version

This is Version 1 of the reflection protocol. All reflection events include `"protocol_version": 1` in their schema for forward-compatibility.
