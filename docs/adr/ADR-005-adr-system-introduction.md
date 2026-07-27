# ADR-005 — ADR System Introduction

**Status**: Implemented
**Date**: 2026-07-27
**Related**: ADR-004 (GOAP A* Planner), ruvnet/ruflo ADR system (reference implementation)

## Context

BuilderDNA has made several significant architectural decisions since its inception (dual-loop architecture, Python stack, local embeddings, SQLite storage, collector cache design). These decisions are documented in `CLAUDE.md` under "Key Design Decisions" — but only as one-line summaries. There is no record of:

- **Why** each decision was made (the alternatives considered)
- **What data** supported the decision (measured proof)
- **What the limits are** (when to revisit)
- **How decisions connect** (the decision chain — which ADR led to which)

This makes it hard for future contributors (and future selves) to understand the architecture's evolution, and risks repeating past debates.

Ruflo's 110+ ADR system demonstrated that lightweight, indexed decision records create a self-documenting architecture. Each ADR is short (~200 lines), has a standard template, and forms a linked chain via `Related` and `Supersedes` fields.

## Decision

Adopt the ADR (Architecture Decision Record) system for BuilderDNA, modeled on Ruflo's practice:

### Format
Standard 5-section template: **Context → Decision → Alternatives Considered → Consequences → Honest Limits**. Optional sections: **Measured Proof** (when data is available) and **Verification** (reproducible commands).

### Location
`docs/adr/ADR-NNN-slug-title.md` — independent directory with index in `docs/adr/README.md`.

### Numbering
Global increment (ADR-001, ADR-002, ...). Numbers are never reused. Superseded ADRs keep their number and gain a `Superseded` status with a link to the replacing ADR.

### Status Lifecycle
```
Proposed → Accepted → Implemented → Superseded
```
- **Proposed**: written but not yet agreed upon
- **Accepted**: agreed upon, pending implementation
- **Implemented**: code matches the decision
- **Superseded**: replaced by a newer ADR (still valuable as historical record)

### Updates
When an ADR's implementation status changes or new evidence arrives, amend the original file with a dated **Status Update** section at the bottom. Don't create a new ADR for small corrections.

### Writing Discipline
- Write the ADR **at decision time**, not retrospectively
- Be specific: name libraries, parameter values, interface shapes
- Include honest limits — what this decision does NOT solve
- When possible, include measured proof (before/after metrics)

## Alternatives Considered

### Keep decisions in CLAUDE.md
Rejected: `CLAUDE.md` is 150+ lines and growing. It's a project overview, not a decision log. Adding full ADR content there would make it unreadable.

### Date-based numbering (ADR-2026-07-27-01)
Rejected: when multiple ADRs are written on the same day, date-based numbering adds unnecessary suffix complexity. Sequential numbering establishes a clear timeline without date parsing.

### Simplified template (Decision + Context only)
Rejected: the "Alternatives Considered" and "Honest Limits" sections are the highest-value parts of an ADR — they prevent repeating past debates and set clear boundaries for when to revisit. Removing them would make ADRs less useful.

## Consequences

### Positive
- Architecture decisions become traceable and searchable
- New contributors can understand why the codebase is shaped the way it is
- ADR index in `docs/adr/README.md` provides a one-glance decision timeline
- Decision chains show how the architecture evolved (e.g., ADR-001 dual loop → ADR-004 GOAP planner)

### Negative
- Writing ADRs takes discipline — it's easy to skip when moving fast
- 5-section template may feel heavy for small decisions (can shorten for trivial ones)
- Backfilling historical decisions (ADR-001 through ADR-003) captures the decision but not the original decision-making context

### Follow-up
- Enforce in code review: significant architectural changes should include an ADR
- Periodically audit: are ADRs being written? Are superseded ones marked?
- Consider a CI check that flags PRs touching architecture-critical files without a corresponding ADR

## Honest Limits

- This system depends on human discipline — it won't work if we skip writing ADRs
- Retrospective ADRs (001-003) lack the "at decision time" freshness
- The ADR index must be manually maintained (adding new entries to README.md)
- Small iterative changes may not warrant a full ADR — use judgment

## Verification

```bash
# Check ADR directory exists and has index
ls docs/adr/README.md

# Verify all ADRs referenced in the index exist
for f in $(grep -oP 'ADR-\d{3}[^)]+' docs/adr/README.md | grep -oP 'ADR-\d{3}[^.]*'); do
  test -f "docs/adr/${f}.md" || echo "MISSING: $f"
done

# Count ADRs
ls docs/adr/ADR-*.md | wc -l
```
