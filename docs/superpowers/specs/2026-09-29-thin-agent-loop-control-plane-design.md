# Thin Agent Loop, Thick Control Plane

**Date:** 2026-09-29
**Status:** approved design, pending written-spec review
**Scope:** a bounded, deterministic "investigation control plane" that lets the Agent
dynamically decide its next action, piloted on `reddit-opportunity`, then generalized to
`repo-trend`, with `builderdna` as the eventual top-level router.

---

## Goal

Let BuilderDNA decide its next investigation action from fresh evidence, while keeping
source calls, budget, state, evidence thresholds, persistence, and recovery deterministic.
Pilot on Reddit pain discovery (`reddit-opportunity`), then generalize to `repo-trend`, then
make `builderdna` the top-level entry point. The success outcome is more verifiable,
actionable pain clusters and opportunity hypotheses — **not longer reports**.

The project stays standalone: no Finch integration, no shared database/files/packages/Skills/CLI
or output contract, no social replies, relationship management, or writing drafts. `twitter-learning`
is retained. `concept-radar` keeps owning cross-source validation and the
`Watch / Verify / Build / Drop` state machine. The current local single-user
`Skill + Python CLI + file Workspace` is unchanged — no web service, no general graph runtime,
no new agent framework, no new database.

---

## Confirmed Decisions

1. **Scope:** spec covers P0–P5. P0–P3 (the Reddit pilot through replay evaluation) are fully
   specified; P4 (`repo-trend`) and P5 (`builderdna`) are specified at the design level only,
   each behind an explicit entry condition.
2. **Acquisition stays RSS-only for the pilot.** `inspect_thread`'s "context" is the post's full
   `selftext` plus linked upstream sources — comments are not read. Comment ingestion is an
   explicit post-P3 decision, not part of this spec.
3. **Architecture (A′):** reuse the existing evidence contract (`SourceHandoffItem`), RSS
   normalization (`concepts/adapters/reddit.py`), handoff (`concepts/handoffs.py`), and the
   JSONL store mechanics — rather than reimplementing them. Build only the genuinely new pieces:
   the investigation loop, the action contract, and the `PainClusterCandidate` model.
4. **Store mechanics:** extract the already-generic JSONL functions from `concepts/store.py`
   into a shared `state/jsonl.py` now (not deferred), so `ConceptStore` and the new
   `InvestigationStore` share one tested implementation. Protected by `test_concept_store.py`.

---

## Why reuse rather than rebuild

The plan's proposed `EvidenceItem` already exists as `SourceHandoffItem`
(`concepts/handoffs.py:112`), field-for-field:

| Plan's EvidenceItem | Existing `SourceHandoffItem` |
|---|---|
| raw URL / platform ID | `url` (stable `id` derived by `_evidence_id_for`) |
| author | `author` |
| published / collected time | `published_at` / `captured_at` |
| content summary | `excerpt` (note-taker paraphrase, not verbatim scrape) |
| source type | `source` (closed enum) |
| upstream origin | `upstream_origin` + `independence_key` |
| supports / refutes claim | `role` (`problem`/`implementation`/`adoption`/`counterevidence`) |
| observed / inferred / unknown | `directness` (`direct`/`indirect`/`inferred`) |

`SourceHandoffEnvelope` already pins `schema_version: Literal[1]`, provenance rules
(`directness != inferred` requires a url/upstream), UTC-only timestamps, "Reddit RSS never counts
as consensus/adoption", and "GitHub stars never become adoption". `import_handoff` is already
atomic, idempotent, and conflict-checked. Rebuilding any of this is pure duplication.

The genuinely missing pieces — which this spec adds — are:

- `Investigation` lifecycle + `ActionRecord` + budget / revision / checkpoint.
- The action contract (§3.3): request/response envelope, error shell, `allowed_next_actions`.
- The action executor that maps domain actions to RSS calls.
- The `PainClusterCandidate` model + its validation service.
- The replay / evaluation harness.

