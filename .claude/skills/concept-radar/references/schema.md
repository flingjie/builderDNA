# Concept Radar Schema

Human-readable contract for the concept lifecycle. Production code expresses the
same contracts as Pydantic models and JSON schemas; this file is the canonical
English description. Do not invent fields here — the Pydantic models are the
authoritative machine contract.

## Canonical contracts

### `ConceptCard`

The current snapshot of one concept. Fields:

- **identity** — stable ID and display name.
- **aliases** — alternative names the same concept has been captured under.
- **problem** — the job or failure the concept addresses.
- **why-now** — what changed that makes this worth acting on now.
- **source-linked evidence IDs** — evidence records backing this card.
- **maturity** — evidence status (how well-supported the concept is).
- **portfolio stage** — the lifecycle decision for this card (Inbox / Watch / Verify / Build / Drop).
- **component scores** — the individual score components that make up priority.
- **smallest experiment** — a bounded, falsifiable experiment proposal (required before Build).
- **prediction** — the prediction recorded on entry to Build.
- **outcome** — the recorded outcome of the Build experiment.
- **lesson** — the lesson learned from the outcome.

### `ConceptEvidence`

An immutable source record. Fields:

- **role** — the role this evidence plays (e.g. implementation vs adoption).
- **directness** — how directly the source speaks to the claim.
- **strength** — how strong the source is as evidence.
- **`independence_key`** — groups reposts or citations of one upstream claim so
  they do not inflate recurrence.

### `RadarReview`

An immutable transition record. Fields:

- **reason** — why the card transitioned.
- **expected evidence** — what evidence is expected next.
- **review date** — when the transition happened / next review is due.

### `RadarRunPayload`

A structured run summary from which Markdown is rendered. It records, per source,
whether the source was complete, partial, unavailable, or not requested, plus the
cards affected by the run.

## Invariants

1. **Evidence is immutable** — corrections append a superseding record rather than editing history.
2. **A concept has one current snapshot per ID** — updates are atomic.
3. **Maturity describes evidence status; stage describes a portfolio decision.**
4. **Reposts or citations of one upstream claim share an `independence_key`.**
5. **`user_alignment` changes priority only, never evidence strength or maturity.**
6. **`Build` requires two source types, two independent chains, reviewed counterevidence, and a bounded smallest experiment.**
