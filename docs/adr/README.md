# Architecture Decision Records (ADR)

BuilderDNA uses Architecture Decision Records to document every meaningful architectural choice. Each ADR captures the context, the decision, the alternatives considered, measurable proof, honest limits, and verification steps.

## Template

```markdown
# ADR-NNN — [One-line summary of the decision]

**Status**: Proposed | Accepted | Implemented | Superseded
**Date**: YYYY-MM-DD
**Supersedes**: ADR-XXX (if replacing a prior decision)
**Related**: ADR-XXX, issue #XXX

## Context

Why does this decision need to be made now? What is the current state? What data do we have?

## Decision

What did we choose? Be specific — name the library, the parameter values, the interface shape.

## Alternatives Considered

What other options did we evaluate? Why were they rejected? (One paragraph per alternative.)

## Consequences

### Positive
- What gets better because of this?

### Negative  
- What gets worse? What new constraints do we take on?

### Follow-up
- What needs to be tracked or revisited later?

## Measured Proof (if applicable)

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| ... | ... | ... | ... |

## Honest Limits

- What edge cases does this not cover?
- Under what conditions would this decision need to be revisited?

## Verification

```bash
# Commands to verify this decision is correctly implemented
```
```

## Conventions

- **Numbering**: global increment (ADR-001, ADR-002, ...). Never reuse numbers.
- **Status lifecycle**: `Proposed` → `Accepted` → `Implemented` → `Superseded`
- **File naming**: `ADR-NNN-slug-title.md` (e.g., `ADR-001-dual-loop-architecture.md`)
- **Updates**: amend the original ADR with dated status updates rather than creating a new ADR for small corrections
- **Superseding**: when a decision is reversed, mark the old one `Superseded` and link to the new one via `Supersedes`

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](ADR-001-dual-loop-architecture.md) | Dual-Loop Architecture (Claude Code + Python Sandbox) | Implemented | 2026-07-27 |
| [ADR-002](ADR-002-python-typer-uv-stack.md) | Python + Typer + uv Technology Stack | Implemented | 2026-07-27 |
| [ADR-003](ADR-003-local-ollama-embeddings.md) | Local Ollama Embeddings for Pain Analysis | Implemented | 2026-07-27 |
| [ADR-004](ADR-004-goap-astar-planner.md) | GOAP A* Planner in Skill Layer | Accepted | 2026-07-27 |
| [ADR-005](ADR-005-adr-system-introduction.md) | ADR System Introduction | Implemented | 2026-07-27 |
