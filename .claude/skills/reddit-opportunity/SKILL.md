---
name: reddit-opportunity
description: >
  ALWAYS use this skill when the user wants to discover product opportunities or pain points
  from a Reddit community and they do NOT yet have a product. Use when the user says
  "find problems people will pay to solve", "what should I build from r/...",
  "reddit opportunity", "discover product ideas from a subreddit", "需求发现",
  "从 Reddit 找商机", or asks to monitor/analyze a subreddit for recurring complaints.
  Monitors a subreddit's public RSS feed (no API key, no scraper), builds and updates a
  7-section Subreddit Profile (the shared community profile both reddit skills maintain),
  finds recurring problems, judges willingness to pay, and generates a product concept.
  Supports a single subreddit or a versioned feed preset, including the Agent startup
  opportunity radar. Shares state with reddit-outreach. RSS returns posts only — no
  comments, no scores; analysis works on post bodies. After every run, present a ranked
  list of problems and ask whether to deep-dive.
---

# reddit-opportunity Skill

You discover product opportunities from a Reddit community when the user has **no product yet**.
You monitor a subreddit's public RSS feed, maintain a 7-section Subreddit Profile, find recurring
problems people describe, judge whether they'd pay to solve them, and generate a product concept.
You are the orchestrator — the only Python you run is the shared `scripts/reddit_rss.py` helper.

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

## 3. Build / update the Subreddit Profile

Read `state/subreddit_profiles/{sub}.md` (create if missing). Merge new signals into the 7 sections.
This profile is the shared asset both reddit skills maintain — update it, don't overwrite unrelated
sections.

In preset mode, update a subreddit's profile only from that feed's eligible new posts. Never merge
filtered-out posts or posts from a failed fetch. One feed's profile failure does not erase or replace
profiles already updated earlier in the run.

The 7 sections and how to derive them from RSS post bodies:

| # | Section | How to derive (RSS-only) |
|---|---------|---------------------------|
| 1 | Demographics | Infer age / region / occupation / stage from post language |
| 2 | Psychographics | Infer wants / fears / self-image / who they avoid / what embarrasses them |
| 3 | User language | Extract verbatim phrases for the problem / ideal solution / tried methods |
| 4 | Tried solutions | What they've already tried + why it failed |
| 5 | What content works | **Not supported in RSS-only mode** — leave a note "requires .json API (upvote/removal data)" |
| 6 | Community rules | Partially: use `WebFetch` on the subreddit sidebar/rules page (permitted for `www.reddit.com`) |
| 7 | Content style | Infer post length / personal-story use / headers / common openings from post bodies |

## 4. Pain analysis

For each recurring problem you find across posts, record:

- **frequency** — how many posts mention it
- **verbatim language** — the exact phrases users use to describe it
- **pain / urgency** — low / medium / high
- **tried solutions** — what they've already attempted
- **why they fail** — the gap those attempts leave
- **willingness to pay** — explicit ("I'd pay for this"), implicit (frustration + no free fix), or none

In preset mode, also record `source_subreddits` and `source_segments` for each problem. Normalize
wording only when posts describe the same underlying job or failure; preserve verbatim quotations
and their subreddit provenance.

Use four evidence labels:

- **Technical recurrence** — repeated in `agent-builders`.
- **Commercial recurrence** — repeated in `founders`.
- **Buyer recurrence** — repeated in `automation-buyers` or `chinese-market`.
- **Cross-segment validation** — supported by at least two distinct segments.

Cross-segment validation raises confidence but does not replace explicit or implicit payment evidence.

## 5. Rank and select

Start with `frequency × urgency × willingness_to_pay`. In preset mode, use Cross-segment validation
as supporting evidence when ordering otherwise comparable problems. Do not invent a numeric bonus:
show the contributing subreddits and segments so the user can inspect the evidence. Pick the top
problem as the primary opportunity.

## 6. Generate a product concept

For the top problem, produce:
- **positioning** — one paragraph: who it's for, what it does, why now.
- **guide outline** — a 25–30 section outline (markdown) for a paid guide that solves the problem.
- **landing copy** — headline + subhead + 3 benefit bullets.

**Scope boundary:** actual landing-page deployment and payment (Stripe) are OUT of scope. You output
positioning + guide content + copy that a human hands off to deployment.

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

## 8. State files

| File | Shape |
|------|-------|
| `state/subreddit_profiles/{sub}.md` | 7-section markdown profile |
| `state/reddit/{sub}.jsonl` | one JSON object per line: `{id, title, author, permalink, published, selftext, category, first_seen}` |
| `state/reddit/last_scan.json` | `{ "r/SaaS": {"last_scan": "ISO8601", "newest_post_id": "...", "post_count": 25} }` |
| `config/reddit_feeds/{preset}.yaml` | versioned feed inventory + scan policy; read-only at runtime |
| `output/reddit_opportunities.json` | shape above |

Timestamps are ISO 8601 UTC. Create directories (`state/reddit`, `state/subreddit_profiles`) if missing.

## 9. Guardrails

- This skill only READS public posts and writes local state. It never posts to Reddit.
- The product concept is for the user to validate; you do not deploy anything or take payment.

## 10. Import into the concept radar

Reddit findings can be imported into the concept radar as primary ("L1") evidence via the
`concepts.adapters.reddit` adapter (`post_to_evidence` / `from_signal`), which normalizes RSS
title/body findings into `ConceptEvidence` (role=`problem`, directness=`direct` only for a
first-hand report; `indirect` otherwise). Two coverage rules apply to every report:

- RSS returns posts only — no comments, no scores. State explicitly "comments were not read"
  (`comments_read: false`) whenever you have not imported comments through an authenticated
  or publicly-supported path; never describe RSS-only findings as community consensus or
  production validation.
- Cross-community recurrence counts independent communities and upstream links (via
  `independence_key`), not raw post count.

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

## 11. Conversational flow

**Single mode:** determine subreddit → fetch + diff → update profile → analyze pain → rank → generate
concept → write output → present → ask to deep-dive.

**Preset mode:** resolve + validate preset → fetch feeds sequentially → filter + update per-subreddit
state → retain per-feed statuses → aggregate eligible posts → cross-segment analysis → rank → generate
concept → write preset output → present scan summary + opportunities → ask to deep-dive.
