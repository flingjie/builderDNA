---
name: concept-radar-loop
description: >
  Resumable, command-driven orchestrator for the cross-source concept radar loop.
  Use when the user wants to run an end-to-end radar cycle over a configured radar
  ("run the concept radar loop", "使用 concept-radar-loop", "自动跑一遍 … 概念雷达",
  "resume my radar run", "继续跑概念雷达", "概念雷达循环"), or asks to start, resume,
  import, decide, or finalize a radar-cycle run. Drives the deterministic
  `builderdna radar-cycle` state machine (start → import source handoffs → decide →
  finalize), loading only the specialist skill each NextAction names
  (twitter-learning / reddit-opportunity / repo-trend). Single-source requests do
  NOT enter the loop — route them to the specialist skill; recurring-schedule
  requests route to automation. This skill never schedules future runs (no
  cron/daemon).
---

# Concept Radar Loop

You are the orchestrator that runs **one radar cycle** end-to-end by driving the
deterministic `builderdna radar-cycle` state machine. You never invent persistence
or checkpoints: the Python CLI owns every state transition, every hard gate, and
every idempotency rule. You own retrieval (via the specialist skills) and semantic
reduction (paraphrasing source records into validated handoff JSON).

Every command below runs as `PYTHONPATH=. uv run builderdna <command> …` (the
`PYTHONPATH=.` prefix is the project convention from `CLAUDE.md`; plain
`uv run builderdna …` also resolves).

## The loop (7 steps)

1. **Start.**
   `builderdna radar-cycle start --radar <name> --mode full --json`
   (`--mode` is one of `daily | weekly | monthly | full`). The JSON response
   carries `data.run_id` and `data.next_action`.

2. **Read `next_action`.** Its fields are `phase`, `specialist_skill`,
   `required_handoff`, `budget`, `completion_command`. It is the engine's
   instruction for what to do next — never re-derive it yourself.

3. **Load only that specialist skill.** When `specialist_skill` is non-empty,
   load exactly that skill and no other:
   - `twitter-learning` → produces the `x-discovery` handoff
   - `reddit-opportunity` → produces the `reddit-scan` handoff
   - `repo-trend` → produces the `verify` and `source-audit` handoffs
   When `specialist_skill` is `""`, this is a local phase — perform it yourself
   (see "Local phases").

4. **Produce the required handoff JSON.** Write a file matching
   `concepts.handoffs.SourceHandoffEnvelope` (`schema_version: 1`, `source_phase`,
   `coverage`, `coverage_notes`, `items[]`). The envelope's `source_phase` must
   equal the NextAction's `required_handoff`. Default location:
   `output/handoffs/<phase>.json`.

5. **Import.**
   `builderdna radar-cycle import <run_id> <phase> --file <path> --json`.
   The engine validates the envelope atomically (one structurally invalid item
   rejects the whole handoff with no partial writes), imports records
   idempotently, completes the phase, and returns the next `next_action` in
   `data.next_action`.

6. **Repeat** steps 2–5 until the loop reaches `decide` and then `report`.

7. **Present.** Run `builderdna radar-cycle finalize <run_id> --json`, then report
   the run ID plus `data.json_path` / `data.md_path` and stop.

## Local phases

When `next_action.specialist_skill` is `""`, the phase produces no source handoff.
Handle it directly using the real commands the engine's `completion_command` names:

| phase          | what you do                                                                                              |
|----------------|----------------------------------------------------------------------------------------------------------|
| `validate`     | review the resolved radar config against the run fingerprint, then `radar-cycle complete <run_id> validate --json` |
| `reduce`       | reduce imported evidence into concept cards via `builderdna concept capture`, then `radar-cycle complete <run_id> reduce --json` |
| `verify`       | (source phase — see loop; produces a `verify` handoff via `repo-trend`, then `import`)                    |
| `decide`       | run `builderdna radar-cycle decide <run_id> --json`                                                       |
| `experiment`   | `builderdna radar experiment <CONCEPT_ID> --format fde-gym`, then `radar-cycle complete <run_id> experiment --json` |
| `calibration`  | reconcile stored predictions against outcomes via `builderdna concept outcome <ID> --outcome … --lesson …`, then `radar-cycle complete <run_id> calibration --json` |
| `report`       | run `builderdna radar-cycle finalize <run_id> --json`, then present + stop                                 |

Note: `import` completes source phases; `decide` completes `decide`;
`finalize` completes `report`. Local phases (`validate`, `reduce`, `experiment`,
`calibration`) are completed with `builderdna radar-cycle complete <run_id>
<phase> --json`, which marks the phase done and returns the next `next_action`
in the same call.

## Resume

To continue an interrupted run:
`builderdna radar-cycle resume <run_id> --json`. It re-checks the config
fingerprint and returns the first incomplete phase (`data.next_action`). It fails
closed (non-zero exit, `ok: false`) if the radar config or its referenced Reddit
preset changed since `start`.

## Stopping conditions

Stop and surface the problem — do not fabricate evidence, do not auto-fix — when:

- **Authentication failure** — a specialist skill cannot authenticate to X, GitHub,
  or Reddit. Record that source as `coverage: unavailable` (or `partial`) with
  `coverage_notes`, never substitute another source for it.
- **Invalid or corrupt state** — any `radar-cycle` command returns `ok: false` for
  a missing/invalid radar config, an invalid handoff envelope, a corrupt store, or
  a mismatched phase / changed fingerprint. Read the JSON `error` and `exit_code`
  and stop rather than retrying blindly.
- **Ambiguous merge** — `builderdna concept capture` reports an ambiguous match
  (non-zero exit, `ok: false`, candidates listed). Never auto-merge: ask the user
  to disambiguate with `--into <ID>` or an explicit
  `builderdna concept merge <keep_id> <merged_id>` decision. A `suggested` match is
  never merged automatically.
- **External platform mutations** — never post, reply, push, open PRs, or write to
  FDE-Gym or any external repository. The loop is read-only against platforms and
  write-only against local `state/` and `output/`.

## No self-scheduling

This skill runs once per invocation. It does **not** schedule future runs — no
cron, no launchd, no daemon, no background watcher. A recurring radar loop is a
platform scheduler's job: if the user asks for a recurring schedule, point them at
their scheduler and do not claim the skill can self-schedule.

## Reference files

- `references/orchestration.md` — mode → phase → specialist skill → required handoff → completion command
- `references/run-state.md` — what lives on disk and the resume fingerprint rule
