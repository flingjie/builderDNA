---
name: repo-awesome
description: >
  ALWAYS use this skill when the user wants to find repos through community-curated lists,
  awesome lists, or expert recommendations — even if they don't explicitly say "awesome list."
  Mine hand-curated Awesome Lists on GitHub to discover high-quality repositories that human
  curators have vouched for. Use for: mining awesome-* lists for any topic, finding what
  experts recommend in a domain, discovering best-of-class tools from curated collections,
  extracting repos from markdown awesome lists, cross-referencing repos across multiple
  curated lists, and any request involving "curated", "hand-picked", "community-recommended",
  or "best-of" repos. Trigger phrases: "mine awesome lists for X", "awesome list for Y",
  "what do awesome lists recommend for Z", "curated X repos", "awesome X tools",
  "best X repos according to experts", "community-recommended X", "awesome-*",
  "what's in the awesome-X list". Unlike repo-trend (API search for trending repos),
  repo-awesome extracts repos from hand-curated markdown collections — each entry was
  vouched for by a human curator. Uses curation scoring that rewards repos appearing in
  multiple awesome lists. After every run, present a ranked table with curation scores
  and list membership, then ask if they want to deep-dive.
  Pure Claude-orchestrated — uses gh CLI, gh api, and WebSearch as fallback.
---

# repo-awesome Skill

You mine curated Awesome Lists on GitHub to discover quality repositories. You find the best
awesome lists for a topic, fetch their raw markdown, parse repo links, score each repo by
curation consensus, and track everything in the shared state store.

## Architecture

```
User: "mine awesome lists for MCP servers"
       │
       ▼
You (Claude) — find awesome lists, fetch READMEs, parse links, score repos
       │
       ├─► gh search repos "awesome <topic> in:name" → find top lists
       │       │
       │       ▼  2-3 best awesome lists chosen
       │
       ├─► gh api repos/{o}/{r}/readme (raw) → parse markdown for repo links
       │       │
       │       ▼  deduplicated repo list (50-200+ repos per list)
       │
       ├─► gh api repos/{o}/{r} (batch, top ~30) → metadata for scoring
       │       │
       │       ▼  curation scores, stage classification
       │
       ├─► Tier 1: Present ranked table (curation score, list coverage)
       │
       ├─► [on demand] Tier 2 + Tier 3 evaluation (same as repo-trend)
       │
       ├─► output/tracked_repos.json ⟷ persistent state
       └─► state/watches.json ⟷ saved searches
```

## Quick Reference

| User says | You do |
|-----------|--------|
| "mine awesome lists for X" / "awesome X" | Find lists → parse → rank → Tier 1 table |
| "deep dive on #3" | Tier 2 + Tier 3 on specified repo(s) |
| "compare top 3" | Side-by-side Tier 2 checklist for top N |
| "track these" / "watch this search" | Save to `state/watches.json` |
| "what changed?" | Diff from `output/tracked_repos.json` |
| "only lists with > 1000 stars" | Adjust list quality threshold |

---

## 1. Awesome List Discovery

### Step 1: Search for Awesome Lists

Use GitHub search to find awesome lists for the topic:

```
gh search repos "awesome <topic> in:name stars:>50" \
  --sort stars \
  --limit 5 \
  --json fullName,stargazersCount,description,updatedAt,pushedAt,url
```

This finds repos with "awesome" and the topic keyword in the name, sorted by stars.
Example: "awesome mcp server in:name stars:>50" → punkpeye/awesome-mcp-servers, etc.

### Step 2: Select the Best Lists

Pick the top 2-3 lists by stars. Criteria:
- **Stars**: higher = more community validation
- **Recency**: pushed within 6 months (active curation)
- **Relevance**: description matches the user's intent

If the search returns 0 results, broaden:
- Remove `stars:>50`
- Try alternative keywords: `curated <topic> in:name`, `<topic> list in:name stars:>100`
- Use WebSearch: `WebSearch("awesome <topic> github")` to find lists listed on blogs/directories

### Step 3: Clarifying Questions Policy

Ask **at most one** question if the topic is ambiguous:
- "There are 3 MCP awesome lists (91k★, 15k★, 500★). Use the top 2, or all 3?"
- "Should I focus on a specific category within these lists (e.g., only framework repos)?"

---

## 2. Markdown Parsing

### Fetch Raw README

For each selected awesome list:

```
gh api repos/{owner}/{repo}/readme -H 'Accept: application/vnd.github.raw' | head -2000
```

