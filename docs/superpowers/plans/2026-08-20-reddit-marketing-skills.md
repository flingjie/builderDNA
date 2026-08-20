# Reddit Marketing Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two Claude Code skills (`reddit-opportunity` + `reddit-outreach`) plus a shared stdlib-only RSS helper and its tests, from the approved spec `docs/superpowers/specs/2026-08-20-reddit-marketing-skills-design.md`.

**Architecture:** A single stdlib Python helper (`scripts/reddit_rss.py`) fetches and parses a subreddit's public Atom RSS feed into JSON. Two Claude-orchestrated skills consume that JSON: `reddit-opportunity` (Agent 1 — no product yet → find recurring pain → product concept) and `reddit-outreach` (Agent 2 — have a product → score posts → draft replies a human posts). Both maintain a shared 7-section Subreddit Profile in `state/subreddit_profiles/`.

**Tech Stack:** Python ≥3.11 stdlib only for the helper (`urllib.request`, `xml.etree.ElementTree`, `argparse`, `json`). Skills are pure Claude-orchestrated markdown. Tests use `pytest` + `monkeypatch` + `capsys` (no `pytest-httpx` needed — the helper uses `urllib`, not `httpx`).

## Global Constraints

- **RSS only** — no Reddit API key, no scraper, no `.json` endpoint. Copy this verbatim into skills: "Reddit's `.rss` returns posts only — no comments, no upvote scores, no removal data."
- **Human posts everything** — never auto-post; drafts answer the question first, no links, no promotion.
- **Helper is stdlib-only** — `urllib.request` + `xml.etree.ElementTree`; do not import `httpx`, `requests`, `pydantic`, or any third-party lib.
- **On-demand + diff** — skills run when invoked; record last-scan time + newest post id, show what changed.
- **Rate ~1 request/min** at the skill layer (space consecutive helper invocations); the helper itself is one request per invocation.
- **Python ≥3.11**; run helper via `python3 scripts/reddit_rss.py` (no `uv run` required).
- **Skill files** live at `.claude/skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`); state files use snake_case keys; timestamps are ISO 8601 UTC.

---

### Task 1: RSS helper script + unit tests

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/reddit_rss.py`
- Test: `tests/test_reddit_rss.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `build_url(subreddit, sort, limit) -> str`, `parse_atom(xml_text) -> list[dict]`, `fetch(url, timeout=15) -> str`, `main(argv=None) -> int`. Later skills invoke `python3 scripts/reddit_rss.py SUBREDDIT [--sort new] [--limit 25]` and read stdout JSON. Exit codes: `0` success, `1` network/parse error, `2` rate-limited (403/429), `3` not found (404).

- [ ] **Step 1: Create `scripts/__init__.py`**

Empty file (makes `scripts.reddit_rss` importable; pytest `pythonpath=["."]` already puts the repo root on `sys.path`):

```bash
touch scripts/__init__.py
```

- [ ] **Step 2: Write the failing test `tests/test_reddit_rss.py`**

