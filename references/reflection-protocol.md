# Reflection Protocol Reference

Shared protocol specification for the `/reflect` and `/distill` skills. **Single source of truth** — both skills reference this file for schemas, lens definitions, adversary rules, and storage conventions.

---

## Architecture Overview

```
RAL Recording Layer (daily, passive)
  │
  ├─ /note capture  → state/records.jsonl  (events + feelings)
  ├─ /note amplify  → add meaning + tags
  └─ /note weekly   → find connections + direction arrows
  │
  ▼
/reflect (single conversation + unprocessed records → extraction)
  │
  ├─ Load context: user_dna.json + reflections.jsonl + records.jsonl
  ├─ Check pending action experiments from previous reflection
  ├─ Step 0.5: Preprocess (long conversations: extract signal-rich excerpts → condensed map)
  ├─ Pass 1: Parallel 3-Lens Extraction
  │   ├─ Value Lens Agent   (segments → focus → attract/extract)
  │   ├─ Ability Lens Agent (segments → focus → detect edges)
  │   └─ Pattern Lens Agent (segments → focus → abstract 3 levels)
  ├─ Validation Gate (check schemas, handle failures, degraded modes)
  ├─ Pass 2: Adversary Agent (calibrate + reframe + concretize)
  ├─ Pass 3: Synthesize & Present Diffs + Action Experiments
  └─ User confirms/rejects → write reflections.jsonl + claude-mem + mark records processed

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

Run all three in parallel. Each receives the conversation (full transcript or condensed signal map from Step 0.5 preprocessing) as input, plus the current user_dna.json as context.

### Value Lens

**Prompt:**

> You are a Value Extraction Agent. Analyze the following conversation and extract what the user deeply cares about.
>
> **STEP 0 — Segment (切分):** Before any analysis, break the conversation into distinct segments by topic, task, or emotional register. A single undifferentiated "conversation" hides nuance. Identify 2-5 segments. For each, label the dominant topic and emotional tone.
>
> **STEP 1 — Focus (聚焦):** Not all segments are equal. Identify which segments contain the strongest signals — emotional spikes, unprompted initiation, flow states, or trade-off moments. Devote most of your analytical depth to the top 1-2 segments. Low-signal segments get a brief note; don't force findings from thin material.
>
> **STEP 2 — Extract:**
> **Primary orientation: what is the user pursuing?** Look for direction, attraction, and energy — not just what they resist, but what they move toward.
>
> **Value tags MUST come from the Tag Catalog (see below).** Valid keys: `autonomy|collaboration|stability|competition|creation|exploration|optimization|execution|devtools|end_user|infrastructure|knowledge|growth|mastery|recognition|wealth`. Dimensions: `environment|activity|output|reward`. Never invent new keys.
>
> Focus on:
> - **Attraction signals** — topics they initiate, explore, or lean into without being asked. What do they gravitate toward unprompted?
> - **Absorption** — moments of deep engagement, flow, or "losing track of time." What absorbs their full attention?
> - **Energy shifts** — topics that make them more animated, curious, or invested. When do they light up?
> - **Revealed preferences** — what they actually choose when given trade-offs, regardless of what they say they value
> - **Negative signals as navigation** — frustration, disappointment, and avoidance also point to what they value (strong reaction = something they care about was violated). Treat these as clues to underlying values, not as bugs to fix.
> - **Self-initiated investment** — what they sacrifice time or attention for without external demand
>
> Current self-model context (from user_dna.json): [insert values]
>
> Output structured JSON:
> ```json
> {
>   "segments": [
>     {
>       "label": "short label for this segment",
>       "topic": "what the conversation was about",
>       "emotional_tone": "dominant emotion",
>       "signal_strength": "high|medium|low",
>       "rationale": "why this signal strength — one sentence"
>     }
>   ],
>   "focus_segments": ["labels of the segments that received deep analysis"],
>   "candidate_values": [
>     {
>       "key": "autonomy|collaboration|stability|competition|creation|exploration|optimization|execution|devtools|end_user|infrastructure|knowledge|growth|mastery|recognition|wealth",
>       "dimension": "environment|activity|output|reward",
>       "evidence": "direct quote or behavioral observation from the conversation",
>       "segment": "which segment this came from",
>       "confidence": 0.0-1.0,
>       "direction": "strengthen|weaken|new"
>     }
>   ],
>   "attraction_signals": [
>     {
>       "topic": "what they were drawn to",
>       "trigger": "what sparked the pull — a question, discovery, or moment of interest",
>       "segment": "which segment",
>       "intensity": 1-10
>     }
>   ],
>   "emotional_spikes": [
>     {
>       "emotion": "excitement|frustration|pride|anxiety|curiosity|satisfaction|disappointment",
>       "trigger": "what caused it",
>       "intensity": 1-10,
>       "segment": "which segment",
>       "value_linked": "which value key this emotion connects to"
>     }
>   ],
>   "summary": "one-sentence synthesis of what this conversation reveals about the user's values — what they're moving TOWARD"
> }
> ```

### Ability Lens

**Prompt:**

> You are an Ability Detection Agent. Analyze the following conversation and extract demonstrated or emerging capabilities.
>
> **STEP 0 — Segment (切分):** Before any analysis, break the conversation into distinct segments by topic, task, or register. Identify 2-5 segments. For each, label the dominant activity and cognitive demand.
>
> **STEP 1 — Focus (聚焦):** The highest-signal segments are where the user initiates, persists, or makes novel connections without prompting. Devote most analytical depth to the top 1-2 segments. Low-signal segments don't need forced findings.
>
> **STEP 2 — Extract:**
> **Primary orientation: what is the user becoming?** Look for capacities in motion — skills they're growing into, not just ones they've already mastered.
>
> Focus on:
> - What they built, designed, or analyzed — especially work they initiated without external pressure
> - What connections they made that show depth — novel links between concepts
> - What frameworks or mental models they applied instinctively
> - What they taught or explained to others with enthusiasm
> - What complexity they navigated comfortably
> - **Intrinsic persistence** — what they keep working at despite difficulty or lack of external reward
> - **Emerging edges** — skills that are surfacing but not yet fully formed. What are they reaching toward that they can't do well yet but care about doing?
>
> Current self-model context (from user_dna.json): [insert values/preferences]
>
> Output structured JSON:
> ```json
> {
>   "segments": [
>     {
>       "label": "short label for this segment",
>       "activity": "what the user was doing",
>       "cognitive_demand": "what kind of thinking was required",
>       "signal_strength": "high|medium|low",
>       "rationale": "why this signal strength"
>     }
>   ],
>   "focus_segments": ["labels of the segments that received deep analysis"],
>   "demonstrated_abilities": [
>     {
>       "ability": "short label, e.g. system_design, code_architecture, strategic_thinking",
>       "evidence": "direct quote or behavioral observation",
>       "segment": "which segment this came from",
>       "level": "emerging|developing|mastered",
>       "confidence": 0.0-1.0
>     }
>   ],
>   "emerging_edges": [
>     {
>       "ability": "what they're reaching toward",
>       "evidence": "what shows this direction of growth",
>       "segment": "which segment",
>       "confidence": 0.0-1.0
>     }
>   ],
>   "new_connections": [
>     "description of a novel link the user made between concepts"
>   ],
>   "summary": "one-sentence synthesis of the user's demonstrated capabilities and growth direction"
> }
> ```

### Pattern Lens

**Prompt:**

> You are a Pattern Recognition Agent. Analyze the following conversation for recurring themes, decision patterns, and behavioral motifs.
>
> **STEP 0 — Segment (切分):** Break the conversation into distinct segments by topic, task, or emotional register (2-5 segments). For each, label the dominant pattern type.
>
> **STEP 1 — Focus (聚焦):** Devote analytical depth to segments with the strongest emotional or initiation signals. Don't spread thin — the top 1-2 segments hold most of the pattern information.
>
> **STEP 2 — Extract patterns:**
> **Primary orientation: what is the user consistently moving toward?** Look for pursuits, not just problems — the activities, ideas, and experiences they self-initiate across contexts.
>
> Focus on:
> - **Pursuit patterns** — what themes do they self-initiate vs. only respond to? What do they keep coming back to?
> - Repeated phrases or framing devices that reveal underlying assumptions
> - **Cross-domain connections** — do patterns in one area (work, learning, relationships) show up in others?
> - Consistent approaches to problems — their default toolkit
> - Recurring tensions or trade-offs — the dilemmas they keep circling back to
> - Decision-making heuristics the user applies
> - **Energy signature** — which activities or topics consistently raise their energy vs. drain it?
>
> **STEP 3 — Abstract (抽象化):** For each identified pattern, climb the abstraction ladder 3 levels:
> - **Case** — the specific instance from THIS conversation (the raw observation)
> - **Pattern** — the recurring theme this instance belongs to (the recognizable shape across instances)
> - **Principle** — the underlying truth about how this user operates (what would hold across domains and timescales)
>
> Example: "They spent 2 hours debugging a test config" (case) → "Invests heavily in toolchain reliability" (pattern) → "Values infrastructure-quality foundations that compound over time" (principle)
>
> Cross-reference data:
> - Current self-model (user_dna.json): [insert full model]
> - Historical reflections (if available): [insert search results from claude-mem]
> - If this is the first reflection: state "First reflection — cross-referencing user_dna.json only. Historical patterns will emerge with more data."
>
> Output structured JSON:
> ```json
> {
>   "segments": [
>     {
>       "label": "short label for this segment",
>       "pattern_type": "what kind of pattern this segment most reveals",
>       "signal_strength": "high|medium|low",
>       "rationale": "why this signal strength"
>     }
>   ],
>   "focus_segments": ["labels of the segments that received deep analysis"],
>   "identified_patterns": [
>     {
>       "pattern": "short label, e.g. learns_by_deconstructing, favors_depth_over_breadth",
>       "evidence": "direct quote or behavioral observation from THIS conversation",
>       "segment": "which segment",
>       "historical_links": ["reflection_id or 'none' for new patterns"],
>       "confidence": 0.0-1.0
>     }
>   ],
>   "abstraction_layers": [
>     {
>       "case": "the specific instance from this conversation",
>       "pattern": "the recurring theme this belongs to",
>       "principle": "the underlying truth about how this user operates — domain-agnostic, enduring",
>       "confidence": 0.0-1.0
>     }
>   ],
>   "cross_domain_connections": [
>     "description of a pattern that appears across different contexts (work, learning, relationships, etc.)"
>   ],
>   "energy_signature": {
>     "energizing": ["topics or activities that consistently energize the user"],
>     "draining": ["topics or activities that consistently drain the user"]
>   },
>   "recurring_dilemmas": [
>     "description of a tension that shows up repeatedly"
>   ],
>   "decision_heuristics": [
>     "description of an implicit rule the user applies"
>   ],
>   "summary": "one-sentence synthesis of the patterns detected — what is the user consistently moving toward?"
> }
> ```

---

## Agent Output Validation Gate (between Pass 1 and Pass 2)

Runs inline in the main conversation BEFORE the adversary agent is spawned. Validates all three lens outputs against their schemas.

### Failure Modes

| Mode | Definition | Action |
|------|-----------|--------|
| **Timeout** | Agent never returns (hangs > 120s) | Retry once with a shorter prompt. If still hangs, mark lens as `failed` and proceed with survivors. |
| **Empty return** | Agent returns null, empty string, or `{}` | Mark lens as `failed`. Don't retry — likely a systemic issue (prompt confusion, model refusal). |
| **Malformed JSON** | Return text exists but isn't valid JSON | Attempt extraction: find the first `{` and last `}`, parse the substring. If that fails too, mark as `failed`. |
| **Missing required fields** | JSON parses but required fields (`segments`, `summary`, etc.) are absent or empty arrays `[]` when signal was clearly present | Proceed with partial data. Flag which fields are missing. Adversary is told to rely less on this lens. |
| **Semantic garbage** | JSON is valid and fields exist, but content is nonsensical (e.g., repeated words, wrong language, fabrications with no evidence link) | Hardest to detect. Check: is `summary` >10 chars and in expected language? Does each finding's `evidence` contain an actual quote or specific behavioral description (not "they seemed to care")? Flag suspect outputs for adversary review. |
| **Stale cache / wrong context** | Agent returns plausible output that doesn't match THIS conversation | Check: do the `segments` labels correspond to actual conversation topics? Do the evidence quotes appear in the transcript? If clearly wrong context, discard and mark as `failed`. |

### Validation Protocol

For each lens output, verify these invariants before passing to adversary:

```
Value Lens:
  ✓ segments is non-empty array, each has label + signal_strength
  ✓ focus_segments is non-empty array
  ✓ summary is non-empty string
  ✓ candidate_values: each has key from allowed enum (Tag Catalog), confidence 0-1, direction from allowed enum
  ✓ NO candidate_value has a key outside the 16 allowed values. If found → drop that finding, flag as "invalid_tag"

