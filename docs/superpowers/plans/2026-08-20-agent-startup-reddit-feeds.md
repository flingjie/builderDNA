# Agent Startup Reddit Feed Preset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned `agent-startup` Reddit feed preset and teach `reddit-opportunity` to scan it safely while preserving the existing single-subreddit flow.

**Architecture:** A YAML preset defines 13 categorized feeds and one shared scan policy. `reddit-opportunity` remains the orchestrator: it reads the preset, invokes the existing single-request RSS helper sequentially, filters broad Chinese feeds, maintains the existing per-subreddit state, and aggregates opportunities across segments. The helper and `reddit-outreach` remain unchanged.

**Tech Stack:** Claude Code skill Markdown, YAML parsed by PyYAML 6+, Python 3.11+, pytest 8+, existing stdlib RSS helper `scripts/reddit_rss.py`.

## Global Constraints

- Public Reddit `.rss` only; no Reddit API, `.json` endpoint, scraper, login, comments, scores, votes, or removal data.
- Preserve explicit single-subreddit behavior: `/reddit-opportunity SaaS` must not load a preset.
- Do not silently turn an unspecified invocation into a 13-feed scan; ask the existing single clarification question when the target is ambiguous.
- The versioned preset lives at `config/reddit_feeds/agent-startup.yaml`; runtime history remains in ignored `state/` files.
- The preset contains exactly 13 unique feeds across `agent-builders`, `founders`, `automation-buyers`, and `chinese-market`.
- `scan.sort` is `new`, `scan.limit` is `25`, request spacing is `60` seconds, rate-limit retry delay is `60` seconds, and retry count is `1`.
- Every `language: zh` feed has a non-empty `include_keywords` list; matching is case-insensitive over `title + selftext`, with any-keyword semantics.
- In preset mode, one feed failure does not abort later feeds. In single-subreddit mode, preserve the existing stop-and-report behavior.
- Apply keyword filtering before history append and profile analysis, but advance the per-subreddit cursor from the raw feed's newest post even when filtering yields zero eligible posts.
- Preserve existing per-subreddit files and shapes shared with `reddit-outreach`.
- Do not change `scripts/reddit_rss.py` or `.claude/skills/reddit-outreach/SKILL.md`.
- Do not add scheduling, automatic posting, negative keywords, keyword weights, or non-Reddit sources.

## File Structure

| File | Responsibility |
|---|---|
| `config/reddit_feeds/agent-startup.yaml` | Declarative 13-feed inventory, segmentation, language metadata, keyword filter, and scan policy |
| `tests/test_reddit_feed_presets.py` | Executable contract for preset structure and required orchestration guidance in the skill |
| `.claude/skills/reddit-opportunity/SKILL.md` | Target resolution, preset validation, sequential fetch, filtering, state updates, aggregation, output, and partial-failure behavior |

---

### Task 1: Add the versioned feed preset and schema contract

**Files:**
- Create: `config/reddit_feeds/agent-startup.yaml`
- Create: `tests/test_reddit_feed_presets.py`

**Interfaces:**
- Consumes: PyYAML's `yaml.safe_load()` and the approved feed inventory.
- Produces: a mapping with `name: str`, `description: str`, `scan: dict`, and `feeds: list[dict]`. Task 2 documents how the skill resolves this path; Task 3 consumes the scan and feed fields.

- [ ] **Step 1: Write the failing preset contract tests**

Create `tests/test_reddit_feed_presets.py` with:

