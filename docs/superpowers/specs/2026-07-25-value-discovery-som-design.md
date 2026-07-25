# Value-Discovery: Sleight of Mouth Integration

**Date:** 2026-07-25
**Status:** approved
**Scope:** `.claude/skills/value-discovery/skill.md`

## Goal

Upgrade the value-discovery skill's Phase 2 signal detection from 5 patterns to 7 core + 2 auxiliary, drawing on Robert Dilts' *Sleight of Mouth* (《语言的魔力》) framework. The existing 5 signals already map to 4 SoM patterns; this design adds the 3 highest-ROI missing patterns plus 2 Chunking tools as optional auxiliaries.

## Current → Target

| Phase | Current | Target |
|-------|---------|--------|
| Phase 2 (Meta Model) | 5 signals | 7 core signals (+ Judgment Claim, + Belief Articulation) |
| Phase 3 (Coverage Check) | 1 bridging question type | Same + 3 auxiliary tools (Chunk Up, Chunk Down, Analogy) |
| Phase 4 (Conflict Detection) | Unchanged | Unchanged — new info flows in naturally |
| Phase 5 (Ranking Confirm) | Unchanged | +1 optional belief calibration checkpoint |
| Edge Cases | 5 entries | +6 entries (11 total) |

## Design Decisions

### 1. Two-tier architecture (core vs auxiliary)

**Decision:** 7 core signals scanned every response + 3 auxiliary tools used only when stuck.

**Rationale:** 9-way parallel signal matching would degrade agent judgment quality. The 7 core signals all have clear linguistic triggers that can be pattern-matched in a single pass. Chunking and Analogy are context-dependent "unsticking" tools that don't fit the trigger-word model — they need deliberate human-like judgment about when the user is stuck. Keeping them as optional tools preserves signal-to-noise ratio in the main loop.

### 2. Belief Articulation gated behind precondition

**Decision:** Only trigger Apply to Self (Belief Articulation) after ≥2 identifiable beliefs have surfaced.

**Rationale:** Apply to Self used too early reads as adversarial challenge, not curiosity. The SoM pattern's purpose is belief expansion, not belief attack. In a value-discovery context (not therapy), waiting until the user has demonstrated enough self-awareness to have multiple beliefs makes the question land as genuine reflection.

### 3. Every auxiliary tool has an explicit exit condition

**Decision:** "Use once, if no traction, pivot to a different path." No retry loops.

**Rationale:** Value-discovery's core strength is conversational naturalness. Retrying a failed analogy or re-chunking reads as mechanical — the user feels like they're in a script. The exit conditions are: Chunk Up → fall back to Phase 3 bridging; Chunk Down → if the scene contradicts the abstract value, go to Phase 4 Conflict Detection; Analogy → explicit abandon after one rejection.

### 4. Phase 4 and Phase 5 mostly unchanged

**Decision:** No structural changes to conflict detection or ranking confirmation.

**Rationale:** The new signals produce richer intermediate data, but the synthesis (ranking confirmation) and tension resolution (conflict detection) logic is already general enough to handle it. The one addition — an optional calibration checkpoint in Phase 5 when Belief Articulation was used — is additive, not structural.

## SoM Pattern Mapping

| SoM Pattern | Value-Discovery Signal | Status |
|-------------|----------------------|--------|
| Counterexample | Causal Belief → "有没有反例？" | existing |
| Redefine (Y) | Vague Word → "你怎么定义？" | existing |
| Hierarchy of Criteria | Comparison → "只能选一个，你选哪个？" | existing |
| Intention | Emotion Marker → "什么被满足/侵犯？" | existing |
| **Reality Strategy** | **Judgment Claim → "你的判断标准是什么？"** | **new** |
| **Apply to Self** | **Belief Articulation → "这个信念帮你看到/忽略了什么？"** | **new** |
| Chunking Up | Auxiliary Tool A | new (optional) |
| Chunking Down | Auxiliary Tool B | new (optional) |
| Analogy/Metaphor | Auxiliary Tool C | new (optional) |

## Signal Priority (when multiple signals fire simultaneously)

```
Belief Articulation (if precondition met)
  > Judgment Claim
    > Emotion Marker
      > Causal Belief / Identity / Comparison / Vague Word (pick strongest)
```

One question per turn. Never fire multiple follow-ups at once.

## Files to Change

| File | Change |
|------|--------|
| `.claude/skills/value-discovery/skill.md` | Replace Phase 2 signal table, expand Phase 3 with auxiliary tools, append Phase 5 calibration line, append 6 edge case entries |

## No Schema Changes

`state/user_dna_schema.py` and `state/user_dna.json` are unchanged. The output contract stays identical — richer inputs produce better data through the same output channels. Evidence log entries for new signal types use the same format as existing entries.

## Implementation Plan

1. Edit `.claude/skills/value-discovery/skill.md` — apply all four change sections:
   - **Section 1:** Replace Phase 2 signal table (5→7) + add signal priority rule
   - **Section 2:** Append auxiliary tools block to Phase 3
   - **Section 3:** Append 6 new edge cases + signal priority to Edge Cases table
   - **Section 4:** Append Belief Articulation calibration line to Phase 5
2. No tests to update — value-discovery is a skill (Claude-orchestrated), not Python code. The evaluation rubric in `evals/evals.json` is shared across all skills and doesn't test signal-level fidelity.
3. No schema or state files to update.