Ability Lens:
  ✓ segments is non-empty array
  ✓ focus_segments is non-empty array
  ✓ summary is non-empty string
  ✓ demonstrated_abilities: each has ability label, evidence, level from allowed enum, confidence 0-1

Pattern Lens:
  ✓ segments is non-empty array
  ✓ focus_segments is non-empty array
  ✓ summary is non-empty string
  ✓ identified_patterns: each has pattern label, evidence, confidence 0-1
  ✓ abstraction_layers: if present, each has case + pattern + principle
```

### Degraded Modes

| Survivors | Action |
|-----------|--------|
| 3/3 passed | Full protocol. Adversary receives all three sets. |
| 2/3 passed | Proceed. Adversary is told: "Lens [X] failed — rely more on the surviving two lenses. Cross-corroboration thresholds are relaxed." |
| 1/3 passed | Proceed but flag heavily. Report: "[failed lenses] 未能完成分析，本次复盘仅基于 [surviving lens] 视角，信号可能不完整。" Adversary skips cross-lens corroboration. |
| 0/3 passed | Abort. Report to user: "本轮复盘无法完成——所有分析视角均未返回有效结果。可能是对话过长或内容过于复杂。建议先运行 `/note daily` 记录关键感受，或等待下一次对话。" Still save a minimal reflection event with `status: "aborted"` and the failure reasons. |

---

## Adversary Agent (Pass 2)

Runs AFTER all three lens agent outputs have been validated. Receives validated lens outputs as input.

### Calibrated Skeptic Posture

The adversary does NOT simply filter everything. It distinguishes between two things that are often confused:

- **Emotional intensity** (how much the user cares) — this IS evidence of importance, not noise to suppress
- **Interpretation accuracy** (whether the lens agent's specific claim about WHAT the emotion means is correct) — this is what needs verification

**Calibration rules (REVISED):**
- High emotional intensity (8-10) → **HIGH-VALUE SIGNAL.** The emotion itself is evidence that this matters deeply to the user. Scrutinize whether the SPECIFIC INTERPRETATION is correct — don't dismiss the signal because of its intensity. Flag as `deep_dive_candidate`.
- Medium emotional intensity (4-7) → Standard signal. Verify with at least one corroborating source.
- Low emotional intensity (1-3) → Light signal. Default to survive unless contradicted, but note the low emotional stake.

**Corroboration sources:**
1. Another lens agent found the same or related signal
2. user_dna.json shows a consistent value pattern
3. Historical reflections (if available) show the same pattern
4. The evidence quote is specific and behavioral (not vague)

**Reframing check (NEW):** For each finding, ask: "Is there an alternative interpretation of the same evidence that is more empowering or generative?" The goal is not to dismiss the original interpretation but to offer the user a choice of framings.

### Adversary Prompt

> You are a Calibrated Skeptic Agent. Review the following extraction outputs and sharpen each finding.
>
> **Your role has three parts:**
> 1. **Truth calibration** — verify that each claim is well-supported by evidence
> 2. **Meaning expansion** — offer alternative framings that might unlock new self-understanding
> 3. **Action concretization** — transform surviving insights into testable action experiments
>
> **Core principle: emotional intensity IS evidence of importance, not a reason to dismiss.** When the user has a strong emotional reaction, that tells you this matters. Your job is to verify that the SPECIFIC CLAIM about what it means is accurate — not to penalize intensity.
>
> For each finding, determine:
> 1. Does the evidence actually support this specific claim?
> 2. Is this finding corroborated across lenses or contradicted?
> 3. **Reframing check**: Is there an alternative, more empowering or generative interpretation of the same evidence? Offer it as an option — don't impose it.
> 4. **Perspective switch**: How would a trusted friend / mentor / future self interpret the same behavior? Offer one alternative perspective per major finding.
> 5. High emotional intensity + thin evidence → flag as "emotionally real, needs user judgment to interpret." Don't filter it out.
>
> **STEP — Concretize (具体化):** For every surviving signal and deep_dive_candidate, generate an action experiment — a specific, testable behavior the user can try. Format: **"If [trigger condition], then [specific action]."** The experiment must:
> - Be small enough to try within a week
> - Have a clear trigger (environmental cue, not vague feeling)
> - Be falsifiable — the user can tell whether they did it
> - Connect directly to the insight (the action tests whether the insight is real)
>
> Example: Insight "user values building tools over writing reports" → Experiment: "If I'm asked to produce a deliverable, then I'll spend 10 minutes building a small helper script before writing the narrative — and track which part energized me more."
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
>       "alternative_framing": "an alternative, more empowering interpretation of the same evidence (optional)",
>       "perspective_switch": "how a different observer (friend, mentor, future self) might see this (optional)",
>       "requires_user_judgment": true|false,
>       "user_question": "if requires_user_judgment, the question to ask the user"
>     }
>   ],
>   "action_experiments": [
>     {
>       "insight": "which finding this experiment tests",
>       "rule": "If [trigger], then [action].",
>       "trigger": "the specific environmental cue",
>       "action": "the specific behavior to try",
>       "how_to_verify": "how the user will know if it worked",
>       "expected_signal": "what insight would be confirmed if this works"
>     }
>   ],
>   "overall_quality_score": 0.0-1.0,
>   "deep_dive_candidates": [
>     {
>       "finding": "reference",
>       "rationale": "why this high-emotion signal warrants deeper exploration"
>     }
>   ],
>   "filtered_signals": [
>     {
>       "signal": "what was filtered",
>       "reason": "insufficient corroboration|contradicted_by_model|weak_evidence|alternative_explanation_more_likely"
>     }
>   ],
>   "surviving_signals_summary": "one-sentence synthesis of what survived and what it reveals about the user's direction"
> }
> ```

