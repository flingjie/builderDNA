---
name: trace-classify
description: Classify raw tool-call traces into structured step-level trace files, and run periodic reviews to surface optimization insights. Works with traces captured by the PostToolUse hook (state/traces/capture.py).
---

# trace-classify

Two-mode skill for execution trace management.

## Mode 1: Classify (default)

Turn a raw trace file (`state/traces/{session_id}.raw.jsonl`) into a structured, human-readable step trace (`state/traces/{skill}_{date}_{suffix}.json`).

### Trigger phrases

- "classify the last trace"
- "classify trace {session_id}"
- "trace this session"
- "what happened in that builderdna run"

### Workflow

#### 1. Find the raw trace

If the user doesn't specify a session ID, read the most recently modified `.raw.jsonl` file in `state/traces/`:

```bash
ls -t state/traces/*.raw.jsonl | head -1
```

#### 2. Detect the skill

Read the raw file. Scan for tool calls that identify the skill:

| Signal | Skill |
|--------|-------|
| `Bash` with `builderdna collect`, `builderdna trend`, etc. | `builderdna` |
| `Bash` with `gh api`, `gh search` + `repo-trend` patterns | `repo-trend` |
| `Bash` with `gh api` + awesome-list URL patterns | `repo-awesome` |

If no recognized skill is detected, report: "This session doesn't contain a recognized skill execution. Raw trace preserved at `state/traces/{session_id}.raw.jsonl`."

#### 3. Classify tool calls into steps

Group contiguous tool calls into logical steps. **For builderdna**, use this taxonomy:

| Step | Detection rule |
|------|---------------|
| `bootstrap` | `Read` calls on `state/hypotheses.json`, `state/user_weights.json`, `state/user_dna.json` at session start |
| `goal_determination` | Period between bootstrap and first CLI command (often no tool calls — mark as pure reasoning) |
| `collect` | `Bash` containing `builderdna collect` |
| `trend` | `Bash` containing `builderdna trend` |
| `short_circuit` | `Read` on `output/trends.json` + optional user question about skipping |
| `pain` | `Bash` containing `builderdna pain` |
| `opportunity` | `Bash` containing `builderdna opportunity` |
| `report` | `Bash` containing `builderdna report` |
| `observability` | `Bash` containing `builderdna observability` OR `Skill` invocation of `observability` |
| `interpretation` | `Read` calls on `output/*.json` after report generation |
| `hypothesis_update` | `Read`/`Edit`/`Write` on `state/hypotheses.json` at end of session |

Rules:
- Each step starts at the `ts` of its first tool call and ends at the `ts` of its last tool call.
- A step with no tool calls (goal_determination) gets `started_at` from the previous step's end and `ended_at` from the next step's start.
- Tool calls between two recognized steps that don't fit any pattern are absorbed into the nearest preceding step.
- Mark `status` as `"success"` unless a tool call has an error exit code or the result contains traceback/error.
- Mark step as `"skipped"` if the expected tool call is absent (e.g., no pain step because short-circuit triggered).

#### 4. Generate output_summary for each step

**For CLI steps** (collect, trend, pain, opportunity, report):
- Parse the `tool_result` field. The stdout is a `SandboxResult` JSON with `stats` and `payload`.
- Extract key metrics:
  - **collect**: total repos, total issues, topic count, top 3 topics by count, zero-产出 topics, API calls, cache hits
  - **trend**: trend count, top velocity topic + score, gap_score range
  - **pain**: cluster count, total issues clustered, noise count
  - **opportunity**: opportunity card count, top card + gap_score
  - **report**: output format, file size or line count
- If the SandboxResult can't be parsed, summarize the first/last ~200 chars of stdout instead.

**For non-CLI steps** (bootstrap, short_circuit, interpretation):
- Infer from the tool calls: what files were read, what decisions were made.
- Keep it 1-2 sentences.

**Zero-产出 detection** (acceptance criterion):
- For the `collect` step, always include: `"Zero-yield topics: [topic1, topic2, ...]"` if any topic produced 0 repos.
- This is the key data point for the weekly review.

#### 5. Write the structured trace

