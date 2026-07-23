---
name: repo-trend
description: >
  ALWAYS use this skill when the user wants to find, discover, search for, evaluate, compare,
  or track GitHub repositories — even if they don't explicitly say "trending" or "discover."
  Covers: discovering trending repos in any domain, searching for open-source tools by topic,
  evaluating individual repo quality (deep-dive), comparing repos side-by-side, tracking repos
  over time with watches, checking for new/updated repos since last scan, and any request that
  involves finding or assessing GitHub projects. Trigger phrases include "find me X repos",
  "trending repos in Y", "what's hot in Z", "discover X tools", "evaluate this repo",
  "compare top 3", "which repo is better for X", "I need a tool that does X",
  "track these repos", "check my watches", "what changed since last scan",
  "re-scan my watches", and any mention of repo-trend, repo discovery, or repo scout.
  Uses three-tier evaluation: quick API scan for discovery → full checklist for assessment →
  deep Claude reasoning for strategic recommendations. Pure gh CLI orchestration, no Python.
  After every discovery, present a ranked table with hotness scores and lifecycle stages,
  then ask if the user wants to deep-dive. Important: if the user asks about finding or
  evaluating ANY GitHub repo, use this skill — don't try to search GitHub without it.
---

# repo-trend Skill

You discover, rank, evaluate, and track GitHub repositories. You orchestrate `gh` CLI
calls, compute composite scores, manage persistent state in JSON files, and present
results conversationally. No Python — you are the orchestrator.

## Architecture

```
User: "find me trending AI Agent repos"
       │
       ▼
You (Claude) — parse intent, formulate queries, run gh CLI, compute scores, manage state
       │
       ├─► gh search repos (2 queries: established + emerging)
       │       │
       │       ▼  deduplicated list + hotness scores
       │
       ├─► Tier 1: Present ranked summary table (hotness, stage badges)
       │
       ├─► [on demand] gh api repos/{o}/{r} → topics, metadata
       ├─► [on demand] gh api repos/{o}/{r}/readme → README content
       ├─► [on demand] gh api repos/{o}/{r}/contributors → top contributors
       │
       ├─► Tier 2: Full checklist evaluation (numeric scores)
       ├─► Tier 3: Claude semantic deep analysis (qualitative narrative)
       │
       ├─► output/tracked_repos.json  ⟷  persistent state with diff tracking
       └─► state/watches.json         ⟷  saved search configurations
```

## Quick Reference

| User says | You do |
|-----------|--------|
| "find trending X repos" / "discover X" | Two-query discovery → Tier 1 ranked table |
| "deep dive on #3" / "evaluate owner/repo" | Tier 2 + Tier 3 on specified repo(s) |
| "compare top 3" | Side-by-side Tier 2 checklist for top N |
| "track these" / "watch this search" | Save search to `state/watches.json` |
| "check my watches" / "re-scan watches" | Re-run all active watches, show diffs |
| "what changed?" / "what's new?" | Diff from `output/tracked_repos.json` |
| "only Python" / "stars > 500" / "language: Rust" | Adjust filters, re-run discovery |
| "stop watching X" | Mark watch inactive in `state/watches.json` |

---

## 1. Query Construction

### Translating Natural Language to GitHub Search Syntax

When the user asks to discover repos, construct a GitHub search query from their intent:

1. **Extract the domain/topic** — "AI Agent" → `ai agent`, "Rust CLI tools" → `rust cli`, "MCP servers" → `mcp server`
2. **Apply explicit modifiers if provided** — "Python only" → add `language:python`, "stars > 500" → adjust threshold
3. **Use the keyword form** — join keywords with spaces. GitHub search treats spaces as AND.

### Default Thresholds

Apply these unless the user overrides:

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Min stars | 100 | Liberal — catches emerging repos |
| Recency window | 90 days | Liberal — `pushed:>YYYY-MM-DD` |
| Language | Any | User adds if they care |
| License | Any | Evaluation tier flags missing licenses |
| Max results | 20 per query | Enough for variety, fits in context |

### Clarifying Questions Policy

Ask **at most one** clarifying question before searching, and only when the intent is genuinely ambiguous:

- "Do you mean AI Agent frameworks, or any AI-related repo?"
- "Looking for production-grade (>1000 stars) or emerging projects?"
- "Any language preference?"

If the query is clear ("find me trending MCP server repos"), search immediately.

---

## 2. Discovery Flow (Two-Query Strategy)

### Step 1: Compute Cutoff Date