**Always use `head -2000` by default.** Top awesome lists (e.g. punkpeye/awesome-mcp-servers at 91k★) can have READMEs exceeding 500KB. Fetching the full file takes 30+ seconds and consumes excessive tokens — the first 2000 lines contain the vast majority of curated entries.

If a list is small (< 100KB), you can drop the `head` pipe. If all 2000 lines are repo entries, the list is genuinely huge — note to user that only the first ~2000 lines were parsed and some later entries may be missing.

### Known Limitation

Since only the first ~2000 lines are parsed, cross-list deduplication only works within the truncated portion. A repo that appears in list A's lines 1-2000 and list B's lines 3000-5000 will be treated as "list A only." This is acceptable for Tier 1 ranking, as the most important entries are near the top of curated lists.

### Extract Repo Links

Awesome lists use a consistent format for repo entries. Parse these patterns:

**Primary pattern — bullet with GitHub link:**
```
- [Name](https://github.com/owner/repo) - Description
- [owner/repo](https://github.com/owner/repo) — Description with emoji
```

**Extraction rules:**
1. Match lines containing `- [` or `* [` that include `github.com/` in the link
2. Extract: display name, `owner/repo` from the URL, and trailing description
3. Skip: non-GitHub links, table of contents entries, section headers

**Regex guide (Claude uses regex mentally):**
```
Pattern: \[([^\]]+)\]\(https://github\.com/([^/)]+/[^/)]+)\)
```
- Group 1 = display name
- Group 2 = owner/repo (extract from URL path)

### Deduplicate

A repo may appear in multiple awesome lists. Track which lists each repo came from.
This list membership drives the curation score.

### Filter Out Noise

- Skip repos with no stars (raw metadata fetch will confirm)
- Skip archived repos (check during metadata fetch)
- Skip forks unless the fork is more popular than the original
- Skip non-software repos (e.g., "awesome-*" lists themselves, blogs, papers) — unless user wants them

---

## 3. Metadata Fetch

For each unique repo (up to 30 — if more, prioritize repos appearing in multiple lists):

```
gh api repos/{owner}/{repo} --jq '{stargazers_count, forks_count, open_issues_count, subscribers_count, created_at, pushed_at, language, license: .license.spdx_id, description, topics, archived, fork}'
```

This uses the Core API (5,000/hr), not the Search API (30/min). Run these in batches.
30 repos × 1 API call each = 30 calls, well within limits.

---

## 4. Curation Scoring

Rank repos by curation signal, not trending signal. The formula:

```
curation_score = (1 + list_count) * log2(stars + 1)
```

Where:
- `list_count` = number of awesome lists this repo appears in (0 = in 1 list, 1 = in 2 lists, etc.)
- `log2(stars + 1)` = smoothed star signal (prevents a 100k-star repo from dominating)

### Tier 2 Quality Adjustment

Optionally blend in quality signals:

```
adjusted_score = curation_score * (1 + quality_bonus)

quality_bonus = 0
if has_license:      quality_bonus += 0.1
if pushed < 30 days: quality_bonus += 0.2
if topics >= 3:      quality_bonus += 0.1
if contributors >= 5: quality_bonus += 0.1
```

### Lifecycle Stage

Same velocity-based classification as repo-trend:
```
velocity = stars / max(1, days_since_creation)
if   velocity > 80  → accelerating
elif velocity > 50  → emerging
elif velocity > 20  → mainstream
else                → declining
```

### Source Tagging

Label each repo with its source(s):
- `"awesome: list1_name"`, `"awesome: list1_name + list2_name"`
- This distinguishes awesome-mined repos from trend-mined repos in `tracked_repos.json`

---

## 5. Tier 1 Summary Table

| Rank | Repo | Stars | Lists | Curation | Velocity | Stage | Language |
|------|------|-------|-------|----------|----------|-------|----------|
| 1 | owner/repo | 5.2k | 3/3 | 42.5 | 87.3 | 🔥 accel | Python |
| 2 | owner/repo2 | 12k | 2/3 | 35.1 | 23.1 | 📈 emerg | TypeScript |
| ... | ... | ... | ... | ... | ... | ... | ... |

**Lists column**: "2/3" = appears in 2 of the 3 awesome lists mined
**Stage icons**: 🔥 accelerating, 📈 emerging, 📊 mainstream, 📉 declining

### After the Table

"**Deep dive on any of these?** Say a number or repo name. Or 'track these' to save. Or 'show me the full list from [awesome-list-name]' to browse all entries."

---

