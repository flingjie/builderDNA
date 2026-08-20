# Agent Startup Reddit Feed Preset

**Date:** 2026-08-20
**Status:** approved design, pending written-spec review
**Scope:** one versioned feed preset plus multi-subreddit orchestration in `reddit-opportunity`

## Goal

Give an Agent entrepreneur a reusable, balanced Reddit opportunity radar. The preset must combine:

1. Agent-development communities for engineering and production pain.
2. Founder communities for willingness-to-pay, validation, pricing, and customer-acquisition signals.
3. Automation and small-business communities for problems expressed by potential buyers rather than only by Agent builders.
4. A small Chinese-language signal lane, filtered aggressively because Reddit has no high-activity Chinese Agent-startup vertical comparable to its English communities.

The preset extends the existing on-demand workflow. It does not add a scheduler, Reddit API client, scraper, comment ingestion, or automatic posting.

## Confirmed Decisions

1. **Focus:** Agent entrepreneurship rather than only Agent framework engineering.
2. **Coverage:** balanced, approximately 10–14 communities.
3. **Language:** English-first with a filtered Chinese supplement.
4. **Configuration:** a version-controlled preset, not ignored local state and not a hard-coded list inside `SKILL.md`.
5. **Compatibility:** explicit single-subreddit requests keep the current behavior.
6. **Acquisition:** public Reddit RSS only; comments, scores, and removal data remain unavailable.

## Why a Layered Feed Set

A feed composed only of Agent-development communities overweights framework comparisons, product launches, and builders talking to other builders. It can identify supply-side pain but is weak evidence of a market.

The preset therefore separates three kinds of evidence:

| Segment | Question answered |
|---|---|
| Agent builders | What is technically painful or unreliable? |
| Founders | What do builders struggle to validate, sell, price, and operate? |
| Potential buyers | What repetitive business work is painful enough to seek help for? |

Chinese Reddit coverage is a supplementary discovery lane, not an equal fourth market sample. Broad Chinese communities are admitted only through explicit keyword filtering.

## Versioned Preset

Create:

```text
config/reddit_feeds/agent-startup.yaml
```

Proposed schema:

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

### Schema rules

- `name` is a stable, lowercase preset identifier.
- `scan.sort` must be one of `new`, `hot`, or `top`.
- `scan.limit` must be a positive integer and is capped at 25 for this preset.
- `request_interval_seconds` applies between helper invocations, not before the first request.
- `retry_limit` is one; repeated failures are recorded and skipped.
- Every feed requires a unique `subreddit`, `segment`, and `language`.
- `include_keywords` is optional for English feeds. Every `language: zh` feed must define a non-empty keyword list because the selected Chinese communities are broad rather than Agent-specific.
- Keyword matching is case-insensitive over `title + selftext`; Chinese strings use normal substring matching.
- A post matching any configured keyword is eligible. No keyword must match when a feed has no filter.

The 60-second interval follows the existing RSS-only design constraint and avoids turning a 13-feed scan into a burst of requests. A live validation burst returned one successful feed followed by `429` responses, confirming that a five-second interval is not a safe default.

## Feed Inventory

### Agent builders

| Subreddit | Primary signal |
|---|---|
| `AI_Agents` | Agent frameworks, production systems, commercialization |
| `LangChain` | Orchestration, LangGraph, state, integrations |
| `LocalLLaMA` | Inference cost, privacy, self-hosting, model constraints |
| `LLMDevs` | LLM application engineering and operations |

### Founders

| Subreddit | Primary signal |
|---|---|
| `SaaS` | Pricing, acquisition, retention, B2B willingness to pay |
| `startups` | Validation, market selection, operations, fundraising |
| `SideProject` | Early launches, feedback, failed experiments |
| `indiehackers` | Bootstrapping, revenue, distribution, solo-team constraints |
| `microSaaS` | Narrow products and small-team opportunities |

### Automation users and buyers

| Subreddit | Primary signal |
|---|---|
| `automation` | Repetitive workflows and integration demand |
| `n8n` | Workflow automation, Agent integrations, self-hosting |
| `smallbusiness` | Non-technical operational pain and purchasing context |

### Filtered Chinese supplement

| Subreddit | Primary signal | Filter requirement |
|---|---|---|
| `China_irl` | Chinese-language discussion that occasionally surfaces AI, entrepreneurship, and automation needs | Must match at least one configured keyword |

Total: **13 feeds**.

## Invocation and Precedence

The skill supports two modes:

```text
/reddit-opportunity SaaS
/reddit-opportunity agent-startup
```

Precedence rules:

