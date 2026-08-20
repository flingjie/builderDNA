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
  Shares state with reddit-outreach. RSS returns posts only — no comments, no scores;
  analysis works on post bodies. After every run, present a ranked list of problems and
  ask whether to deep-dive.
---

# reddit-opportunity Skill

You discover product opportunities from a Reddit community when the user has **no product yet**.
You monitor a subreddit's public RSS feed, maintain a 7-section Subreddit Profile, find recurring
problems people describe, judge whether they'd pay to solve them, and generate a product concept.
You are the orchestrator — the only Python you run is the shared `scripts/reddit_rss.py` helper.

## Architecture

```
User: "what should I build from r/SaaS?"
       │
       ▼
You (Claude) — fetch RSS, diff new posts, update profile, analyze pain, rank, generate concept
       │
       ├─► python3 scripts/reddit_rss.py SaaS --sort new      → JSON posts
       │
       ├─► state/reddit/last_scan.json        ⟷  last scan + newest post id (diff)
       ├─► state/subreddit_profiles/SaaS.md   ⟷  7-section community profile
       ├─► state/reddit/SaaS.jsonl            ⟷  append-only post history
       │
       ├─► Pain analysis (frequency, verbatim language, urgency, tried, why-fail, willingness)
       ├─► Rank problems → pick top 1
       └─► output/reddit_opportunities.json   → ranked problems + product concepts
```

## Quick Reference

| User says | You do |
|-----------|--------|
| "find problems in r/X" / "what should I build from r/X" | Fetch → update profile → rank pain → present |
| "deep dive on #1" | Expand one problem into a full product concept + guide outline + landing copy |
| "scan r/X again" / "what changed" | Diff vs `last_scan.json`, process only new posts |

---

## 1. Determine the subreddit

If the user didn't name one, ask at most one question: "Which subreddit?" (e.g. `SaaS`, `sideproject`,
`EntrepreneurRideAlong`). If given, proceed immediately.

## 2. Fetch posts and diff

```bash
python3 scripts/reddit_rss.py SUBREDDIT --sort new --limit 25
```

The helper routes through `http://127.0.0.1:7890` by default; use `--proxy ""` for a direct connection.

- If exit 0: parse the JSON array of posts.
- If exit 2 (`rate_limited`): wait ~60s, retry once; if still rate-limited, tell the user and stop.
- If exit 3 (`not_found`): tell the user "r/SUBREDDIT does not exist or is private" and stop.
- If exit 1 (`network_error` / `parse_error` / `http_error`): tell the user the error and stop.

Read `state/reddit/last_scan.json`. Compare each post's `id` against the stored `newest_post_id`
for this subreddit: posts **newer** than it are new. On first scan (no entry), all posts are new.
Append every fetched post to `state/reddit/{sub}.jsonl` (dedupe by `id` — skip if already present),
then update `last_scan.json`.

## 3. Build / update the Subreddit Profile

Read `state/subreddit_profiles/{sub}.md` (create if missing). Merge new signals into the 7 sections.
This profile is the shared asset both reddit skills maintain — update it, don't overwrite unrelated
sections. The 7 sections and how to derive them from RSS post bodies:

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

## 5. Rank and select

Rank problems by `frequency × urgency × willingness_to_pay`. Pick the top one as the primary
opportunity.

## 6. Generate a product concept

For the top problem, produce:
- **positioning** — one paragraph: who it's for, what it does, why now.
- **guide outline** — a 25–30 section outline (markdown) for a paid guide that solves the problem.
- **landing copy** — headline + subhead + 3 benefit bullets.

**Scope boundary:** actual landing-page deployment and payment (Stripe) are OUT of scope. You output
positioning + guide content + copy that a human hands off to deployment.

## 7. Write output and present

Write `output/reddit_opportunities.json`:

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
      "product_concept": "...",
      "guide_outline": ["..."],
      "landing_copy": "..."
    }
  ]
}
```

Present a ranked table, then ask: "Deep dive on any of these? Say a number."

## 8. State files

| File | Shape |
|------|-------|
| `state/subreddit_profiles/{sub}.md` | 7-section markdown profile |
| `state/reddit/{sub}.jsonl` | one JSON object per line: `{id, title, author, permalink, published, selftext, category, first_seen}` |
| `state/reddit/last_scan.json` | `{ "r/SaaS": {"last_scan": "ISO8601", "newest_post_id": "...", "post_count": 25} }` |
| `output/reddit_opportunities.json` | shape above |

Timestamps are ISO 8601 UTC. Create directories (`state/reddit`, `state/subreddit_profiles`) if missing.

## 9. Guardrails

- This skill only READS public posts and writes local state. It never posts to Reddit.
- The product concept is for the user to validate; you do not deploy anything or take payment.

## 10. Error handling

| Symptom | Fix |
|---------|-----|
| `rate_limited` (exit 2) | Wait ~60s, retry once; then stop and tell the user |
| `not_found` (exit 3) | Tell the user the subreddit doesn't exist or is private; stop |
| `network_error` / `parse_error` | Tell the user the error; stop |
| No new posts since last scan | Report "no new posts since {last_scan}" and stop |
| Profile section 5 requested | Explain RSS has no upvote/removal data; mark section "requires .json API" |

## 11. Conversational flow

1. Determine subreddit → 2. Fetch + diff → 3. Update profile → 4. Analyze pain → 5. Rank → 6. Generate concept → 7. Write `output/reddit_opportunities.json` → 8. Present ranked table → 9. Ask to deep-dive.