```python
from pathlib import Path

import yaml

PRESET_PATH = Path("config/reddit_feeds/agent-startup.yaml")
EXPECTED_FEEDS = {
    "AI_Agents": ("agent-builders", "en"),
    "LangChain": ("agent-builders", "en"),
    "LocalLLaMA": ("agent-builders", "en"),
    "LLMDevs": ("agent-builders", "en"),
    "SaaS": ("founders", "en"),
    "startups": ("founders", "en"),
    "SideProject": ("founders", "en"),
    "indiehackers": ("founders", "en"),
    "microSaaS": ("founders", "en"),
    "automation": ("automation-buyers", "en"),
    "n8n": ("automation-buyers", "en"),
    "smallbusiness": ("automation-buyers", "en"),
    "China_irl": ("chinese-market", "zh"),
}
REQUIRED_ZH_KEYWORDS = {
    "AI Agent",
    "智能体",
    "AI 代理",
    "大模型",
    "自动化",
    "工作流",
    "SaaS",
    "创业",
    "独立开发",
    "获客",
    "降本增效",
}


def load_preset() -> dict:
    return yaml.safe_load(PRESET_PATH.read_text(encoding="utf-8"))


def test_agent_startup_scan_policy():
    preset = load_preset()

    assert preset["name"] == "agent-startup"
    assert preset["description"]
    assert preset["scan"] == {
        "sort": "new",
        "limit": 25,
        "request_interval_seconds": 60,
        "retry_after_rate_limit_seconds": 60,
        "retry_limit": 1,
    }


def test_agent_startup_feed_inventory():
    feeds = load_preset()["feeds"]
    actual = {
        feed["subreddit"]: (feed["segment"], feed["language"])
        for feed in feeds
    }

    assert len(feeds) == 13
    assert len(actual) == len(feeds)
    assert actual == EXPECTED_FEEDS


def test_chinese_feeds_require_keywords():
    chinese_feeds = [
        feed for feed in load_preset()["feeds"] if feed["language"] == "zh"
    ]

    assert chinese_feeds
    for feed in chinese_feeds:
        keywords = feed.get("include_keywords")
        assert isinstance(keywords, list)
        assert keywords

    china_irl = next(
        feed for feed in chinese_feeds if feed["subreddit"] == "China_irl"
    )
    assert set(china_irl["include_keywords"]) == REQUIRED_ZH_KEYWORDS


def test_feed_fields_use_supported_values():
    preset = load_preset()
    assert preset["scan"]["sort"] in {"new", "hot", "top"}
    assert 1 <= preset["scan"]["limit"] <= 25

    for feed in preset["feeds"]:
        assert set(feed) >= {"subreddit", "segment", "language"}
        assert feed["segment"] in {
            "agent-builders",
            "founders",
            "automation-buyers",
            "chinese-market",
        }
        assert feed["language"] in {"en", "zh"}
```

- [ ] **Step 2: Run the tests and verify the preset is missing**

Run:

```bash
uv run pytest tests/test_reddit_feed_presets.py -v
```

Expected: four failures with `FileNotFoundError` for `config/reddit_feeds/agent-startup.yaml`.

- [ ] **Step 3: Create the complete preset**

Create `config/reddit_feeds/agent-startup.yaml` with:

```yaml
name: agent-startup
description: Balanced Agent entrepreneurship opportunity radar

scan:
  sort: new
  limit: 25
  request_interval_seconds: 60
  retry_after_rate_limit_seconds: 60
  retry_limit: 1

feeds:
  - subreddit: AI_Agents
    segment: agent-builders
    language: en

  - subreddit: LangChain
    segment: agent-builders
    language: en

  - subreddit: LocalLLaMA
    segment: agent-builders
    language: en

  - subreddit: LLMDevs
    segment: agent-builders
    language: en

  - subreddit: SaaS
    segment: founders
    language: en

  - subreddit: startups
    segment: founders
    language: en

  - subreddit: SideProject
    segment: founders
    language: en

  - subreddit: indiehackers
    segment: founders
    language: en

  - subreddit: microSaaS
    segment: founders
    language: en

  - subreddit: automation
    segment: automation-buyers
    language: en

  - subreddit: n8n
    segment: automation-buyers
    language: en

  - subreddit: smallbusiness
    segment: automation-buyers
    language: en

  - subreddit: China_irl
    segment: chinese-market
    language: zh
    include_keywords:
      - AI Agent
      - 智能体
      - AI 代理
      - 大模型
      - 自动化
      - 工作流
      - SaaS
      - 创业
      - 独立开发
      - 获客
      - 降本增效
```

- [ ] **Step 4: Run the preset contract tests**

Run:

```bash
uv run pytest tests/test_reddit_feed_presets.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit the preset contract**

```bash
git add config/reddit_feeds/agent-startup.yaml tests/test_reddit_feed_presets.py
git commit -m "feat: add agent startup Reddit feed preset"
```

---

### Task 2: Add preset target resolution to `reddit-opportunity`

**Files:**
- Modify: `.claude/skills/reddit-opportunity/SKILL.md:3-56`
- Modify: `tests/test_reddit_feed_presets.py`

**Interfaces:**
- Consumes: the preset path pattern `config/reddit_feeds/{preset}.yaml` and the specific identifier `agent-startup` from Task 1.
- Produces: deterministic target resolution with two modes: `single` carrying one subreddit, or `preset` carrying the loaded YAML mapping. Task 3 relies on those mode names and precedence rules.

- [ ] **Step 1: Add failing tests for skill discovery and precedence**

Append to `tests/test_reddit_feed_presets.py`:

```python
SKILL_PATH = Path(".claude/skills/reddit-opportunity/SKILL.md")


