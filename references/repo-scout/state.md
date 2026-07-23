# Repo Scout State Schema

Documents the JSON schemas for `output/tracked_repos.json` and `state/watches.json`.
Both files are human-readable JSON (not binary) to support inspection and git diff.
Used by `repo-trend` and any future skill that tracks repos across sessions.

---

## output/tracked_repos.json

Tracks every repo discovered across all discovery sessions. Used for diff reporting
and trend analysis. Stored in the gitignored `output/` directory (local state, not committed).

### Full Schema

```json
{
  "version": 1,
  "updated_at": "2026-07-23T12:00:00Z",
  "repos": {
    "owner/repo": {
      "full_name": "owner/repo",
      "added_at": "2026-07-20T10:00:00Z",
      "first_seen": {
        "stars": 5000,
        "forks": 300,
        "open_issues": 45,
        "subscribers": 80,
        "pushed_at": "2026-07-19T15:00:00Z",
        "hotness": 245.6,
        "velocity": 45.2,
        "stage": "emerging",
        "language": "Python",
        "description": "A thing that does stuff",
        "license": "MIT"
      },
      "last_seen": {
        "stars": 5200,
        "forks": 310,
        "open_issues": 42,
        "subscribers": 85,
        "pushed_at": "2026-07-22T20:00:00Z",
        "hotness": 280.1,
        "velocity": 47.8,
        "stage": "accelerating",
        "language": "Python",
        "description": "A thing that does stuff",
        "license": "MIT"
      },
      "history": [
        {
          "checked_at": "2026-07-21T10:00:00Z",
          "scan_id": "scan_20260721_100000",
          "stars": 5100,
          "hotness": 260.4,
          "velocity": 46.5,
          "stage": "emerging",
          "pushed_at": "2026-07-20T18:00:00Z",
          "change_reason": "stars_grew"
        }
      ],
      "evaluation": {
        "tier": 2,
        "last_eval_at": "2026-07-21T10:05:00Z",
        "tier2_score": 7.5,
        "tier3_verdict": "Consider",
        "tier3_notes": "Strong community, clear documentation, first-mover advantage.",
        "tags": ["agent", "framework", "python"]
      },
      "watch": {
        "active": true,
        "watch_id": "watch_001",
        "source_search": "AI agent framework"
      }
    }
  }
}
```

### Field Reference

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `version` | integer | yes | Schema version, currently 1 |
| `updated_at` | ISO 8601 | yes | Last write timestamp |
| `repos` | object | yes | Keyed by `owner/repo` full name |
| `repos.*.full_name` | string | yes | Duplicate of key for convenience |
| `repos.*.added_at` | ISO 8601 | yes | When first discovered |
| `repos.*.first_seen` | snapshot | yes | Initial observation (see snapshot fields below) |
| `repos.*.last_seen` | snapshot | yes | Most recent observation |
| `repos.*.history[]` | array | yes | Significant changes only (may be empty) |
| `repos.*.evaluation` | object | no | Present only if Tier 2+ evaluation was run |
| `repos.*.watch` | object | no | Present only if repo is being actively watched |

### Snapshot Fields (first_seen / last_seen / history entries)

| Field | Type | Notes |
|-------|------|-------|
| `stars` | integer | Current star count |
| `forks` | integer | Current fork count |
| `open_issues` | integer | Open issue count |
| `subscribers` | integer | Watcher/subscriber count |
| `pushed_at` | ISO 8601 | Last push timestamp |
| `hotness` | float | Composite hotness score |
| `velocity` | float | Stars per day |
| `stage` | string | `accelerating`, `emerging`, `mainstream`, or `declining` |
| `language` | string | Primary language |
| `description` | string | Repo description |
| `license` | string | SPDX identifier (e.g., "MIT") |

### History Entry Additional Fields

| Field | Type | Notes |
|-------|------|-------|
| `checked_at` | ISO 8601 | When this snapshot was taken |
| `scan_id` | string | Identifier for the scan that produced this entry |
| `change_reason` | string | One of: `stars_grew`, `stars_dropped`, `hotness_changed`, `stage_changed`, `new_activity`, `re_evaluated` |

### Significant Change Thresholds

A `history` entry is appended ONLY when at least one of these conditions is met:

| Trigger | Threshold |
|---------|-----------|
| Star count change | > 10% since last recorded value |
| Hotness change | > 20% since last recorded value |
| Stage change | Classification changed (e.g., emerging → accelerating) |
| New activity | `pushed_at` is newer than previously recorded value |

### Diff Reporting

When the user asks "what changed?", compute:

1. **New repos**: present in scan but not in `repos` → list with hotness
2. **Changed repos**: new history entries since last scan → list with before/after
3. **Stale repos**: `last_seen.pushed_at` > 180 days ago → flag as potentially abandoned
4. **Stage transitions**: repos that moved between lifecycle stages → highlight

Report format: conversational summary with counts, then key highlights.

---

## state/watches.json

Saved search configurations for repeat execution. Stored in `state/` (tracked by git).

### Full Schema

```json
{
  "version": 1,
  "watches": [
    {
      "id": "watch_001",
      "label": "AI Agent repos",
      "query": "ai agent stars:>100",
      "created_at": "2026-07-20T10:00:00Z",
      "last_run": "2026-07-23T12:00:00Z",
      "thresholds": {
        "min_stars": 100,
        "max_age_days": 90
      },
      "language_filter": "",
      "topic_filter": "",
      "status": "active",
      "notes": "Monitoring the agent framework space"
    }
  ]
}
```

### Field Reference

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `version` | integer | yes | Schema version |
| `watches[]` | array | yes | List of watch configs |
| `watches[].id` | string | yes | Unique, `watch_NNN` format |
| `watches[].label` | string | yes | Human-readable name |
| `watches[].query` | string | yes | GitHub search query string (without thresholds) |
| `watches[].created_at` | ISO 8601 | yes | When watch was created |
| `watches[].last_run` | ISO 8601 | yes | Last time this watch was scanned |
| `watches[].thresholds.min_stars` | integer | yes | Minimum star filter |
| `watches[].thresholds.max_age_days` | integer | yes | Maximum push age in days |
| `watches[].language_filter` | string | no | Language constraint (e.g., "Python"), empty = any |
| `watches[].topic_filter` | string | no | Topic constraint (e.g., "mcp"), empty = any |
| `watches[].status` | string | yes | `"active"` or `"inactive"` |
| `watches[].notes` | string | no | Free-form user notes |