## 6. Tier 2 + Tier 3 Evaluation

Identical to repo-trend. Read `references/repo-scout/eval.md` for the full scoring rubrics.

### Tier 2 (Full Checklist)
- Fetch detailed metadata, README, contributors
- Score across 7 dimensions (Topic Alignment, README Substance, README Structure, Contributor Diversity, Issue Health, Release Cadence, Stars Growth)
- Compute weighted aggregate score (0-10)

### Tier 3 (Deep Analysis)
- Read README (first 300 lines)
- Assess: clarity, docs, innovation, community, risk, market fit
- Output: Summary, Strengths, Concerns, Audience, Verdict (Consider/Watch/Pass)

### Additional Awesome-Specific Check
When evaluating repos from awesome lists, also note:
- **Curator's description**: what did the awesome list author say about this repo?
- **Category placement**: which section of the list was it in? (e.g., "Frameworks" vs "Tools" vs "Tutorials")
- **Freshness vs. staleness**: awesome lists can contain abandoned repos — cross-check pushed_at

---

## 7. State Management

Uses the same `output/tracked_repos.json` and `state/watches.json` as repo-trend.

### Writing After Mining

For each repo discovered:
1. Create/update entry in `tracked_repos.json`
2. Include `source: "awesome"` and `source_lists: ["list1", "list2"]` in the snapshot
3. Apply the same significant-change thresholds (stars > 10%, curation score > 20%, stage change)

### Cross-Skill Integration

Repos discovered by repo-awesome can be:
- Evaluated by repo-trend's Tier 2/3 flow
- Compared against trend-discovered repos in the same domain
- Tracked together in `tracked_repos.json` — the `source` field distinguishes origin

### Watch Management

Same as repo-trend: "watch this topic" saves the awesome list search to `state/watches.json`.
On re-scan, re-fetch the lists and report new repos, removed repos, and changed repos.

---

## 8. Rate Limits and Error Handling

| API Type | Limit | Usage Pattern |
|----------|-------|---------------|
| Search API | 30/min | 1 call to find awesome lists |
| Core API (readme) | 5,000/hr | 2-3 calls for raw READMEs |
| Core API (repo metadata) | 5,000/hr | ~30 calls for repo details |
| WebSearch | N/A | Fallback only when API search returns nothing |

### Edge Cases

| Situation | Handling |
|-----------|----------|
| README is huge (> 300KB) | Read first 2000 lines, note truncation, parse what's available |
| Repo link is to a non-GitHub domain | Skip — only mine github.com repos |
| Awesome list is empty or poorly formatted | Note to user, skip that list, use the next best one |
| List hasn't been updated in > 1 year | Flag to user: "Note: list X hasn't been updated since YYYY-MM-DD — some repos may be stale" |
| Repo was deleted/renamed since list was created | Skip with a note: "X repos from the list no longer exist" |
| gh api rate limited on metadata batch | Pause, wait for reset, resume. Core API resets hourly. |

---

## 9. Reference Files

Read these when needed:

| File | When to Read | Content |
|------|-------------|---------|
| `references/repo-scout/eval.md` | Before Tier 2 or Tier 3 | Full scoring rubrics |
| `references/repo-scout/state.md` | Before state operations | JSON schema |
| `output/tracked_repos.json` | Start of mining, diff requests | Prior repo data |
| `state/watches.json` | Start of watch operations | Saved watch configs |

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| No awesome lists found | Remove `stars:>50`, try alternative keywords, use WebSearch fallback |
| README too large to parse | Use `head -2000`, note truncation, focus on early sections |
| Too many repos (> 200) | Prioritize repos appearing in multiple lists, cap at 50 for metadata fetch |
| Repo metadata 404 | Repo was deleted/renamed. Skip and note. |
| List has no GitHub repos | Some lists include websites/books/papers only. Tell user and try another list. |
| Parse errors on malformed markdown | Skip malformed lines, report count of successfully parsed vs. skipped |

---

## 11. Conversational Flow

### Mining: 1. Search for awesome lists → 2. Pick top 2-3 → 3. Fetch/parse READMEs → 4. Score repos → 5. Present Tier 1 table → 6. Update `tracked_repos.json` → 7. Ask "Deep dive on any?"
### Deep Dive: Same Tier 2 + Tier 3 flow as repo-trend — reuse `references/repo-scout/eval.md`.
### Cross-Reference: Compare against repos previously discovered by repo-trend in `tracked_repos.json`. Note hotness scores alongside curation scores for any overlap.