---

## Architecture

```text
scripts/reddit_rss.py                (RSS fetch — unchanged)
concepts/adapters/reddit.py          (infer_directness, independence_key_for_post — reused)
concepts/handoffs.py                 (SourceHandoffItem / Envelope / import_handoff — reused)
        ▲                                   ▲
        │ evidence contract                 │ user selects candidate → handoff to concept-radar
        │                                   │
investigations/   (NEW)                     │
  models.py       (Investigation, ActionRecord, PainClusterCandidate)
  contract.py     (Action request/response envelope + error shell)
  actions.py      (action registry + executor: action → RSS call + validation)
  service.py      (InvestigationService: init / run_action / propose / finish / resume)
  store.py        (InvestigationStore → state/jsonl.py)
        │
state/jsonl.py    (extracted generic JSONL mechanics: atomic write, idempotent append,
                   conflict detection, corruption guard)
concepts/store.py (ConceptStore, now built on state/jsonl.py)
```

Only the loop orchestration (`service.py`), action execution (`actions.py`), the action contract
(`contract.py`), three models, and `InvestigationStore` are new. Everything else is reused.

---

## Data Models

| Model | Key fields | State machine |
|---|---|---|
| `Investigation` | `id`, topic/target, `created_at`, `revision`, config/schema version + fingerprint, budget, `status`, action log, `checkpoint`, `end_reason` | `OPEN → PAUSED / COMPLETED / FAILED`; `PAUSED` is entered by `ask_user` (a fork escalated to the user) and returns to `OPEN` on `resume` |
| `ActionRecord` | `id`, `investigation_id`, pre/post `revision`, `action`, `canonical_params`, `reason`, `uncertainty_to_reduce`, result `status`, `observation`, `remaining_budget`, `allowed_next_actions` snapshot | append-only |
| `EvidenceItem` | **reused as `SourceHandoffItem`** (no new model) | — |
| `PainClusterCandidate` | problem statement, affected scenarios, independent cases (evidence refs), time span, existing workarounds, counterevidence, sample/coverage limits, open questions, minimal validation action | candidate, not a `ConceptCard` |

Collection status (`success` / `failed` / `no_results`) is recorded on the `ActionRecord.observation`,
**not** on the evidence. Evidence (`SourceHandoffItem`) is only produced for successfully collected
items; `seek_counterevidence`'s "no counterevidence found" is recorded as a coverage note, not as
evidence. This is what makes "source failure ≠ investigation failure" and "`no_results` vs failure"
expressible.

`PainClusterCandidate` is **not** the same type as `ConceptCard`. It is a single-source discovery
artifact (verbatim language, workaround inventory, counterevidence, coverage limits, minimal
validation action); `ConceptCard` is a cross-source lifecycle decision (stage/maturity/gate). The
translation already exists: `SourceHandoffItem.proposed_concept` → `capture_handoff`, applied only
after the user selects a candidate.

---

## Action Contract

**Request** (Agent → CLI):

```json
{
  "schema_version": "1",
  "investigation_id": "inv_...",
  "expected_revision": 4,
  "action": "seek_counterevidence",
  "params": {"claim_id": "claim_..."},
  "reason": "existing cases are all from one community, might be a local problem",
  "uncertainty_to_reduce": "whether other usage contexts already have a mature solution"
}
```

**Response** (CLI → Agent):

```json
{
  "status": "completed",
  "revision": 5,
  "observation": {
    "evidence_ids": ["ev_..."],
    "summary": "found one alternative-solution case; applicability pending",
    "source_status": "ok"
  },
  "remaining_budget": {"actions": 3},
  "allowed_next_actions": ["inspect_thread", "propose_pain_cluster", "finish"]
}
```

Errors reuse the same envelope with `status ∈ {no_results, source_failure, budget_exhausted,
invalid_action, stale_revision}`. `expected_revision` prevents stale context from overwriting newer
state. A retry with the same `(investigation_id, revision, action, canonical_params)` returns the
same saved result without re-calling the source or re-writing.