def test_skill_documents_agent_startup_preset_resolution():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "config/reddit_feeds/{preset}.yaml" in skill
    assert "/reddit-opportunity agent-startup" in skill
    assert "Explicit subreddit wins" in skill
    assert "Do not silently default to a preset" in skill
    assert "single mode" in skill
    assert "preset mode" in skill


def test_skill_frontmatter_mentions_feed_presets():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]

    assert "feed preset" in frontmatter
    assert "Agent startup" in frontmatter
```

- [ ] **Step 2: Run the two new tests and verify they fail**

Run:

```bash
uv run pytest \
  tests/test_reddit_feed_presets.py::test_skill_documents_agent_startup_preset_resolution \
  tests/test_reddit_feed_presets.py::test_skill_frontmatter_mentions_feed_presets \
  -v
```

Expected: two assertion failures because the current skill only documents a single subreddit.

- [ ] **Step 3: Extend the frontmatter trigger description**

In `.claude/skills/reddit-opportunity/SKILL.md`, replace the final part of the frontmatter description:

```yaml
  Shares state with reddit-outreach. RSS returns posts only — no comments, no scores;
  analysis works on post bodies. After every run, present a ranked list of problems and
  ask whether to deep-dive.
```

with:

```yaml
  Supports a single subreddit or a versioned feed preset, including the Agent startup
  opportunity radar. Shares state with reddit-outreach. RSS returns posts only — no
  comments, no scores; analysis works on post bodies. After every run, present a ranked
  list of problems and ask whether to deep-dive.
```

- [ ] **Step 4: Replace the architecture and quick-reference blocks**

Replace `.claude/skills/reddit-opportunity/SKILL.md:24-50` with:

````markdown
## Architecture

```text
User target
   ├─► explicit subreddit ───────────────────────────────► single mode
   └─► config/reddit_feeds/{preset}.yaml ───────────────► preset mode
                                                               │
Claude orchestrator                                             │
   ├─► python3 scripts/reddit_rss.py SUBREDDIT ... ◄───────────┘
   ├─► state/reddit/last_scan.json        ⟷ per-subreddit cursors
   ├─► state/subreddit_profiles/{sub}.md  ⟷ per-subreddit profiles
   ├─► state/reddit/{sub}.jsonl           ⟷ eligible post history
   ├─► per-feed filtering + status
   ├─► cross-segment pain analysis
   └─► output/reddit_opportunities.json
```

The helper remains single-request and single-subreddit. Preset iteration, request spacing,
filtering, state updates, and aggregation happen in this skill.

## Quick Reference

| User says | You do |
|-----------|--------|
| "find problems in r/X" / "what should I build from r/X" | Run single mode for X |
| "/reddit-opportunity agent-startup" / "scan my Agent startup feeds" | Load `config/reddit_feeds/agent-startup.yaml` and run preset mode |
| "deep dive on #1" | Expand one problem into a full product concept + guide outline + landing copy |
| "scan r/X again" / "what changed" | Diff that subreddit vs `last_scan.json`, process only new posts |

---
````

- [ ] **Step 5: Replace target selection with explicit precedence and validation**

Replace `.claude/skills/reddit-opportunity/SKILL.md:53-56` with:

```markdown
## 1. Determine the target mode

Resolve the target in this order:

1. **Explicit subreddit wins.** A user-provided `r/X` or subreddit name selects **single mode**,
   even if a preset also exists.
2. A known preset name such as `agent-startup`, or a request to scan "my Agent startup feeds",
   selects **preset mode** and loads `config/reddit_feeds/{preset}.yaml`.
3. If neither target is identifiable, ask at most one question: "Which subreddit or feed preset?"
   Give `SaaS` and `agent-startup` as examples.
4. Do not silently default to a preset.

Before network access in preset mode, validate:

- top-level `name`, `description`, `scan`, and non-empty `feeds` exist;
- `scan.sort` is `new`, `hot`, or `top`;
- `scan.limit` is an integer from 1 through 25;
- interval and retry values are non-negative integers;
- subreddit names are unique;
- every feed has `subreddit`, `segment`, and `language`;
- every `language: zh` feed has a non-empty `include_keywords` list.