Calculate `CUTOFF` = today minus 3 months, formatted as `YYYY-MM-DD`.

### Step 2: Run Query A (Established Quality)

```
gh search repos "<keyword query> stars:>100" \
  --sort stars \
  --limit 20 \
  --json createdAt,stargazersCount,language,license,description,fullName,url,updatedAt,pushedAt,forksCount,openIssuesCount,isArchived,isFork,homepage,watchersCount
```

This finds the most-starred repos matching the domain — established quality.

### Step 3: Run Query B (Emerging / Recently Active)

```
gh search repos "<keyword query> pushed:>$CUTOFF stars:>100" \
  --sort updated \
  --limit 20 \
  --json createdAt,stargazersCount,language,license,description,fullName,url,updatedAt,pushedAt,forksCount,openIssuesCount,isArchived,isFork,homepage,watchersCount
```

This finds repos that are actively being worked on — emerging signal.

### Step 4: Merge and Filter

1. Parse both JSON arrays
2. Deduplicate by `fullName` — if a repo appears in both, keep the entry with higher `stargazersCount`
3. Filter out: `isArchived: true`, `isFork: true` (unless user explicitly wants forks)
4. **Quality filter for Query B results**: repos from Query B with stars below the default threshold (100) are noise — drop them. If a Query B repo has < 200 stars, only keep it if its velocity is exceptional (> 30 stars/day) or it appears in both queries.
5. You now have a merged candidate list (up to 40 repos before dedup, typically 15-25 after filtering)

### Step 5: Compute Hotness Scores

For each repo in the merged list:

```
days_since_creation = max(1, (today - createdAt).days)
days_since_push    = max(0, (today - pushedAt).days)

velocity = stargazersCount / days_since_creation
recency  = 1.0 / (1.0 + days_since_push / 90)
hotness  = log2(stargazersCount + 1) * velocity * recency * log2(forksCount + 1)
```

Note: `log2(forksCount + 1)` correctly handles repos with 0 forks — zero forks means zero community engagement multiplier, which is intentional.

### Step 6: Classify Lifecycle Stage

```
if   velocity > 80  → accelerating
elif velocity > 50  → emerging
elif velocity > 20  → mainstream
else                → declining
```

### Step 7: Rank and Present

Sort by `hotness` descending. Read `output/tracked_repos.json` and join any prior evaluation data
(tags, tier scores, verdicts) onto the matching repos.

---

## 3. Tier 1 Summary Table

Present results as a ranked table. Format exactly:

```
| Rank | Repo | Stars | Velocity | Forks | Language | Stage | Hotness | Known? |
|------|------|-------|----------|-------|----------|-------|---------|--------|
| 1 | owner/repo | 5.2k | 87.3 | 420 | Python | 🔥 accelerating | 341.2 | ★ eval'd |
| 2 | owner/repo2 | 12k | 23.1 | 1.8k | TypeScript | 📈 emerging | 198.7 | new |
| 3 | owner/repo3 | 350 | 52.8 | 85 | Rust | 📈 emerging | 156.3 | new |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |
```

**Stage icons**: 🔥 accelerating, 📈 emerging, 📊 mainstream, 📉 declining
**Known column**: "★ eval'd" if prior evaluation exists, "tracked" if seen before, "new" if first discovery

### After the Table

Always follow with: "**Deep dive on any of these?** Say a number, repo name, or 'compare top 3'. Or say 'track these' to save for later."

---

## 4. Tier 2 Full Checklist

When the user asks to deep-dive on specific repos:

### Step 1: Fetch Detailed Metadata

For each repo:
```
gh api repos/{owner}/{repo} --jq '{topics, stargazers_count, forks_count, subscribers_count, open_issues_count, created_at, updated_at, pushed_at, language, license: .license.spdx_id, description, size, archived, fork, homepage, default_branch, has_issues, has_wiki, has_pages, has_discussions}'
```

### Step 2: Fetch README

```
gh api repos/{owner}/{repo}/readme -H 'Accept: application/vnd.github.raw'
```
If README exceeds ~10,000 chars, read the first 300 lines for scoring and note the truncation.

### Step 3: Fetch Contributors

```
gh api repos/{owner}/{repo}/contributors --jq '.[:5] | .[] | {login, contributions}'
```

### Step 4: Score Each Dimension

See `references/repo-scout/eval.md` for the full scoring rubric. Compute each dimension:

| Dimension | Weight | Quick Scoring |
|-----------|--------|---------------|
| Topic Alignment | 15% | Count domain-relevant topics in `.topics` |
| README Substance | 20% | Character count: >2000=1.0, >1000=0.7, >500=0.5, <500=0.1 |
| README Structure | 15% | +0.3 for `## Install`, +0.2 for code examples, +0.2 for API docs |
| Contributor Diversity | 15% | >=5=1.0, >=3=0.7, 1-2=0.3 |
| Issue Health | 15% | `open_issues / (subscribers+1)`: <0.3=1.0, <0.5=0.7, <2.0=0.4 |
| Release Cadence | 10% | Days since push: <7=1.0, <30=0.7, <90=0.4, >90=0.1 |
| Stars Growth | 10% | Compare to `tracked_repos.json`: >20%/month=1.0, >5%=0.5, 0=no history |

### Step 5: Compute Tier 2 Score

```
tier2_score = sum(dimension_score * weight) * 10   # normalized 0-10
```

### Step 6: Present

Show a breakdown table with per-dimension scores and the aggregate, followed by key observations.

---

## 5. Tier 3 Deep Analysis (Claude Semantic Reasoning)

Run after Tier 2 or when the user directly asks for strategic evaluation.

### Process

1. Read the README (focus on first 300 lines; skim rest if needed)
2. Read the detailed metadata from Tier 2
3. Read recent issues if relevant: `gh api repos/{owner}/{repo}/issues --jq '.[:5] | .[] | {title, state, updated_at}'`
4. Apply Claude reasoning across all dimensions in `references/repo-scout/eval.md` Tier 3 section

### AI Agent Domain Specific Checks

When evaluating in the AI Agent space, additionally check for:
- MCP server/client integration
- Multi-agent coordination patterns
- State persistence / checkpointing
- Local LLM support (Ollama, llama.cpp)
- Tool calling / function calling
- Observability (tracing, logging)
- Model agnosticism (multiple LLM providers)

### Output Format

```
## Deep Analysis: owner/repo

**Verdict: Consider / Watch / Pass**

### Summary
2-3 sentence overview.

### Strengths
- Bullet points of what it does well

### Concerns
- Bullet points of risks and red flags

### Who Should Use It
Target audience and use case fit.

### Key Takeaway
One actionable recommendation for the user.
```

---

## 6. State Management

### Reading State

At the start of a discovery session, read `output/tracked_repos.json` to get prior data.
At the start of a watch operation, read `state/watches.json`.

### Writing State After Discovery

After every discovery run, update `output/tracked_repos.json`:

1. For each repo in the current scan:
   - **New** (not in `repos`): create entry with `first_seen` snapshot, empty `history`, `added_at` = now
   - **Existing** (in `repos`): update `last_seen`, and check if a `history` entry is warranted
2. Generate a `scan_id`: `scan_YYYYMMDD_HHMMSS`
3. Update `updated_at` to now
4. Write the full JSON back

### When to Append History

Only append a `history` entry when at least one of these triggers fires:

| Trigger | Threshold |
|---------|-----------|
| Star change | > 10% difference from `last_seen.stars` |
| Hotness change | > 20% difference from `last_seen.hotness` |
| Stage changed | Different from `last_seen.stage` |
| New activity | `pushed_at` is more recent than `last_seen.pushed_at` |

The `change_reason` field: use `stars_grew`, `stars_dropped`, `hotness_changed`, `stage_changed`, `new_activity`, or `re_evaluated`.

### Diff Reporting

When the user asks "what changed?", compute from `tracked_repos.json`:

1. **New since last scan**: repos where `added_at` is after the previous scan's `updated_at`
2. **Changed**: repos with new `history` entries since the user's last check
3. **Stage transitions**: repos where `first_seen.stage` ≠ `last_seen.stage`
4. **Stale warning**: repos where `last_seen.pushed_at` is > 180 days ago

Report as:
```
### What's New
- **3 new repos** discovered: owner/a (Python, 520★), owner/b (Rust, 340★), owner/c (TypeScript, 1.2k★)
- **2 repos changed**: owner/d moved from emerging → accelerating, owner/e gained 45% more stars
- **1 repo stale**: owner/f — last pushed 202 days ago, may be abandoned
```

---

## 7. Watch Management

### Creating a Watch

When the user says "track these" or "watch this search" after a discovery run:

1. Generate a watch ID: `watch_NNN` (find the next unused number)
2. Create the watch config:
   ```json
   {
     "id": "watch_003",
     "label": "<user-friendly name — ask the user or derive from query>",
     "query": "<the original search query without thresholds>",
     "created_at": "<now ISO 8601>",
     "last_run": "<now ISO 8601>",
     "thresholds": { "min_stars": 100, "max_age_days": 90 },
     "language_filter": "",
     "topic_filter": "",
     "status": "active",
     "notes": ""
   }
   ```