### v1 actions (RSS-only)

| Action | Purpose | Control-plane requirement |
|---|---|---|
| `search_discussions` | expand relevant discussions | query normalization, source budget, duplicate-query detection |
| `inspect_thread` | deep-read one candidate discussion + context | URL/ID whitelist; record collection result and failure reason |
| `find_similar_cases` | check recurrence across independent discussions | dedup by author/community/time/common-upstream (reuse `independence_key_for_post`) |
| `seek_workaround` | how users currently solve it | preserve verbatim quote; distinguish real practice from suggestion |
| `seek_counterevidence` | find "not a problem / already solved" evidence | record whether found + search coverage |
| `propose_pain_cluster` | submit a structured candidate | validate every fact is traceable and unknowns are explicit |
| `ask_user` / `finish` | escalate a key fork to the user, or end | checkpoint + end reason |

These are domain actions — no arbitrary shell or API surface is exposed to the Agent. Actions reuse
the existing RSS collection implementation.

---

## CLI Surface

A new `builderdna investigate` command group (Typer group, JSON-first, mirroring `concept`/`radar`):

```text
investigate init     --topic ... --subreddit r/X    create Investigation; return state + available actions
investigate run      --id ... --action ... --params ... --reason ... --expected-revision N
investigate status   --id ...                        revision / budget / action-log summary
investigate propose  --id ... --candidate ...        validate + persist a PainClusterCandidate
investigate finish   --id ... --reason ...           checkpoint + end reason
investigate resume   --id ...                        resume from the last completed action
```

Exit-code contract mirrors `concepts/service.py`: `0` success, `1` unexpected failure,
`2` validation error (including a rejected candidate), `3` conflict. Exit `4` (blocked gate) is
reserved but unused in the pilot — no investigation-level hard gate exists yet.

---

## Skill Rewrite (P2)

`reddit-opportunity/SKILL.md` changes from a long fixed recipe into four parts: **goal, available
actions, stop condition, output requirements**. Each round the Agent picks one action from
`allowed_next_actions`, with a reason that names a concrete evidence gap (never "keep searching").
It prioritizes counterevidence, workarounds, and independent cases; it stops at low information gain
or budget exhaustion and reports gaps honestly. It only ever submits `PainClusterCandidate`; the
domain service validates evidence and the fact/inference boundary before persisting.

Default bounded budget starts at **≤8 actions, ≤3 evidence rounds, ≤1 candidate per topic**, as
configurable parameters tuned through replay — not hard-coded domain truths. The existing daily cap
of ≤3 concept cards and ≤1 Build per week remains owned by concept-radar.

---

## Replay and Evaluation (P0 / P3)

**P0 — freeze the baseline.** Select 10–20 historical topics from the existing
`state/reddit/*.jsonl` corpus (14 subreddits already on disk) covering recurring pain, single-post
noise, same-source reposts, already-solved problems, source failure, and zero results. Save the
current output, runtime, and source-call count, and annotate each topic "useful / not useful + why".

**P3 — replay and release gate.** Run the fixed flow and the new flow over the same frozen topics and
blind-score five axes: PainCluster actionability; independent-evidence qualification rate (not
counting reposts as multiple cases); counterevidence coverage; unsupported-assertion count;
duplicate-candidate count — plus source calls / runtime / failure-recovery rate per useful candidate.

Release condition: useful-candidate quality improves, and unsupported assertions and duplicate
candidates do **not** increase. If gains come only from more calls, tighten queries and budget first.
Keep failure samples, adjust the Skill decision prompt or CLI gates, and re-compare against the same
replay set.

---

## P4 / P5 (design level, gated)

**P4 — generalize to `repo-trend`.** Reuse only the Action/Observation protocol, budget, source
tracking, idempotency, and checkpoint. Define repo-domain actions (growth anomalies,
Release/Issue/PR signals, alternative projects, maintenance signals). Trend velocity and sample
coverage stay in the deterministic domain service. Do not force Reddit's `PainClusterCandidate`
schema onto repo trends.
*Entry condition:* P3's real runs and replays prove dynamic supplementary evidence improves quality,
and the protocol is stable.