If validation fails, report the exact file and field and stop before the first RSS request.
```

- [ ] **Step 6: Run the target-resolution tests**

Run:

```bash
uv run pytest tests/test_reddit_feed_presets.py -v
```

Expected: `6 passed`.

- [ ] **Step 7: Commit target resolution**

```bash
git add .claude/skills/reddit-opportunity/SKILL.md tests/test_reddit_feed_presets.py
git commit -m "feat: add Reddit feed preset resolution"
```

---

### Task 3: Document multi-feed acquisition, filtering, and resumable state

**Files:**
- Modify: `.claude/skills/reddit-opportunity/SKILL.md:58-90`
- Modify: `tests/test_reddit_feed_presets.py`

**Interfaces:**
- Consumes: validated `scan` and `feeds` mappings from Task 2 and helper exit codes `0`, `1`, `2`, and `3` from `scripts/reddit_rss.py`.
- Produces: eligible posts grouped by subreddit, raw-feed cursors, and one terminal status per feed: `scanned`, `no-new-posts`, `filtered-empty`, `missing/private`, `rate-limited`, or `failed`. Task 4 consumes those posts and statuses.

- [ ] **Step 1: Add failing acquisition-contract tests**

Append to `tests/test_reddit_feed_presets.py`:

```python
def test_skill_documents_multi_feed_acquisition_contract():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    for phrase in (
        "## 2A. Single-subreddit fetch",
        "## 2B. Preset fetch loop",
        "Keyword filtering",
        "title + selftext",
        "raw feed's newest post",
        "request_interval_seconds",
        "retry_after_rate_limit_seconds",
        "retry_limit",
    ):
        assert phrase in skill


def test_skill_documents_every_feed_status():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    for status in (
        "scanned",
        "no-new-posts",
        "filtered-empty",
        "missing/private",
        "rate-limited",
        "failed",
    ):
        assert f"`{status}`" in skill
```

- [ ] **Step 2: Run the new acquisition tests and verify they fail**

Run:

```bash
uv run pytest \
  tests/test_reddit_feed_presets.py::test_skill_documents_multi_feed_acquisition_contract \
  tests/test_reddit_feed_presets.py::test_skill_documents_every_feed_status \
  -v
```

Expected: two assertion failures because the current skill has no preset loop or per-feed statuses.

- [ ] **Step 3: Replace the fetch-and-diff section**

Replace the current `## 2. Fetch posts and diff` section, from that heading through the paragraph ending with `then update last_scan.json.`, with:

````markdown
## 2A. Single-subreddit fetch

Run:

```bash
python3 scripts/reddit_rss.py SUBREDDIT --sort new --limit 25
```

The helper routes through `http://127.0.0.1:7890` by default; use `--proxy ""` for a direct connection.

- Exit 0: parse the JSON array.
- Exit 2 (`rate_limited`): wait about 60 seconds and retry once; on repeat failure, report and stop.
- Exit 3 (`not_found`): report that the subreddit is missing/private and stop.
- Exit 1: report the helper's network, parse, or HTTP error and stop.

Read `state/reddit/last_scan.json`. Posts newer than this subreddit's `newest_post_id` are new;
on first scan all fetched posts are new. Append fetched posts to `state/reddit/{sub}.jsonl`, deduped
by `id`, then update the cursor. Continue with the existing profile and pain-analysis flow.

## 2B. Preset fetch loop

Process feeds sequentially in YAML order. Do not launch parallel helper invocations.
For each feed:

1. Invoke:

   ```bash
   python3 scripts/reddit_rss.py SUBREDDIT --sort SCAN_SORT --limit SCAN_LIMIT
   ```

2. Handle the result without discarding state already written for earlier feeds:
   - Exit 0: parse and diff the feed, then continue below.
   - Exit 2: wait `retry_after_rate_limit_seconds`, retry up to `retry_limit`, then record
     `rate-limited` and continue to the next feed.
   - Exit 3: record `missing/private` and continue.
   - Exit 1 or malformed stdout: record `failed` and continue. Do not append or advance that feed.
3. Read that subreddit's cursor and identify new posts from the raw feed.
4. If there are no new posts, record `no-new-posts`.
5. Apply Keyword filtering when `include_keywords` exists:
   - combine each post's `title + selftext`;
   - compare case-insensitively;
   - retain the post when any keyword is a substring;
   - do not append, profile, or analyze filtered-out posts.