### All-Signals-Filtered Fallback

If the adversary filters ALL signals:

> "本轮复盘没有发现足够置信度的信号。但这不代表对话没有价值——可能这次对话更多是探索性的，信号仍然积累在你的记录中。当下一个高频情绪信号出现时，它会和这次的信号产生联结。No proposed diffs."

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
    "segments": [{"label": "...", "topic": "...", "emotional_tone": "...", "signal_strength": "high", "rationale": "..."}],
    "focus_segments": ["..."],
    "candidate_values": [
      {"key": "creation", "dimension": "activity", "evidence": "...", "segment": "...", "confidence": 0.8, "direction": "strengthen"}
    ],
    "attraction_signals": [
      {"topic": "...", "trigger": "...", "segment": "...", "intensity": 8}
    ],
    "emotional_spikes": [
      {"emotion": "excitement", "trigger": "...", "intensity": 8, "segment": "...", "value_linked": "creation"}
    ],
    "summary": "..."
  },
  
  "ability_lens": {
    "segments": [{"label": "...", "activity": "...", "cognitive_demand": "...", "signal_strength": "high", "rationale": "..."}],
    "focus_segments": ["..."],
    "demonstrated_abilities": [
      {"ability": "system_design", "evidence": "...", "segment": "...", "level": "developing", "confidence": 0.7}
    ],
    "emerging_edges": [
      {"ability": "what they're reaching toward", "evidence": "...", "segment": "...", "confidence": 0.6}
    ],
    "new_connections": ["linked X to Y"],
    "summary": "..."
  },
  
  "pattern_lens": {
    "segments": [{"label": "...", "pattern_type": "...", "signal_strength": "high", "rationale": "..."}],
    "focus_segments": ["..."],
    "identified_patterns": [
      {"pattern": "learns_by_deconstructing", "evidence": "...", "segment": "...", "historical_links": [], "confidence": 0.75}
    ],
    "abstraction_layers": [
      {"case": "specific instance", "pattern": "recurring theme", "principle": "underlying truth", "confidence": 0.8}
    ],
    "cross_domain_connections": ["pattern X appears across work and learning contexts"],
    "energy_signature": {
      "energizing": ["building tools", "exploring new tech"],
      "draining": ["status meetings", "context switching"]
    },
    "recurring_dilemmas": ["tradeoff between depth and breadth"],
    "decision_heuristics": ["prefers data-driven validation over intuition"],
    "summary": "..."
  },
  
  "adversary_verdict": {
    "surviving_signals": [
      {"finding": "ref", "survives": true, "adjusted_confidence": 0.85, "reasoning": "...", "alternative_framing": "...", "perspective_switch": "..."}
    ],
    "action_experiments": [
      {
        "insight": "...",
        "rule": "If ..., then ...",
        "trigger": "...",
        "action": "...",
        "how_to_verify": "...",
        "expected_signal": "...",
        "status": "active|completed|expired|skipped",
        "selected": true|false,
        "activated_at": "ISO",
        "expires_at": "ISO (activated_at + 14 days)",
        "outcome": null,
        "outcome_detail": null
      }
    ],
    "deep_dive_candidates": [
      {"finding": "ref", "rationale": "high emotional intensity warrants deeper exploration"}
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

## Cross-Domain Connections
- **[connection]**: [how a pattern spans across work, learning, relationships, etc.]

## Energy Signature
| Energizing | Draining |
|------------|----------|
| ... | ... |

## Demonstrated Growth
- **[ability]**: [from level → to level, with evidence]

## Emerging Edges
- **[ability]**: [what they're reaching toward, with evidence across reflections]

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
| One lens agent fails/returns empty | Validation gate classifies as `failed`. Surviving lenses proceed per degraded mode rules. Report flags the missing lens. |
| All three lens agents fail | Abort. Save minimal event with `status: "aborted"`. Report: "本轮复盘无法完成。" |
| Adversary filters ALL signals | Don't force survival. Output: "本轮复盘没有发现足够置信度的信号。但这不代表对话没有价值——可能这次对话更多是探索性的，信号仍然积累在你的记录中。当下一个高频情绪信号出现时，它会和这次的信号产生联结。No proposed diffs." |
| Proposed diff conflicts with current user_dna.json | Flag explicitly: "你之前认为[旧值]，这次信号建议[新值]。这可能代表成长，也可能代表这次对话的情绪强度放大了信号。你怎么看？" |
| reflections.jsonl / records.jsonl has corrupt lines | Skip unparseable lines. Report: "跳过 [N] 行损坏数据，已修复 [K] 行。" Proceed with readable data. |
| reflections.jsonl / records.jsonl >50% corrupt | Recommend manual recovery. Don't auto-delete. |
| records.jsonl missing (first note capture) | Create new file. Not an error. |
| claude-mem unavailable | Both skills work without semantic search. `/distill` falls back to date-range queries on JSONL. |
| User rejects ALL proposed diffs | No update to user_dna.json. Reflection saved with rejection record. This IS signal for future adversary calibration. |
| Conversation too short/low-signal | KEEP the multi-pass protocol. Extraction confidence will naturally be lower. Adversary will flag thin evidence. Output is honest about signal quality. |
| First reflection (cold start) | Full 3-agent protocol. Pattern Lens and Adversary cross-reference user_dna.json only (no historical reflections). Output notes: "这是你的第一次复盘——历史模式会随着更多复盘数据而浮现。" |
| Emotion intensity but no clear value link | Adversary flags: "情绪信号真实但无法映射到具体价值——建议用户自行确认。" Survives with `requires_user_judgment: true`. Added to `deep_dive_candidates`. |
| High-intensity signal with thin evidence | Don't filter. Survive with `requires_user_judgment: true`. Intensity IS evidence — of importance. The uncertainty is about interpretation, not about whether it matters. |

---

## `state/` File Map

| File | Purpose | Writer | Reader |
|------|---------|--------|--------|
| `state/user_dna.json` | User cognitive model | value-discovery, `/distill` | All skills |
| `state/reflections.jsonl` | Full reflection event log | `/reflect` | `/distill` |
| `state/records.jsonl` | RAL daily event captures | `/note` | `/reflect`, `/note` |
| `state/distill_reports/` | Distill markdown reports | `/distill` | User (readable) |
| `models/user_dna_schema.py` | Pydantic schema contract | (read-only reference) | All skills |

---

## State Integrity

JSONL files are append-only — they cannot be rolled back atomically on process crash or partial write. Every load must validate.

### Integrity Checks (run on every file open)

**For `state/records.jsonl` and `state/reflections.jsonl`:**

| Check | Rule | Recovery |
|-------|------|----------|
| File exists | If missing, create empty file. Not an error. | Create with `[]`-equivalent (empty). |
| Line parse | Each line must be valid JSON | Skip unparseable lines. Count them as `corrupt_lines`. Report: "跳过 [N] 行损坏数据。" |
| Required fields | Each record must have `id` (string), `timestamp` (ISO 8601) | Records missing `id`: assign a generated UUID and flag. Records missing `timestamp`: use the previous record's timestamp or file mtime. |
| Duplicate IDs | No two records may share the same `id` | Keep the first occurrence. Flag duplicates. |
| Field types | `confidence` must be numeric 0-1, `level` must be from allowed enum, etc. | Coerce obvious errors (string "0.8" → 0.8). Flag uncorrectable values and skip the field (not the record). |
| Temporal ordering | Records should be in ascending timestamp order (not strictly enforced, but warn) | If three or more records are out of order, report: "记录时间顺序异常，可能是手动编辑导致。" |

### Integrity Report

Every load produces a summary:

```
records.jsonl: [N] 条记录, [M] 条跳过 (损坏), [K] 条修复 (缺少字段)
reflections.jsonl: [N] 条记录, [M] 条跳过, [K] 条修复
```

If `M > 0`: warn the user. If `M > N/2`: recommend recovery.

### Write Safety

When appending to JSONL files in this project:

1. **Serialize the full record to a JSON string first** — catch serialization errors before touching the file.
2. **Append with a trailing newline** — every line must end with `\n`.
3. **Verify line count after write** — does the file have the expected number of lines? If not, the last line may be partial.
4. **If verify fails, don't truncate** — mark the file as suspect, report to user, and append a recovery record with the correct data. Manual cleanup later.

---

## Tag Catalog

Single source of truth for all tagging in the reflection ecosystem. Both Value Lens agents and the `/note` amplify step reference this catalog.

### Value Tags (closed enumeration — tracked in user_dna.json)

| Dimension | Keys | Description |
|-----------|------|-------------|
| **environment** | `autonomy` | Freedom to choose what and how to work |
| | `collaboration` | Working with and through others |
| | `stability` | Predictable, structured environment |
| | `competition` | Thriving in zero-sum or ranked contexts |
| **activity** | `creation` | Building new things from scratch |
| | `exploration` | Discovering, researching, understanding the unknown |
| | `optimization` | Improving existing systems and processes |
| | `execution` | Getting things done, shipping, delivering |
| **output** | `devtools` | Tools and infrastructure for developers |
| | `end_user` | Products and experiences for non-technical users |
| | `infrastructure` | Systems, platforms, foundations |
| | `knowledge` | Writing, teaching, sharing understanding |
| **reward** | `growth` | Personal development and learning |
| | `mastery` | Deep expertise in a craft or domain |
| | `recognition` | External validation, reputation, visibility |
| | `wealth` | Financial outcomes and resources |

These 16 keys are the ONLY valid values for:
- Value Lens `candidate_values[].key`
- Note `value_tags[]`
- user_dna.json value scoring

### Energy Tags (closed enumeration)

| Tag | Meaning |
|-----|---------|
| `energizing` | Activity consistently raises energy |
| `draining` | Activity consistently depletes energy |
| `neutral` | No clear energy signal |

### Domain Tags (open — user-defined, not tracked in user_dna)

Domain tags are free-form and context-specific. Common examples: `coding`, `design`, `writing`, `meeting`, `teaching`, `research`, `management`, `hiring`, `sales`, `strategy`. These help group records but don't feed into the self-model.

When amplifying a record, suggest relevant domain tags from the user's existing tag vocabulary (look at past records for common values), and invite new ones.

### Tag Usage Rules

1. **Value Lens**: MUST use only the 16 value keys. Never invent new ones.
2. **Note amplify**: Suggest from the value tag catalog. Allow free-form domain tags. If the user consistently uses a domain tag that maps to a value key, note it.
3. **Cross-population**: When a user adds a value tag during amplify, the next reflect's Value Lens gets a "user self-tagged" signal — higher confidence than purely extracted signals.
4. **Evolution**: If a value tag is never used across 10+ reflections, flag it as potential prune candidate in the next distill. If a new value dimension consistently emerges in domain tags, flag it as a potential new value key.

---

## Protocol Version

This is Version 6 of the reflection protocol. All NEW reflection events include `"protocol_version": 6`. Existing events from earlier protocol versions are still valid and loadable with the rules below.

### Naming convention

This project uses two distinct version fields:

| Field | Scope | Examples |
|-------|-------|----------|
| `protocol_version` | Reflection events in `reflections.jsonl`, digest gap reports in `digest_gaps.jsonl` | `"protocol_version": 6`, `"protocol_version": 2` |
| `version` | Persistent state files that track their own schema independently | `user_dna.json` (`"version": 1`), `hypotheses.json` (`"version": 1`), `watches.json` (`"version": 1`) |

They evolve at different rates: `protocol_version` tracks the reflection/digest process format (frequently updated), while `version` tracks the data schema of each state file (rarely changed). A v1 `user_dna.json` is valid regardless of whether reflections are produced under v6 of the protocol.

### Backward Compatibility

When loading reflections.jsonl, events may have been written under older protocol versions. Handle them safely:

| Loaded version | Strategy |
|---------------|----------|
| v6 (current) | Full field set available. Use as-is. |
| v3-v5 | Missing fields from v6 additions: `action_experiments[].activated_at`, `action_experiments[].expires_at`, `action_experiments[].status`, `attraction_signals`, `emerging_edges`, `abstraction_layers`, `deep_dive_candidates`, `alternative_framing`, `perspective_switch`, `segments`, `focus_segments`, `energy_signature`, `cross_domain_connections`. Treat all as absent (null/empty). |
| v1-v2 (legacy) | Original schema only: `candidate_values`, `emotional_spikes`, `demonstrated_abilities`, `identified_patterns`, `recurring_dilemmas`, `decision_heuristics`, `verdicts`, `filtered_signals`. All v3-v6 fields absent. Note: "此记录使用旧版协议 (v1/v2)，部分字段缺失。" |

**Key compat rules:**
1. Missing `attraction_signals` → don't error. Just use emotional_spikes as the sole value signals.
2. Missing `action_experiments` → skip experiment step for this reflection. No nudge needed.
3. Missing `energy_signature` / `cross_domain_connections` → distill can't use these. Rely on pattern + value data only.
4. Missing `segments` → the Segment/Focus step in Lens analysis still works (it's an analysis instruction, not a data dependency).
5. `protocol_version` missing entirely → assume v1 (earliest possible).

**No auto-migration:** Old reflections are NOT rewritten. They stay in their original protocol version. This avoids data corruption risk.

**Production note (2026-07-26):** The ONLY reflection in `state/reflections.jsonl` is a v1 record produced during initial skill bootstrapping. The v6 protocol has never been exercised with a real reflection. When `/reflect` runs for the first time under v6, watch for: preprocessing (Step 0.5) producing correct segment boundaries, `energy_signature` and `cross_domain_connections` populated correctly, action experiment lifecycle fields (`status`, `activated_at`, `expires_at`) written consistently. The backward-compatibility rules handle mixed-version batches, but the v6-only path is untested in production.

## Changelog

### v6 (2026-07-25): "Preprocessing, Validity, and Experiment Lifecycle"
- Added Conversation Preprocessing (Step 0.5) — signal-rich excerpt extraction for long conversations, 50-70% context savings
- Added Agent Output Validation Gate — 6 failure modes, per-lens invariant checks, 4 degraded mode paths including full abort
- Added State Integrity checks for JSONL files — line parsing, field validation, duplicate detection, write safety
- Added action experiment lifecycle: `status` tracking (active|completed|expired|skipped), `activated_at`/`expires_at` timestamps, age-based nudging (gentle at 5+ days, auto-expire at 14+ days)
- Added Unified Tag Catalog — single source of truth for 16 value keys, 3 energy tags, free-form domain tags. Value Lens and note amplify both reference the catalog. Cross-pollination: amplify tags feed reflect as higher-confidence signals.

### v5 (2026-07-25): "Validation Gate & Degraded Modes"
- Added Agent Output Validation Gate between Pass 1 and Pass 2
- Defines 6 failure modes: timeout, empty return, malformed JSON, missing fields, semantic garbage, stale cache
- Added per-lens invariant checks for required fields
- Added 4 degraded mode paths: 3/3 normal, 2/3 relaxed corroboration, 1/3 heavy caveat, 0/3 abort with minimal event
- Reflection events can now have `status: "aborted"` for complete failures

### v4 (2026-07-25): "RAL Recording Layer"
- Added RAL architecture layer: Record → Amplify → Layer (via new `/note` skill)
- Daily event captures stored in `state/records.jsonl`, fed into `/reflect` as additional signal sources
- `/reflect` Step 0 now loads unprocessed records alongside conversation transcript
- Architecture diagram updated to show three-layer pipeline: RAL → /reflect → /distill

### v3 (2026-07-25): "Segmentation + Abstraction + Concretization"
- **All 3 Lenses**: Added STEP 0 (Segment/切分) and STEP 1 (Focus/聚焦) as preprocessing instructions. All outputs gain `segments` and `focus_segments` fields. All signal items trace to their source `segment`.
- **Pattern Lens**: Added STEP 3 (Abstract/抽象化) with `abstraction_layers` — 3-level climb from case → pattern → principle for each finding.
- **Adversary**: Added third role: Action Concretization (具体化). Produces `action_experiments` — specific if-then rules with triggers, verification methods, and expected signals.
- **Reflect skill**: Step 0 now checks for pending action experiments from previous reflection. Step 3 presents action experiments to user for selection. Step 4 persists selected experiments.
- **Distill Report**: Added Abstraction Layers, Action Experiments, Cross-Domain Connections, Energy Signature, and Emerging Edges sections.

### v2 (2026-07-25): "Pursuit Orientation"
- **Value Lens**: Added `attraction_signals`. Reframed focus from "what they defend" to "what they're drawn toward." Negative emotions repositioned as navigation signals, not bugs.
- **Ability Lens**: Added `emerging_edges` and `intrinsic persistence` focus. Reframed from "what they can do" to "what they're becoming."
- **Pattern Lens**: Added `cross_domain_connections` and `energy_signature`. Reframed from "what repeats" to "what direction does it point."
- **Adversary**: Flipped calibration logic — emotional intensity is evidence of importance, not a threat to filter aggressively. Added `alternative_framing`, `perspective_switch`, and `deep_dive_candidates`.
- **Distill Report**: Added Cross-Domain Connections, Energy Signature, and Emerging Edges sections.

### v1 (original): "Defense Orientation"
- Initial protocol with Value/Ability/Pattern lenses and Calibrated Skeptic adversary.