Write to `state/traces/{skill}_{YYYY-MM-DD}_{session_suffix}.json`:

```json
{
  "skill": "builderdna",
  "session_id": "abc123",
  "classified_at": "2026-08-10T15:00:00Z",
  "started_at": "2026-08-10T14:30:00Z",
  "ended_at": "2026-08-10T14:32:15Z",
  "total_duration_ms": 135000,
  "steps": [
    {
      "name": "collect",
      "started_at": "2026-08-10T14:30:05Z",
      "ended_at": "2026-08-10T14:30:50Z",
      "duration_ms": 45000,
      "status": "success",
      "tool_count": 1,
      "output_summary": "150 repos + 45 issues across 12 topics. Top: langchain(30), llama-index(25), autogen(18). Zero-yield: crewai, taskweaver. API: 12 calls, cache: 3 hits (20%)."
    }
  ],
  "summary": {
    "total_steps": 8,
    "steps_run": 6,
    "steps_skipped": 2,
    "errors": 0,
    "warnings": 0
  }
}
```

#### 6. Report to user

Present a compact table of steps:

```
builderdna trace | session abc123 | 2m15s total

  bootstrap        2.3s   ✓  3 state files loaded
  goal_determination  1.2s  ✓  opportunity_discovery mode
  collect         45.0s   ✓  150 repos, 12 topics, crewai/taskweaver = 0
  trend            1.2s   ✓  8 trends, top: multi-agent (0.85)
  short_circuit    0.8s   →  gap_score ≥ 1.0, proceeding
  pain             8.5s   ✓  3 clusters, 42 issues
  opportunity      0.3s   ✓  8 cards, top: "Agent Observability" (gap=2.1)
  report           0.2s   ✓  markdown, 4.2KB
  interpretation   2.1s   ✓  3 files read, 2 hypotheses updated
  observability     —     skipped
```

Then ask: "Save this trace? (y/n)" — wait for confirmation before writing.

---

## Mode 2: Review

Scan all classified trace files and surface optimization insights.

### Trigger phrases

- "review this week's traces"
- "trace review"
- "how are my builderdna runs doing"
- "any optimization opportunities from traces"

### Workflow

#### 1. Gather traces

List all classified trace files for the requested time range (default: last 7 days):

```bash
ls -t state/traces/builderdna_*.json | head -20
```

#### 2. Read and analyze

Read each trace file. Extract and compare:

| Dimension | What to look for |
|-----------|-----------------|
| **Duration trends** | Is each run getting faster or slower? Which step dominates? |
| **Zero-yield topics** | Which topics consistently produce 0 repos across multiple runs? |
| **Skipped steps** | Is short-circuit triggering often? Are pain/opportunity usually skipped? |
| **Error patterns** | Which steps fail most? Any correlated failures? |
| **API efficiency** | Cache hit rate trending up or down? API call count stable? |

#### 3. Present findings

Format as a report with three sections:

**1. Efficiency Hotspots**
- List the top 3 slowest steps (by average duration across runs) with recommendations.

**2. Redundancy Alerts**
- List zero-yield topics that appear in ≥2 runs — suggest removal from config.
- List steps that were skipped in ≥50% of runs — consider making them explicitly optional.

**3. Trend Lines**
- Week-over-week: avg total duration, avg API calls, cache hit rate.

#### 4. Suggest actions

For each finding, propose a concrete action:
- "Remove `crewai` and `taskweaver` from topics in config.yaml — zero yield in 3/3 runs"
- "pain step averages 8.5s but was skipped in 2/5 runs — consider adding earlier short-circuit criteria"
- "Avg duration increased 30% vs last week — check if rate limiting is more aggressive"

Ask the user which actions to apply.

---

## Fallback: manual trace reading

If the user just wants to see a raw trace without classification:

```bash
cat state/traces/{session_id}.raw.jsonl | python3 -m json.tool
```

Or for a quick overview of tool calls in a session:

```bash
cat state/traces/{session_id}.raw.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    e = json.loads(line)
    print(f'{e[\"ts\"][:19]}  {e[\"tool\"]:12s}  {str(e.get(\"input\",\"\"))[:100]}')
"
```