1. If the user explicitly names a subreddit, run the existing single-subreddit flow.
2. If the user names `agent-startup` or asks to scan their Agent-startup feeds, load the preset.
3. If neither a subreddit nor a preset is identifiable, ask the existing single clarification question.
4. Do not silently turn every `reddit-opportunity` invocation into a 13-feed scan.

## Multi-Feed Data Flow

For a preset scan:

1. Read and validate the preset before making network requests.
2. Iterate feeds in configuration order.
3. Invoke the existing helper once per feed:

   ```bash
   python3 scripts/reddit_rss.py SUBREDDIT --sort SORT --limit LIMIT
   ```

4. Compare the raw feed with `state/reddit/last_scan.json` and identify new posts.
5. For filtered feeds, apply `include_keywords` to new posts before analysis or history append.
6. Append eligible posts to `state/reddit/{subreddit}.jsonl`, deduplicated by post ID.
7. Update the per-subreddit profile from eligible posts.
8. Update the scan cursor from the raw feed's newest post even when all new posts were filtered out. This prevents repeatedly processing irrelevant posts.
9. Wait the configured interval before the next feed.
10. After all feeds finish, aggregate eligible new posts across communities and run the normal problem-ranking and product-concept flow.

Existing per-subreddit profile, post history, and cursor formats remain unchanged and stay compatible with `reddit-outreach`.

## Cross-Community Ranking

A recurring problem is stronger when it appears in more than one segment. The aggregate analysis should retain source provenance and distinguish:

- **Technical recurrence:** repeated inside Agent-builder communities.
- **Commercial recurrence:** repeated inside founder communities.
- **Buyer recurrence:** independently described by automation users or small businesses.
- **Cross-segment validation:** the same underlying problem appears in at least two segments.

Cross-segment validation is ranking evidence, not an automatic guarantee of willingness to pay. The final output must still show frequency, verbatim language, attempted solutions, urgency, and payment evidence under the existing skill rubric.

## Error Handling and Resume Behavior

- **Invalid preset:** stop before fetching and report the exact invalid field.
- **Missing/private subreddit:** mark that feed unavailable and continue.
- **Timeout/network error:** record the feed failure and continue.
- **First `429`:** wait 60 seconds and retry that feed once.
- **Repeated `429`:** mark the feed rate-limited and continue; do not retry again during the run.
- **Partial run:** preserve successful per-subreddit state. A later invocation resumes using existing cursors and ID deduplication.
- **No eligible posts:** report that the scan succeeded but produced no posts after filtering; do not treat this as a network failure.
- **Unexpected helper output:** do not append history or advance that feed's cursor.

The final run summary reports each feed as `scanned`, `no-new-posts`, `filtered-empty`, `missing/private`, `rate-limited`, or `failed`.

## Files to Change

| File | Change |
|---|---|
| `config/reddit_feeds/agent-startup.yaml` | Add the versioned 13-feed preset and scan policy |
| `.claude/skills/reddit-opportunity/SKILL.md` | Add preset detection, config validation, multi-feed orchestration, filtering, rate spacing, partial-failure summary, and cross-community aggregation |
| `tests/test_reddit_feed_presets.py` | Validate required fields, allowed sort values, limit bounds, unique subreddits, known segments/languages, and keyword requirements for broad Chinese feeds |

No change is required to `scripts/reddit_rss.py`: it remains a single-request Atom fetcher. No change is required to `reddit-outreach`; it automatically benefits from the existing shared per-subreddit state.

## Verification

1. Run the preset-schema tests.
2. Run the existing RSS helper tests to catch regressions:

   ```bash
   uv run pytest tests/test_reddit_feed_presets.py tests/test_reddit_rss.py -v
   ```

3. Perform a single-feed smoke test against `AI_Agents` and verify the current JSON shape.
4. Exercise the preset flow with helper output stubbed or fixture-backed so verification does not require waiting twelve minutes or depending on Reddit availability.
5. Confirm a Chinese post that matches `智能体` is retained and an unrelated post is filtered.
6. Confirm duplicate IDs are not appended twice.
7. Confirm one failed or rate-limited feed does not prevent later feeds from being processed.
8. Confirm explicit `/reddit-opportunity SaaS` still uses the original single-subreddit flow.

## Out of Scope

- Scheduling or background monitoring.
- Reddit comments, scores, votes, or removal data.
- Reddit authentication or API credentials.
- Automatic replies, posting, voting, or account actions.
- Adding non-Reddit Chinese sources.
- Keyword scoring, negative keywords, per-keyword weights, or a UI for editing presets.
- Changing `reddit-outreach` behavior.
