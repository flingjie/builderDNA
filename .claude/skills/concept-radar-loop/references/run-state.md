# Concept Radar Loop — Run State

Everything the loop persists lives under `state/` (canonical state) and `output/`
(presentation). The Python engine owns every write; the skill never edits these
files directly.

## On-disk layout

| path                              | contents                                                                                                   | owner                                   |
|-----------------------------------|------------------------------------------------------------------------------------------------------------|-----------------------------------------|
| `state/radar_cycles/{run-id}.json`| one checkpoint per run: serialized `RadarCycleRun` + `outputs`, `coverage`, `run_status`                    | `radar_cycles/checkpoint.py`            |
| `state/concepts.jsonl`            | one current snapshot per concept ID (atomic rewrite on upsert)                                              | `concepts/store.py`                     |
| `state/concept_evidence.jsonl`    | append-only `ConceptEvidence` records (idempotent replay; conflict on same-ID/different-payload)             | `concepts/store.py`                     |
| `state/radar_reviews.jsonl`       | append-only `RadarReview` records                                                                           | `concepts/store.py`                     |
| `output/handoffs/{phase}.json`    | handoff files the skill writes before `import` (the default `completion_command` path)                      | the skill                               |
| `output/radar_cycles/{run-id}.json` | canonical JSON cycle report                                                                               | `radar_cycles/rendering.write_report`   |
| `output/radar_cycles/{run-id}.md` | Markdown report rendered from the JSON (presentation only)                                                  | `radar_cycles/rendering.write_report`   |

## Checkpoint contents

`state/radar_cycles/{run-id}.json` holds the `RadarCycleRun` (id, radar, mode,
checkpoint) plus three checkpoint-only top-level keys:

- `checkpoint.config_fingerprint` — SHA-256 of the resolved radar config,
  including the referenced Reddit preset.
- `checkpoint.phases` — per-phase status
  (`pending | running | completed | partial | blocked | failed`).
- `checkpoint.counts` — per-phase counts (evidence imported, build decisions).
- `checkpoint.errors` — error strings recorded during the run.
- `outputs` — `{phase: [path, ...]}` completed output paths, preserved across resume.
- `coverage` — `SourceCoverage[]` (source type, status, note).
- `run_status` — `"running"` or `"completed"`.

Phase transitions are strict (`radar_cycles/models.PhaseCheckpoint.ALLOWED_TRANSITIONS`):

```text
pending → running
running → completed | partial | blocked | failed
partial | failed → running     # one read-only retry only
blocked → running              # only after changed input / user direction
completed → (never again)
```

All writes are atomic (same-directory temp file + `fsync` + `os.replace`), so an
interrupted write never truncates a valid checkpoint. Multi-host / multi-process
writers are unsupported; run one writer process per store directory.

## Resume: config-fingerprint fail-closed

`builderdna radar-cycle resume <run_id> --json` recomputes the current radar config
fingerprint (`radar_cycles/config.fingerprint`) and compares it to
`checkpoint.config_fingerprint`. On any difference — in the radar YAML or in the
referenced Reddit preset — the command fails closed:

```text
exit code 2, ok: false
error: "config fingerprint changed since start; refusing to resume ..."
```

It refuses to silently continue an in-progress run under different configuration.
The run is not deleted; either revert the config change or start a fresh run before
resuming.