```python
import json
import urllib.error

from scripts.reddit_rss import build_url, main, parse_atom

FIXTURE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>r/SaaS</title>
  <entry>
    <title>Anyone else struggling to automate onboarding?</title>
    <author><name>/u/jane_doe</name></author>
    <link href="https://www.reddit.com/r/SaaS/comments/abc123/automate_onboarding/" />
    <published>2026-08-19T12:00:00+00:00</published>
    <id>/r/SaaS/comments/abc123/automate_onboarding/</id>
    <content>We keep copy-pasting the same onboarding steps.</content>
    <category term="r/SaaS" label="r/SaaS"/>
  </entry>
</feed>"""


def test_build_url():
    assert build_url("SaaS", "new", 25) == "https://www.reddit.com/r/SaaS/.rss?sort=new&limit=25"


def test_parse_atom_extracts_all_fields():
    posts = parse_atom(FIXTURE_ATOM)
    assert len(posts) == 1
    p = posts[0]
    assert p["title"] == "Anyone else struggling to automate onboarding?"
    assert p["author"] == "/u/jane_doe"
    assert p["permalink"] == "https://www.reddit.com/r/SaaS/comments/abc123/automate_onboarding/"
    assert p["published"] == "2026-08-19T12:00:00+00:00"
    assert p["selftext"] == "We keep copy-pasting the same onboarding steps."
    assert p["category"] == "r/SaaS"
    assert p["id"] == "/r/SaaS/comments/abc123/automate_onboarding/"


def test_parse_atom_missing_fields_become_empty():
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>x</title></entry></feed>"""
    posts = parse_atom(xml)
    assert posts[0]["author"] == ""
    assert posts[0]["permalink"] == ""
    assert posts[0]["selftext"] == ""


def test_main_success(monkeypatch, capsys):
    monkeypatch.setattr("scripts.reddit_rss.fetch", lambda url, timeout=15: FIXTURE_ATOM)
    code = main(["SaaS"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(out) == 1
    assert out[0]["id"] == "/r/SaaS/comments/abc123/automate_onboarding/"


def test_main_rate_limited(monkeypatch, capsys):
    def raise_429(url, timeout=15):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr("scripts.reddit_rss.fetch", raise_429)
    code = main(["SaaS"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["error"] == "rate_limited"
    assert out["code"] == 429


def test_main_not_found(monkeypatch, capsys):
    def raise_404(url, timeout=15):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr("scripts.reddit_rss.fetch", raise_404)
    code = main(["SaaS"])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["error"] == "not_found"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_reddit_rss.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.reddit_rss'` (the helper doesn't exist yet).

- [ ] **Step 4: Write the helper `scripts/reddit_rss.py`**

```python
#!/usr/bin/env python3
"""Fetch a subreddit's public RSS feed and emit posts as JSON.

Stdlib only — no Reddit API key, no scraper. Uses the public .rss endpoint.
Respect Reddit: set a real User-Agent; callers space requests (~1/min).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_USER_AGENT = "BuilderDNA/0.1 (reddit RSS research; local use)"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
TIMEOUT = 15


def build_url(subreddit: str, sort: str, limit: int) -> str:
    """Return the public RSS URL for a subreddit (sort validated by argparse)."""
    return f"https://www.reddit.com/r/{subreddit}/.rss?sort={sort}&limit={limit}"


def parse_atom(xml_text: str) -> list[dict]:
    """Parse an Atom feed into a list of post dicts.

    Fields: id, title, author, permalink, published, selftext, category.
    Missing fields become empty strings (never raises on missing elements).
    """
    root = ET.fromstring(xml_text)
    posts: list[dict] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = (entry.findtext("atom:title", "", ATOM_NS) or "").strip()
        author_el = entry.find("atom:author/atom:name", ATOM_NS)
        author = (author_el.text or "").strip() if author_el is not None else ""
        link_el = entry.find("atom:link", ATOM_NS)
        permalink = link_el.get("href", "") if link_el is not None else ""
        published = entry.findtext("atom:published", "", ATOM_NS) or ""
        selftext = (entry.findtext("atom:content", "", ATOM_NS) or "").strip()
        category = entry.findtext("atom:category", "", ATOM_NS) or ""
        post_id = entry.findtext("atom:id", "", ATOM_NS) or ""
        posts.append({
            "id": post_id.strip(),
            "title": title,
            "author": author,
            "permalink": permalink,
            "published": published,
            "selftext": selftext,
            "category": category,
        })
    return posts


def fetch(url: str, timeout: int = TIMEOUT) -> str:
    """Fetch a URL and return the response body as decoded text."""
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subreddit", help="subreddit name without r/ (e.g. 'SaaS')")
    parser.add_argument("--sort", choices=["hot", "new", "top"], default="new")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)

    url = build_url(args.subreddit, args.sort, args.limit)
    try:
        xml_text = fetch(url)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            print(json.dumps({
                "error": "rate_limited", "code": exc.code,
                "retry_after": exc.headers.get("retry-after", "60"),
            }))
            return 2
        if exc.code == 404:
            print(json.dumps({
                "error": "not_found",
                "message": f"r/{args.subreddit} does not exist or is private",
            }))
            return 3
        print(json.dumps({"error": "http_error", "code": exc.code}))
        return 1
    except urllib.error.URLError as exc:
        print(json.dumps({"error": "network_error", "message": str(exc.reason)}))
        return 1

    try:
        posts = parse_atom(xml_text)
    except ET.ParseError as exc:
        print(json.dumps({"error": "parse_error", "message": str(exc)}))
        return 1

    print(json.dumps(posts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reddit_rss.py -v`
Expected: PASS — 6 passed.

- [ ] **Step 6: Smoke-test the helper against a real subreddit (network)**

Run: `python3 scripts/reddit_rss.py SaaS --sort new --limit 5`
Expected: exit 0, a JSON array printed; if rate-limited, a `{"error": "rate_limited", ...}` object. (Either output is fine — do not retry.)

- [ ] **Step 7: Commit**

```bash
git add scripts/__init__.py scripts/reddit_rss.py tests/test_reddit_rss.py
git commit -m "feat: add reddit RSS helper script + tests"
```

---

### Task 2: `reddit-opportunity` skill

**Files:**
- Create: `.claude/skills/reddit-opportunity/SKILL.md`

**Interfaces:**
- Consumes: `python3 scripts/reddit_rss.py SUBREDDIT --sort new` (Task 1). Reads/writes `state/subreddit_profiles/{sub}.md`, `state/reddit/{sub}.jsonl`, `state/reddit/last_scan.json`, `output/reddit_opportunities.json` (all defined in this task's body).
- Produces: a skill triggerable by the description below.

- [ ] **Step 1: Write `.claude/skills/reddit-opportunity/SKILL.md` with exactly this content**

````markdown
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
````

- [ ] **Step 2: Verify the frontmatter parses (name + description present, no tabs)**

Run: `grep -c "^name: reddit-opportunity" .claude/skills/reddit-opportunity/SKILL.md && grep -c "^description:" .claude/skills/reddit-opportunity/SKILL.md`
Expected: `1` and `1`.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/reddit-opportunity/SKILL.md
git commit -m "feat: add reddit-opportunity skill (Agent 1: need discovery)"
```

---

### Task 3: `reddit-outreach` skill

**Files:**
- Create: `.claude/skills/reddit-outreach/SKILL.md`

**Interfaces:**
- Consumes: `python3 scripts/reddit_rss.py SUBREDDIT --sort new` (Task 1); shares `state/subreddit_profiles/`, `state/reddit/`, `state/reddit/last_scan.json` (Task 2). Reads/writes `state/product_files/{product}.md` and `output/reddit_leads.json` (defined below).
- Produces: a skill triggerable by the description below.

- [ ] **Step 1: Write `.claude/skills/reddit-outreach/SKILL.md` with exactly this content**

````markdown
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
````

- [ ] **Step 2: Verify the frontmatter parses**

Run: `grep -c "^name: reddit-outreach" .claude/skills/reddit-outreach/SKILL.md && grep -c "^description:" .claude/skills/reddit-outreach/SKILL.md`
Expected: `1` and `1`.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/reddit-outreach/SKILL.md
git commit -m "feat: add reddit-outreach skill (Agent 2: customer discovery + reply drafts)"
```

---

### Task 4: CLAUDE.md skill table + final verification

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: documented skills in the repo's skill table.

- [ ] **Step 1: Add two rows to the skills table in `CLAUDE.md`**

Find the skills table (the `| Skill | Purpose | Trigger |` table under `## Skills`). Add these two rows after the `repo-awesome` row:

```markdown
| `reddit-opportunity` | Discover product opportunities + pain points from a Reddit community (no product yet): RSS → Subreddit Profile → recurring problems → product concept | "find problems people will pay to solve", "what should I build from r/...", "从 Reddit 找商机" |
| `reddit-outreach` | Find customers + draft replies for an existing product on Reddit (human posts, no spam) | "find customers on reddit", "draft a reply", "红迪获客" |
```

Also update the line "Ten skills are deployed" to "Twelve skills are deployed".

- [ ] **Step 2: Full verification**

Run the helper smoke test and the test suite:

```bash
python3 scripts/reddit_rss.py SaaS --sort new --limit 5
uv run pytest tests/test_reddit_rss.py -v
```

Expected: helper exits 0 (or prints a rate-limit object); tests show `6 passed`.

Manually confirm: both skills appear in `.claude/skills/` with valid frontmatter; `scripts/reddit_rss.py` uses only stdlib imports.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document reddit-opportunity + reddit-outreach skills"
```