**P5 — `builderdna` as top-level router.** `builderdna` understands the user goal and routes to a
single-source analysis or concept-radar; it does **not** build another search loop. User-selected
structured results from a single-source specialist flow into `concept-radar` for cross-source
validation. The interest profile only changes investigation priority, never evidence strength or
Build gates.
*Entry condition:* `reddit-opportunity` and `repo-trend` run, recover, and evaluate independently;
routing tests prove one request is handled by exactly one primary Skill.

---

## Error Handling and Idempotency

- One action per round, validated before execution.
- Same `(investigation_id, revision, action, canonical_params)` retry → same saved result, no
  re-call, no re-write.
- `expected_revision` mismatch → `stale_revision`, nothing written.
- Partial source failure does not fail the investigation; `no_results` and failure are distinct.
- Atomic event append + checkpoint; resume from the last completed action.
- Corrections use the `supersedes` relationship (reused from the evidence model).
- Config/schema-version changes must not silently resume an old cycle (fingerprint check).

---

## Test Scenarios

1. Same post cross-posted across subreddits → counts as one upstream evidence chain.
2. Three independent users describe the same problem, but a mature workaround exists → keep the
   counterevidence and lower the opportunity judgment.
3. Zero search results vs Reddit timeout → different status, diagnostics, and next steps.
4. Duplicate action, stale revision, same-topic re-run → no duplicate write, no unbounded loop.
5. Fourth evidence round exceeds budget → ends with an explicit evidence gap and recovery info.
6. Resume after interruption vs uninterrupted run → same domain state under the same saved
   observations, config, and algorithm version.
7. Agent writes a commenter's speculation as fact, a missing URL, a fabricated independent source →
   candidate rejected with a concrete validation error.
8. Reddit single-source strong signal → can form a `PainClusterCandidate` but cannot satisfy
   concept-radar's cross-source BUILD gate on its own.

---

## Files to Change

| File | Change |
|---|---|
| `state/jsonl.py` | Extract generic JSONL mechanics from `concepts/store.py` |
| `concepts/store.py` | Rebuild `ConceptStore` on `state/jsonl.py` |
| `investigations/models.py` | `Investigation`, `ActionRecord`, `PainClusterCandidate` |
| `investigations/contract.py` | Action request/response envelope + error shell |
| `investigations/actions.py` | Action registry + executor (RSS-backed) |
| `investigations/service.py` | `InvestigationService` (init/run/propose/finish/resume) |
| `investigations/store.py` | `InvestigationStore` |
| `cli/commands/investigate.py` | New `investigate` command group |
| `cli/main.py` | Register `investigate` |
| `.claude/skills/reddit-opportunity/SKILL.md` | Rewrite as the four-part thin loop |
| `tests/test_investigation/` | Tests for the eight scenarios + store/contract/actions |

No change to `scripts/reddit_rss.py` (single-request fetcher), `concepts/handoffs.py`, or
`concepts/adapters/reddit.py`.

---

## Out of Scope

- Reddit comments, scores, votes, or removal data (deferred to a post-P3 decision).
- Reddit authentication or API credentials.
- A web service, graph runtime, agent framework, or new database.
- Automatic replies, posting, or customer outreach.
- Finch integration, or any shared database/files/packages/Skills/CLI with another project.
- Extracting shared cross-Skill capability beyond `state/jsonl.py` — per the implementation
  principle below.

## Implementation Principle

**Prove one dynamic supplementary-evidence decision changes a concrete judgment first, then extract
cross-Skill shared capability.** The only shared extraction in this spec (`state/jsonl.py`) reuses
already-tested machinery; the cross-Skill Action/Observation protocol is extracted only at P4, after
P3 demonstrates quality gain.
