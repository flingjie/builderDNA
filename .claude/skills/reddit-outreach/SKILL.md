---
name: reddit-outreach
description: >
  ALWAYS use this skill when the user HAS a product and wants to find potential customers on
  Reddit, draft replies, or assist sales — without spamming. Use when the user says
  "find customers on reddit", "draft a reply to this post", "who's describing a problem my
  product solves", "reddit outreach", "product file", "红迪获客", or "帮我写个 Reddit 回复".
  Builds a product file (product, price, problem solved, target user, who it's not for,
  capabilities, objections, user language), scans a subreddit's public RSS feed, scores each
  post (relevance 1-5, actively-seeking, already-answered, age, spam-risk), and drafts replies
  that answer the question first with no links and no promotion. A human posts every reply.
  Shares state with reddit-opportunity. RSS returns posts only — no comments; analysis works
  on post bodies.
---

# reddit-outreach Skill

You find potential customers for an existing product and draft replies that help first, promote
never. You build a product file, scan a subreddit's public RSS feed, score each post, and draft
replies a human posts. You never post anything yourself, never include links, and never promote —
you answer the question first. The only Python you run is the shared `scripts/reddit_rss.py` helper.

## Architecture

```
User: "find customers for my onboarding-automation product on r/SaaS"
       │
       ▼
You (Claude) — load product file, fetch RSS, score posts, draft replies
       │
       ├─► state/product_files/onboarding-automation.md   ⟷  product file
       ├─► python3 scripts/reddit_rss.py SaaS --sort new  → JSON posts
       │
       ├─► Score each post: relevance 1-5, actively-seeking?, answered?, age, spam-risk
       ├─► High-score posts → draft reply (answer first, no links, no promotion)
       └─► output/reddit_leads.json → scored posts + drafts (human posts them)
```

## Quick Reference

| User says | You do |
|-----------|--------|
| "find customers for X on r/Y" | Load/build product file → scan → score → present leads |
| "draft a reply to this post" | Generate one helpful draft for a specific post |
| "build my product file" | Interactively ask the product questions and save it |
| "update my product file" | Edit `state/product_files/{product}.md` per user changes |

---

## 1. Load or build the product file

Read `state/product_files/{product}.md`. If missing, build it by asking, one question at a time:

1. What is the product and its price?
2. What problem does it solve?
3. Who is the target user?
4. Who is it NOT for?
5. What can it do / not do?
6. What common objections do users raise?
7. What verbatim language do users use to describe this problem?

Save as a markdown file with those 7 headings.

## 2. Determine the subreddit

If the user didn't name one, ask at most one question. Otherwise proceed.

## 3. Fetch and score posts

```bash
python3 scripts/reddit_rss.py SUBREDDIT --sort new --limit 25
```

Handle exit codes exactly as `reddit-opportunity` does (rate-limit wait/retry, not-found, network error).

Score each post:

| Criterion | Scale | Meaning |
|-----------|-------|---------|
| relevance | 1–5 | How well the post matches the problem your product solves |
| actively_seeking | bool | Is the poster actively asking for a solution? |
| already_answered_well | bool | Does a good answer already exist? (RSS can't see replies — default false, note uncertainty) |
| too_old | bool | Older than ~30 days? |
| spam_risk | low/medium/high | Would a reply from you read as spam? |

A **lead** is a post with `relevance >= 4`, `actively_seeking == true`, and `spam_risk != high`.

## 4. Draft replies

For each lead, draft a reply that:
- answers the question genuinely and concretely,
- does NOT include a link,
- does NOT promote the product,
- is 2–5 sentences, in the subreddit's content style (read `state/subreddit_profiles/{sub}.md` section 7).

A human copies and posts it. You never post.

## 5. Write output and present

Write `output/reddit_leads.json`:

```json
{
  "product": "onboarding-automation",
  "subreddit": "SaaS",
  "generated_at": "2026-08-20T10:05:00Z",
  "leads": [
    {
      "post_id": "/r/SaaS/comments/abc123/automate_onboarding/",
      "permalink": "https://www.reddit.com/r/SaaS/comments/abc123/automate_onboarding/",
      "author": "/u/jane_doe",
      "title": "Anyone else struggling to automate onboarding?",
      "relevance": 4,
      "actively_seeking": true,
      "already_answered_well": false,
      "too_old": false,
      "spam_risk": "low",
      "draft_reply": "..."
    }
  ]
}
```

Present a table of leads with score and draft. Remind the user: "You post these; I don't."

## 6. State files

| File | Shape |
|------|-------|
| `state/product_files/{product}.md` | 7-heading product file |
| `output/reddit_leads.json` | shape above |
| `state/subreddit_profiles/{sub}.md` | shared profile (read section 7 for style; update section 3 with any new verbatim user language) |
| `state/reddit/{sub}.jsonl` | shared post history (append fetched posts, dedupe by id) |
| `state/reddit/last_scan.json` | shared last-scan cursor (update after each scan) |

Timestamps are ISO 8601 UTC.

## 7. Guardrails (non-optional)

- **Never auto-post.** A human posts every reply.
- **Drafts answer first.** No product links, no promotional language.
- If a post already has a good answer or would make your reply look like spam, do not draft — say why.

## 8. Error handling

| Symptom | Fix |
|---------|-----|
| `rate_limited` (exit 2) | Wait ~60s, retry once; then stop and tell the user |
| `not_found` (exit 3) | Tell the user the subreddit doesn't exist or is private; stop |
| No product file | Build it interactively (Section 1) before scanning |
| No posts reach lead threshold | Report "no strong leads today" and list the highest-relevance posts anyway |
| User asks to auto-post | Refuse — this skill drafts only; a human posts |

## 9. Conversational flow

1. Load/build product file → 2. Determine subreddit → 3. Fetch + score → 4. Draft replies → 5. Write `output/reddit_leads.json` → 6. Present leads → 7. Remind the human to post.