6. Advance `state/reddit/last_scan.json` from the raw feed's newest post, including when all new
   posts were filtered out. This prevents the same irrelevant posts from reappearing.
7. Append eligible posts to `state/reddit/{sub}.jsonl`, deduped by `id`, and update that subreddit's
   profile. Record `filtered-empty` when filtering removes every new post; otherwise record `scanned`.
8. Wait `request_interval_seconds` before the next helper invocation. Do not wait after the final feed.

Keep a run-local scan summary with `subreddit`, `segment`, `language`, `status`, `fetched_count`,
`new_count`, `eligible_count`, and optional `error`. Exactly one terminal status is recorded per feed:
`scanned`, `no-new-posts`, `filtered-empty`, `missing/private`, `rate-limited`, or `failed`.
````

- [ ] **Step 4: Clarify profile updates for filtered and partial feeds**

Immediately after the existing first paragraph under `## 3. Build / update the Subreddit Profile`, add:

```markdown
In preset mode, update a subreddit's profile only from that feed's eligible new posts. Never merge
filtered-out posts or posts from a failed fetch. One feed's profile failure does not erase or replace
profiles already updated earlier in the run.
```

- [ ] **Step 5: Run the acquisition contract tests**

Run:

```bash
uv run pytest tests/test_reddit_feed_presets.py -v
```

Expected: `8 passed`.

- [ ] **Step 6: Commit multi-feed acquisition**

```bash
git add .claude/skills/reddit-opportunity/SKILL.md tests/test_reddit_feed_presets.py
git commit -m "feat: add resumable Reddit preset scans"
```

---

### Task 4: Add cross-segment ranking, preset output, and final status handling

**Files:**
- Modify: `.claude/skills/reddit-opportunity/SKILL.md:92-174`
- Modify: `tests/test_reddit_feed_presets.py`

**Interfaces:**
- Consumes: eligible posts and per-feed statuses from Task 3.
- Produces: cross-segment ranked opportunities plus preset-mode `output/reddit_opportunities.json` containing `preset`, `subreddits`, `scan_summary`, and per-opportunity provenance. Single mode retains the existing `subreddit` output shape.

- [ ] **Step 1: Add failing tests for aggregation and output contracts**

Append to `tests/test_reddit_feed_presets.py`:

```python
def test_skill_documents_cross_segment_ranking():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    for phrase in (
        "Technical recurrence",
        "Commercial recurrence",
        "Buyer recurrence",
        "Cross-segment validation",
        "source_subreddits",
        "source_segments",
    ):
        assert phrase in skill


def test_skill_preserves_single_output_and_adds_preset_output():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert '"subreddit": "SaaS"' in skill
    assert '"preset": "agent-startup"' in skill
    assert '"scan_summary"' in skill
    assert '"subreddits"' in skill
```

- [ ] **Step 2: Run the two new tests and verify they fail**

Run:

```bash
uv run pytest \
  tests/test_reddit_feed_presets.py::test_skill_documents_cross_segment_ranking \
  tests/test_reddit_feed_presets.py::test_skill_preserves_single_output_and_adds_preset_output \
  -v
```

Expected: two assertion failures because only single-community ranking and output are documented.

- [ ] **Step 3: Extend pain analysis with source provenance**

Under `## 4. Pain analysis`, after the existing willingness-to-pay bullet, add:

```markdown
In preset mode, also record `source_subreddits` and `source_segments` for each problem. Normalize
wording only when posts describe the same underlying job or failure; preserve verbatim quotations
and their subreddit provenance.

Use four evidence labels:

- **Technical recurrence** — repeated in `agent-builders`.
- **Commercial recurrence** — repeated in `founders`.
- **Buyer recurrence** — repeated in `automation-buyers` or `chinese-market`.
- **Cross-segment validation** — supported by at least two distinct segments.

Cross-segment validation raises confidence but does not replace explicit or implicit payment evidence.
```

- [ ] **Step 4: Extend ranking without changing the existing base formula**

Replace the paragraph under `## 5. Rank and select` with:

```markdown
Start with `frequency × urgency × willingness_to_pay`. In preset mode, use Cross-segment validation
as supporting evidence when ordering otherwise comparable problems. Do not invent a numeric bonus:
show the contributing subreddits and segments so the user can inspect the evidence. Pick the top
problem as the primary opportunity.
```