3. Append to `state/watches.json` and write

### Running Watches

When the user says "check my watches" or "re-scan":

1. Read `state/watches.json`
2. For each watch with `status: "active"`, run the discovery flow (Section 2) using the watch's query + thresholds
3. Update `last_run` for each executed watch
4. Report diffs as in Section 6

### Deactivating

"stop watching X" → find the watch by `label` or `id`, set `status: "inactive"`, write back.

---

## 8. Rate Limits and Error Handling

### Rate Limit Awareness

| API Type | Limit | Resets |
|----------|-------|--------|
| Search API (`gh search repos`) | 30/min (authenticated) | Every 60 seconds |
| Core API (`gh api`) | 5,000/hr (authenticated) | Hourly |

### Pre-Flight Check

Before the first `gh` call in a session:
```
gh auth status
```
If this returns an error, tell the user to run `gh auth login` and stop.

### During Operations

- Track how many search calls you make. Discovery uses exactly 2 search calls.
- For Tier 2, each repo uses 3 core API calls. 5 repos = 15 calls, well within 5,000/hr.
- If you encounter a 429 or 403 (rate limit), read any error message, wait the suggested time (or 60s for search, until reset for core), then retry once.
- If `gh` returns no results, verify the query syntax isn't the issue. Try a broader query before giving up.
- If a repo 404s (deleted or renamed), skip it silently and remove from tracking.

### Token Budget

- `gh search repos --limit 20` with ~14 JSON fields returns ~5-8KB of JSON. This is fine.
- READMEs can be very large. Read only the first 300 lines for Tier 3. If truncated, note it.
- If the discovery result list exceeds 30 repos after dedup, present only the top 20.

---

## 9. Reference Files

Read these when needed:

| File | When to Read | Content |
|------|-------------|---------|
| `references/repo-scout/eval.md` | Before Tier 2 or Tier 3 evaluation | Full scoring rubrics, AI Agent domain checks |
| `references/repo-scout/state.md` | Before state operations | Complete JSON schema documentation |
| `output/tracked_repos.json` | Start of discovery, diff requests | Prior repo data |
| `state/watches.json` | Start of watch operations | Saved search configs |

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gh: command not found` | Install GitHub CLI: `brew install gh` |
| `gh auth status` fails | Run `gh auth login` |
| No search results | Broaden query: remove `stars:>100`, widen time window, check topic name spelling |
| Too many results / noisy | Narrow query: add language filter, raise star threshold to 500 |
| Rate limited (429) | Wait for rate limit reset (search resets every 60s), retry |
| Repo 404 on detail fetch | Repo was deleted or renamed. Skip it and note to user. |
| README is empty | Some repos have no README. Skip README scoring dimensions. |
| `gh search repos` unknown field | Check field names — they are camelCase: `stargazersCount`, not `stargazers_count` |
| Hotness shows NaN | Check for zero `forksCount` or `days_since_creation` = 0. Use `max(1, value)` guards. |

---

## 11. Conversational Flow

### Discovery Session

```
User: "find me trending AI Agent repos"
You: [No clarifying questions needed — clear intent]
```

1. Run Query A + Query B (Section 2)
2. Merge, filter, compute scores
3. Read `output/tracked_repos.json`
4. Present Tier 1 table
5. Update `output/tracked_repos.json`
6. Ask: "Deep dive on any?"

### Deep Dive Session

```
User: "deep dive on #3 and #5"
You: [Run Tier 2 on specified repos]
```

1. Fetch metadata, README, contributors for both repos
2. Score each dimension
3. Present Tier 2 score breakdown
4. Offer Tier 3: "Want me to do a full semantic analysis on either of these?"
5. Update `evaluation` field in `tracked_repos.json`

### Watch Session

```
User: "track these" or "watch this search"
You: "What should I call this watch?" (if not obvious)
```

1. Create watch entry in `state/watches.json`
2. Confirm: "Saved as 'AI Agent frameworks'. I'll track this. Say 'check my watches' anytime."

### Diff Session

```
User: "what changed?" or "anything new?"
You: [Read tracked_repos.json, compare last_seen timestamps]
```

1. Show new, changed, and stale repos
2. Highlight stage transitions
3. Offer: "Want to deep dive on any of the new ones?"
