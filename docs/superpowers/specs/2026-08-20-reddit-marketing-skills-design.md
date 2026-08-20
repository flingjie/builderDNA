# Reddit Marketing Skills: `reddit-opportunity` + `reddit-outreach`

**Date:** 2026-08-20
**Status:** approved
**Scope:** two new skills in `.claude/skills/` + one shared helper script in `scripts/`

## Goal

Turn a source document describing an AI-Agent-driven Reddit marketing system into two Claude Code skills, plus a small shared RSS helper. The system listens to Reddit communities, understands user pain, and discovers opportunities / drafts replies — while **a human does all posting and account actions**. The skills are pure Claude-orchestrated (matching `repo-trend` / `repo-awesome`), not part of the `builderdna` Python pipeline.

Two skills, split by the source's "two agents":

| Skill | Agent | Job (one line) |
|-------|-------|----------------|
| `reddit-opportunity` | Agent 1 (no product yet) | Monitor a community → find recurring pain → validate willingness-to-pay → generate a product concept |
| `reddit-outreach` | Agent 2 (have a product) | Build a product file → find people describing the problem → score → draft replies (human posts) |

The **Subreddit Profile** (the source's "real product") is shared infrastructure both skills read and write.

## Confirmed Constraints

These were decided during brainstorming and are binding:

1. **Split:** two agents → two skills; Subreddit Profile = shared infra.
2. **Data source:** RSS only (`.rss`), no API key, no scraper. **Reddit's `.rss` returns posts only — no comments, no scores.** The skills analyze post bodies (self-posts); comment analysis is explicitly out of scope. This limitation is documented in the skills, not hidden.
3. **Cadence:** on-demand (user says "scan r/xyz"), plus record last-scan time and show diffs (mirrors `repo-trend`'s watch pattern). No built-in scheduler.
4. **Implementation:** skill + helper script. RSS fetch/parse lives in a small stdlib-only Python helper (reliable Atom parsing); the skills orchestrate around it.

## Shared Infrastructure

### Helper script — `scripts/reddit_rss.py`

Stdlib only (`urllib.request` + `xml.etree.ElementTree`), no deps, runnable via `python3` or `uv run`.

```
python3 scripts/reddit_rss.py SUBREDDIT [--sort hot|new|top] [--limit 25]
```

- Fetches `https://www.reddit.com/r/{sub}/.rss` with a custom `User-Agent` (Reddit blocks default Python UAs).
- Parses the Atom feed; emits a JSON array of posts:
  ```json
  [{ "id": "t3_abc123", "title": "...", "author": "u/foo",
     "permalink": "https://www.reddit.com/...", "published": "2026-08-20T...Z",
     "selftext": "...", "category": "r/foo" }]
  ```
- On 403/429 returns a JSON object with an `error` code and a `retry_after` hint; the skill reads it, waits, retries once, then stops on repeat failure.
- On a missing/private subreddit returns a distinct error code.

Rate limiting (~1 request/min) is enforced at the skill layer by spacing consecutive helper invocations; the helper itself is a single-request, single-invocation tool.

### Shared state files

| File | Purpose |
|------|---------|
| `state/subreddit_profiles/{subreddit}.md` | 7-section community profile (core asset; both skills maintain) |
| `state/reddit/{subreddit}.jsonl` | Append-only post history, deduped by post `id` |
| `state/reddit/last_scan.json` | Per-subreddit last-scan timestamp + newest-seen post id (for diffs) |
| `output/reddit_opportunities.json` | Skill 1 output: ranked recurring problems + product concepts |
| `state/product_files/{product}.md` | Skill 2's "product file" (built once, reused) |
| `output/reddit_leads.json` | Skill 2 output: scored posts + reply drafts |

## Skill 1 — `reddit-opportunity` (Agent 1)

Flow:
1. Determine target subreddit(s); ask at most one clarifying question if none given.
2. Run `scripts/reddit_rss.py`, diff against `last_scan.json`, process only new posts.
3. **Build/update the Subreddit Profile** (read old profile, merge new signals into the 7 sections).
4. **Pain analysis** — for each recurring problem record: frequency, verbatim user language, pain/urgency, solutions already tried, why they fail, willingness to pay.
5. **Rank** problems, select the top one.
6. **Generate a product concept**: positioning + a 25–30 page guide outline/draft (Markdown) + landing-page copy.
7. Write `output/reddit_opportunities.json`, present the ranked list, offer to deep-dive.

**Scope boundary (YAGNI):** actual landing-page deployment and payment (Stripe) are **out of scope** — the skill outputs positioning + copy + guide content that a human hands off to deployment.

## Skill 2 — `reddit-outreach` (Agent 2)

Flow:
1. Load the product file; if missing, build it interactively: what the product is, price, problem solved, target user, who it's *not* for, can/can't do, common objections, and the **verbatim language users use to describe the problem**.
2. Determine subreddit(s).
3. Fetch posts, score each: relevance 1–5, actively-seeking?, already-answered-well?, too-old?, spam-risk?.
4. For high-score posts, draft replies — answer the question genuinely, **no links, no promotion**.
5. Write `output/reddit_leads.json` (score + draft per lead), present to the human.

## Guardrails (baked into skill text, non-optional)

- **Never auto-post.** The human posts every reply.
- **Drafts answer the question first**; no product links; no promotional language.
- These are the source's own core rules and are what keep the system from becoming spam. They are stated prominently in `reddit-outreach` and referenced in `reddit-opportunity`.

## Subreddit Profile schema (7 sections) vs. RSS capability

| # | Section | Derivable from RSS? |
|---|---------|---------------------|
| 1 | Demographics (age / region / occupation / stage) | ✅ inferred from selftext |
| 2 | Psychographics (wants / fears / self-image / anti-associations / embarrassments) | ✅ inferred from selftext |
| 3 | User language (verbatim for problem / ideal solution / tried methods) | ✅ extracted verbatim |
| 4 | Tried solutions + why they fail | ✅ inferred from selftext |
| 5 | What content works (upvoted / ignored / removed) | ❌ **not derivable — RSS has no scores/removal data** |
| 6 | Community rules (self-promo allowed? links? mod strictness) | ⚠️ partial — via `WebFetch` of sidebar/rules (already permitted for `www.reddit.com`) |
| 7 | Content style (length / personal stories / headers / openings) | ✅ inferred from post bodies |

Section 5 is explicitly marked "not supported in RSS-only mode" in both skills (upvote data would require the `.json` endpoint, which was excluded). Section 6 is filled via `WebFetch` of the subreddit sidebar/rules.

## Skill frontmatter (trigger design)

- `reddit-opportunity` `description` must trigger on: "find problems people will pay to solve", "what should I build from r/…", "reddit opportunity", "discover product ideas from a subreddit", "需求发现", "从 Reddit 找商机".
- `reddit-outreach` `description` must trigger on: "find customers on reddit", "draft a reply to this post", "product file", "reddit outreach", "谁在找我的产品能解决的问题", "红迪获客".

## Files to Create

| File | Content |
|------|---------|
| `scripts/reddit_rss.py` | stdlib Atom RSS fetcher → JSON |
| `.claude/skills/reddit-opportunity/SKILL.md` | Agent 1 skill (flow + profile schema + state) |
| `.claude/skills/reddit-outreach/SKILL.md` | Agent 2 skill (flow + scoring + drafts + guardrails) |
| `tests/test_reddit_rss.py` | unit tests for the helper (Atom parse, 403 handling, dedup/limit) |

A small `CLAUDE.md` edit (add two rows to the skills table) is included in the implementation plan below.

## Implementation Plan

1. Write `scripts/reddit_rss.py` (stdlib `urllib` + `xml.etree`, custom UA, error codes, JSON out).
2. Write `tests/test_reddit_rss.py` (parse a fixture Atom feed, mock 403, verify limit/dedup) and run `uv run pytest tests/test_reddit_rss.py -v`.
3. Write `.claude/skills/reddit-opportunity/SKILL.md`.
4. Write `.claude/skills/reddit-outreach/SKILL.md`.
5. Update `CLAUDE.md` skills table with the two new rows (documentation hygiene).
6. Verification: run the helper against one real subreddit, confirm JSON shape; manually walk each skill's happy path.