- [ ] **Step 5: Replace the output section with explicit single and preset schemas**

Replace `## 7. Write output and present` through its final presentation sentence with:

````markdown
## 7. Write output and present

Write `output/reddit_opportunities.json`.

Single mode preserves the existing shape:

```json
{
  "subreddit": "SaaS",
  "generated_at": "2026-08-20T10:05:00Z",
  "opportunities": [
    {
      "rank": 1,
      "problem": "automating customer onboarding",
      "frequency": 12,
      "pain_level": "high",
      "verbatim_language": ["we keep copy-pasting the same onboarding steps"],
      "tried_solutions": ["Zapier", "manual SOP docs"],
      "why_they_fail": "brittle, not product-specific",
      "willingness_to_pay": "explicit",
      "product_concept": "An onboarding automation assistant for small B2B SaaS teams.",
      "guide_outline": ["Map the current onboarding workflow", "Identify safe automation boundaries"],
      "landing_copy": "Stop copy-pasting every customer onboarding step."
    }
  ]
}
```

Preset mode uses:

```json
{
  "preset": "agent-startup",
  "subreddits": ["AI_Agents", "LangChain", "SaaS", "China_irl"],
  "generated_at": "2026-08-20T10:05:00Z",
  "scan_summary": [
    {
      "subreddit": "AI_Agents",
      "segment": "agent-builders",
      "language": "en",
      "status": "scanned",
      "fetched_count": 25,
      "new_count": 8,
      "eligible_count": 8
    },
    {
      "subreddit": "China_irl",
      "segment": "chinese-market",
      "language": "zh",
      "status": "filtered-empty",
      "fetched_count": 25,
      "new_count": 5,
      "eligible_count": 0
    }
  ],
  "opportunities": [
    {
      "rank": 1,
      "problem": "keeping multi-agent workflows reliable in production",
      "frequency": 9,
      "pain_level": "high",
      "verbatim_language": ["our agents keep losing state between retries"],
      "source_subreddits": ["AI_Agents", "LangChain", "SaaS"],
      "source_segments": ["agent-builders", "founders"],
      "cross_segment_validation": true,
      "tried_solutions": ["custom retry loops", "manual runbooks"],
      "why_they_fail": "recovery logic is duplicated and incomplete",
      "willingness_to_pay": "implicit",
      "product_concept": "A recovery and observability layer for multi-agent workflows.",
      "guide_outline": ["Model workflow state explicitly", "Design idempotent retries"],
      "landing_copy": "Recover failed agent workflows without rebuilding your orchestration stack."
    }
  ]
}
```

The full preset output lists all configured subreddits and one scan-summary row per feed; the shortened
example above demonstrates the shape. Present the scan summary first, then the ranked opportunity
table, then ask: "Deep dive on any of these? Say a number."
````

- [ ] **Step 6: Update state, error handling, and conversational flow**

Add this row to the state-file table:

```markdown
| `config/reddit_feeds/{preset}.yaml` | versioned feed inventory + scan policy; read-only at runtime |
```

Replace `## 10. Error handling` and its table with:

```markdown
## 10. Error handling

| Symptom | Single mode | Preset mode |
|---------|-------------|-------------|
| `rate_limited` (exit 2) | Wait about 60s, retry once, then report and stop | Wait configured delay, retry configured count, record `rate-limited`, continue |
| `not_found` (exit 3) | Report missing/private and stop | Record `missing/private`, continue |
| network / parse / HTTP error | Report and stop | Record `failed`; do not append or advance that feed; continue |
| no new posts | Report and stop | Record `no-new-posts`, continue |
| all new posts filtered | Not applicable | Advance the raw cursor, record `filtered-empty`, continue |
| profile section 5 requested | Explain RSS lacks score/removal data | Same |

A preset run is successful when its configuration is valid and at least one feed completes acquisition,
even if no eligible new posts remain. Report partial failures explicitly; never describe an unscanned
feed as successful.
```

Replace `## 11. Conversational flow` and its paragraph with:

```markdown
## 11. Conversational flow

**Single mode:** determine subreddit → fetch + diff → update profile → analyze pain → rank → generate
concept → write output → present → ask to deep-dive.

**Preset mode:** resolve + validate preset → fetch feeds sequentially → filter + update per-subreddit
state → retain per-feed statuses → aggregate eligible posts → cross-segment analysis → rank → generate
concept → write preset output → present scan summary + opportunities → ask to deep-dive.
```

