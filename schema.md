# BuilderDNA Schema Reference

Claude Code reads these JSON outputs. Radar file artifacts use a `SandboxResult`-shaped
wrapper when emitted to disk. Interactive `concept` / `investigate` (and most `radar`)
CLI commands print a versioned JSON envelope to stdout instead.

## Common Wrapper (`SandboxResult`)

Used when a command writes a structured run artifact (e.g. radar scan/verify JSON):

```json
{
  "command": "<name>", "schema_version": "1.0", "domain": "<domain>", "computed_at": "<ISO8601>",
  "payload": {...}, "stats": {...},
  "diagnostics": {"data_quality": {...}, "confidence": {...}, "parameter_sensitivity": [...]},
  "errors": [{"code": "...", "message": "...", "source": "...", "recoverable": true}]
}
```

### schema_version

Every `SandboxResult` carries `schema_version` (semver string). Readers check it before
parsing `payload`. Bump on breaking changes to the payload contract.

### errors (unified error structure)

Recoverable per-source/per-item failures are recorded in `errors`, not raised. Each entry:
- `code` — stable machine-readable code (`rate_limited`, `source_unavailable`, `validation_failed`, …)
- `message` — human-readable description
- `source` — which step/source/item produced it (empty when global)
- `recoverable` — whether the command could continue past it

Hard failures raise (no `SandboxResult` is emitted). Partial source failures complete with
their `errors` list preserved — diagnostics are never silently dropped.

### immutability & correction

Appended events are immutable. Corrections add a superseding record (`supersedes` points to
the ID of the record it replaces) rather than editing history. Same input + same config
version + same algorithm version ⇒ stable output.

Authoritative machine contracts for concept lifecycle fields live in `models/concept.py`
and `.claude/skills/concept-radar/references/schema.md`.

## concept → stdout (`builderdna.concept.v1`)

JSON-first envelope (not a `SandboxResult`):

```json
{
  "schema": "builderdna.concept.v1",
  "command": "concept.capture",
  "ok": true,
  "action": "created",
  "changed": ["title", "problem"],
  "data": {},
  "stats": {},
  "computed_at": "<ISO8601>"
}
```

On failure: `ok=false`, `error`, `exit_code` (1 unexpected / 2 validation / 3 conflict), optional `details`.

Subcommands: `capture`, `list`, `show`, `move`, `merge`, `score`, `outcome` (`review` is a deprecated alias for `outcome`).

### Domain payloads (in `data` / store)

**ConceptCard** — current snapshot of one concept: identity, aliases, problem, why-now,
source-linked evidence IDs, maturity (evidence status), portfolio stage
(`inbox` / `watch` / `verify` / `build` / `drop`), component scores, smallest experiment
(required before Build), prediction, outcome, lesson.

**ConceptEvidence** — immutable source record: role (`problem` / `implementation` /
`adoption` / `counterevidence`), directness, strength, `independence_key` (groups
reposts/citations of one upstream claim).

**RadarReview** — immutable transition record: reason, expected evidence, review date.

Invariants: evidence is immutable; one current snapshot per concept ID; maturity ≠ stage;
`user_alignment` changes priority only; Build requires two source types, two independent
chains, reviewed counterevidence, and a bounded smallest experiment.

## radar → file / stdout

### RadarRunPayload (`models/radar_payload.py`)

Structured run summary for `radar scan` / `radar review` / `radar source-audit`:

```text
radar, period, run_at,
sources[{source_type, status (complete|partial|unavailable|not_requested), note}],
cards_affected[], summary, gaps[]
```

A partial source failure yields a usable partial run with explicit gaps — it never
silently substitutes another source.

### VerifyPayload (`radar verify`)

Six-gate build-gate report:

```text
concept_id, title, passed, total,
requirements[{name, met, detail}], missing[],
evidence{source_types[], source_type_count, supporting_chains, counterevidence_count},
handoff{imported, skipped_idempotent, conflicts[], attached_evidence_ids[]}?
```

### Experiment export (`radar experiment`)

Exports a reviewable FDE-Gym scenario proposal from a Build-gated card
(`experiments/` — ExperimentProposal + FDE-Gym export). Does not invent product scope.

## investigate → stdout (`builderdna.investigate.v1`)

JSON-first envelope (mirrors concept):

```json
{
  "schema": "builderdna.investigate.v1",
  "command": "investigate.init",
  "ok": true,
  "data": {},
  "computed_at": "<ISO8601>"
}
```

Subcommands: `init`, `run`, `status`, `propose`, `finish`, `resume`.
Exit codes: 0 success, 1 unexpected, 2 validation, 3 conflict.

### Domain payloads

**Investigation** — `id`, topic/subreddit, revision, schema/config fingerprint, budget,
status (`open` / `paused` / `completed` / `failed`), checkpoint, end_reason.

**ActionRecord** — append-only validated action + observation (revision, budget remaining,
allowed next actions).

**EvidenceRecord** — stored evidence item (`SourceHandoffItem`) with stable ID; Reddit
intake flows through `concepts/adapters/reddit.py` into concept evidence when handed off.

**PainClusterCandidate** — single-source discovery artifact (not a `ConceptCard`):
problem_statement, affected_scenarios, evidence_ids (must trace to stored evidence),
time span, workarounds, counterevidence, coverage_limits, open_questions.

## config → stdout (no JSON envelope)

`config --show` prints resolved configuration to the console (output dir + formats).
Not a `SandboxResult`.
