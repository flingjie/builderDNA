# Concept Radar Loop — Orchestration

Authoritative phase → specialist-skill → handoff → completion mapping, sourced from
`radar_cycles/engine.PHASE_SPECS` plus the engine's `_LOCAL_COMPLETION` and
`_completion_command`. Do not invent phases, skills, or handoff names beyond this
table.

## NextAction contract

Every `radar-cycle start / import / decide / status / resume` response embeds
`data.next_action` (or `next_action: null` once the run is finalizable):

```json
{
  "phase": "x-discovery",
  "specialist_skill": "twitter-learning",
  "required_handoff": "x-discovery",
  "budget": null,
  "completion_command": "radar-cycle import <run_id> x-discovery --file output/handoffs/x-discovery.json"
}
```

| field               | meaning                                                                                          |
|---------------------|--------------------------------------------------------------------------------------------------|
| `phase`             | the `PhaseName` to execute next (`validate`, `x-discovery`, `reddit-scan`, `reduce`, `verify`, `decide`, `experiment`, `calibration`, `source-audit`, `report`) |
| `specialist_skill`  | the skill to load to produce the handoff (`""` = local phase)                                    |
| `required_handoff`  | the `source_phase` value the handoff envelope must carry (`null` for local phases)                |
| `budget`            | the configured cap for this phase (reddit scan limit / `daily_card_cap` / `weekly_build_cap`), else `null` |
| `completion_command`| the CLI command to record the phase's completion: `radar-cycle import …` (source phases), `radar-cycle decide …` / `finalize …` (decide/report), or `radar-cycle complete …` (other local phases) |

## Phase table (from `PHASE_SPECS`)

| phase         | specialist_skill      | required_handoff | completion command                                                                                  |
|---------------|-----------------------|------------------|------------------------------------------------------------------------------------------------------|
| validate      | — (local)             | —                | `radar-cycle complete <run_id> validate --json` (after reviewing the resolved config)                |
| x-discovery   | `twitter-learning`    | `x-discovery`    | `radar-cycle import <run_id> x-discovery --file output/handoffs/x-discovery.json`                    |
| reddit-scan   | `reddit-opportunity`  | `reddit-scan`    | `radar-cycle import <run_id> reddit-scan --file output/handoffs/reddit-scan.json`                    |
| reduce        | — (local)             | —                | `radar-cycle complete <run_id> reduce --json` (after `builderdna concept capture`)                   |
| verify        | `repo-trend`          | `verify`         | `radar-cycle import <run_id> verify --file output/handoffs/verify.json`                              |
| decide        | — (local)             | —                | `radar-cycle decide <run_id> --json`                                                                  |
| experiment    | — (local)             | —                | `radar-cycle complete <run_id> experiment --json` (after `radar experiment … --format fde-gym`)      |
| calibration   | — (local)             | —                | `radar-cycle complete <run_id> calibration --json` (after `concept outcome …`)                       |
| source-audit  | `repo-trend`          | `source-audit`   | `radar-cycle import <run_id> source-audit --file output/handoffs/source-audit.json`                  |
| report        | — (local)             | —                | `radar-cycle finalize <run_id> --json`                                                                |

## Mode → phase sequence (from `engine.phase_sequence`)

| mode      | ordered phases                                                                                              |
|-----------|-------------------------------------------------------------------------------------------------------------|
| `daily`   | validate → x-discovery → reddit-scan → reduce → report (**no verify/decide — cannot enter Build**)           |
| `weekly`  | validate → x-discovery → reddit-scan → reduce → verify → decide → experiment* → calibration → report         |
| `monthly` | validate → source-audit → calibration → report                                                               |
| `full`    | validate → x-discovery → reddit-scan → reduce → verify → decide → experiment* → calibration → report         |
| `resume`  | derived from the stored run's mode minus already-completed phases (no fixed sequence)                        |

`* experiment` is the only optional phase: it is required only when `decide`
completed with at least one Build decision (`checkpoint.counts[decide] > 0`).
Otherwise the engine removes it and the run advances straight to
`calibration` / `report`.

## Handoff envelope (from `concepts.handoffs`)

Each source phase produces one `SourceHandoffEnvelope`:

```json
{
  "schema_version": 1,
  "source_phase": "x-discovery",
  "coverage": "partial",
  "coverage_notes": ["X thread replies unavailable"],
  "items": []
}
```

- `schema_version` is pinned to `1`; an unknown version is rejected.
- `source_phase` ∈ {`x-discovery`, `reddit-scan`, `verify`, `source-audit`} — must
  match the phase being imported.
- `coverage` ∈ {`complete`, `partial`, `unavailable`}.
- `coverage_notes` are explicit gap strings (e.g. "comments not read").
- each `items[]` entry carries: `source`, `role`, `author`, `url`, `published_at`,
  `excerpt`, `directness`, `strength`, `upstream_origin`, `independence_key`,
  `topics`, and optional `proposed_concept`.

Source rules applied by normalization (`concepts.handoffs.normalize_handoff`):

- X-learning defaults to a `problem`/discovery role unless it links first-hand
  evidence (a `url` or `upstream_origin`).
- Reddit RSS is L1 and records "comments not read"; it is never community
  consensus / `adoption`.
- GitHub stars/velocity cannot become `adoption` without external-use evidence.
- Paper / official-doc novelty claims require a primary-source `url`.
- Manual inference must remain `directness: inferred`.