- [ ] **Step 7: Run all preset contract tests**

Run:

```bash
uv run pytest tests/test_reddit_feed_presets.py -v
```

Expected: `10 passed`.

- [ ] **Step 8: Commit aggregate analysis and output**

```bash
git add .claude/skills/reddit-opportunity/SKILL.md tests/test_reddit_feed_presets.py
git commit -m "feat: aggregate Reddit opportunities across feeds"
```

---

### Task 5: Regression tests and fixture-backed skill walkthrough

**Files:**
- Verify: `config/reddit_feeds/agent-startup.yaml`
- Verify: `.claude/skills/reddit-opportunity/SKILL.md`
- Verify: `tests/test_reddit_feed_presets.py`
- Verify unchanged: `scripts/reddit_rss.py`
- Verify unchanged: `.claude/skills/reddit-outreach/SKILL.md`

**Interfaces:**
- Consumes: all Task 1–4 deliverables.
- Produces: evidence that the preset contract passes, helper behavior is unchanged, filtering/cursor rules are internally consistent, partial failures are visible, and single mode remains documented.

- [ ] **Step 1: Run focused preset and RSS regression tests**

Run:

```bash
uv run pytest tests/test_reddit_feed_presets.py tests/test_reddit_rss.py -v
```

Expected: `18 passed` — 10 preset tests plus the current 8 RSS helper tests.

- [ ] **Step 2: Run the complete project test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected: all tests pass. Record the actual count; do not rely on the older CLAUDE.md count.

- [ ] **Step 3: Confirm protected files were not modified**

Run:

```bash
git diff --exit-code -- scripts/reddit_rss.py .claude/skills/reddit-outreach/SKILL.md
```

Expected: exit 0 with no output.

- [ ] **Step 4: Perform the exact fixture-backed orchestration walkthrough**

Without making network requests, walk the implemented skill instructions with this run-local fixture:

```json
{
  "AI_Agents": {
    "exit": 0,
    "posts": [
      {
        "id": "t3_agent_1",
        "title": "Retries lose state in our production agents",
        "selftext": "We would pay for reliable recovery tooling."
      }
    ]
  },
  "China_irl": {
    "exit": 0,
    "posts": [
      {
        "id": "t3_zh_keep",
        "title": "智能体工作流怎么稳定运行？",
        "selftext": "创业团队现在靠人工重试。"
      },
      {
        "id": "t3_zh_drop",
        "title": "周末去了公园",
        "selftext": "天气不错。"
      }
    ]
  },
  "LangChain": {
    "exit": 2,
    "retry_exit": 2,
    "error": "rate_limited"
  }
}
```

Verify the walkthrough yields exactly:

```text
AI_Agents  -> scanned       -> eligible IDs: t3_agent_1
China_irl  -> scanned       -> eligible IDs: t3_zh_keep
LangChain  -> rate-limited  -> eligible IDs: none
filtered out: t3_zh_drop
cursor advancement: AI_Agents and China_irl only
history append: t3_agent_1 and t3_zh_keep only
scan continues after LangChain's repeated 429
```

Also verify the resulting top problem retains both source subreddit and source segment provenance; do not merge the English and Chinese posts unless the analysis concludes they describe the same underlying production-reliability problem.

- [ ] **Step 5: Smoke-test one real feed only**

Run:

```bash
python3 scripts/reddit_rss.py AI_Agents --sort new --limit 5
```

Expected: either exit 0 with a JSON array containing at most five posts, or the helper's existing structured rate-limit/network error. Do not retry and do not run the full 13-feed preset during verification.

- [ ] **Step 6: Review the final diff for scope**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected:

- no whitespace errors;
- only `config/reddit_feeds/agent-startup.yaml`, `tests/test_reddit_feed_presets.py`, and `.claude/skills/reddit-opportunity/SKILL.md` changed since the implementation base;
- no helper, outreach, scheduler, API, or unrelated documentation changes.

- [ ] **Step 7: Commit any verification-only corrections**

If Steps 1–6 required corrections, commit only those reviewed corrections:

```bash
git add config/reddit_feeds/agent-startup.yaml \
  tests/test_reddit_feed_presets.py \
  .claude/skills/reddit-opportunity/SKILL.md
git commit -m "test: verify Reddit feed preset contract"
```

If no files changed during verification, skip this commit.
