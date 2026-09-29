---
name: reddit-opportunity
description: >
  ALWAYS use this skill when the user wants to discover product opportunities or pain points
  from a Reddit community and they do NOT yet have a product. Use when the user says
  "find problems people will pay to solve", "what should I build from r/...",
  "reddit opportunity", "discover product ideas from a subreddit", "需求发现",
  "从 Reddit 找商机", or asks to monitor/analyze a subreddit for recurring complaints.
  Runs a bounded, deterministic investigation loop over a subreddit's public RSS feed
  (no API key, no scraper): the control plane owns source calls, budget, state, and
  evidence thresholds; you decide the next action from evidence.
  Supports a single subreddit or a versioned feed preset, including the Agent startup
  opportunity radar. RSS returns posts only — no comments, no scores; analysis works on
  post bodies. After every run, present the pain cluster and ask whether to deep-dive.
---

# reddit-opportunity Skill

You discover product opportunities from a Reddit community when the user has **no product yet**.
Two modes coexist:

- **single mode** — one subreddit, run as a **thin agent loop over a thick control plane**:
  `builderdna investigate` owns source calls, budget, state, and persistence; you own the
  judgment — which evidence gap to close next.
- **preset mode** — a versioned multi-feed scan (e.g. `agent-startup`) that iterates
  `config/reddit_feeds/{preset}.yaml`, filters each feed, and aggregates cross-segment pain.

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 从 Reddit 发现重复痛点与付费意愿，产出 PainCluster 候选 | 回复帖子、私信、获客（超出本项目范围）|
| 通过 `investigate` 控制面动态决定下一步动作 | 从 X 学习技术信号（那是 twitter-learning 的事）|
| 扫描多源预设，聚合跨区段痛点 | 跨源验证概念（那是 concept-radar 的事）|
| 把被选中的候选交给 concept radar 做跨源验证 | 替代 `investigate` 控制面的状态机与持久化 |

## 路由 (Routing)

| 请求 | 路由 |
|------|------|
| 只从 Reddit 发现痛点/机会 | **`reddit-opportunity`**（本 skill）|
| 只从 X 学习技术信号 | `twitter-learning` |
| 跨源验证概念 | `concept-radar` |

## Quick Reference

| User says | You do |
|-----------|--------|
| "find problems in r/X" / "what should I build from r/X" | Run single mode for X |
| "/reddit-opportunity agent-startup" / "scan my Agent startup feeds" | Load `config/reddit_feeds/agent-startup.yaml` and run preset mode |
| "deep dive on #1" | Expand one problem into a full product concept |
| "scan r/X again" / "what changed" | Diff that subreddit vs `last_scan.json`, process only new posts |

## 目标 (Goal)

用尽量少的动作，确定一个**可行动、可验证**的痛点候选：明确受影响场景 + 最小验证动作，
而不是一篇更长的报告。默认预算：最多 8 个动作、最多 3 轮补证、每个主题最多 1 个候选
（这些是可配置参数，不是领域真理）。

## 1. 确定目标模式 (Determine the target mode)

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

Single mode runs the thin loop over `builderdna investigate`. Discussion acquisition (the "fetch")
happens through the control plane's `search_discussions` action — the control plane owns the RSS
source call, budget, state, and persistence; you own which evidence gap to close next.

### 可用动作 (Available actions)

先 `init`，然后每轮从控制面返回的 `allowed_next_actions` 里选一个动作：

- `search_discussions` — 扩展相关讨论（`--params '{"subreddit":"X","sort":"new","limit":25}'`）
- `inspect_thread` — 深读一个已采集的讨论（完整 selftext + 链接的上游来源）
- `find_similar_cases` — 检查重复是否来自独立讨论（按共同上游去重）
- `seek_workaround` — 查用户当前如何解决（保留原文，区分真实实践 vs 建议）
- `seek_counterevidence` — 找"问题不成立/已经解决"的证据
- `propose_pain_cluster` — 提交结构化候选（每个事实必须可追溯到已采集证据）
- `ask_user` / `finish` — 关键分歧交给用户，或结束并记录原因

每条动作的理由必须指向**具体证据缺口**，禁止写"继续搜索"这类泛词。

命令映射：数据动作和 `ask_user` 走 `investigate run --action <action>`；`propose_pain_cluster`
走 `investigate propose --candidate <file>`；`finish` 走 `investigate finish --reason ...`。

### 停止条件 (Stop condition)

满足任一即结束：

1. 信息收益低——新一轮动作不再改变痛点判断；
2. 动作预算或补证轮数用尽；
3. 已找到明确反证或成熟解法，候选降级为"待验证/不成立"；
4. 候选的证据已可追溯、覆盖限制已写明。

诚实报告缺口：没有可靠证据就结束为"待验证"，不要强行生成机会。

### 输出要求 (Output requirements)

1. 用 `investigate propose` 提交 PainClusterCandidate，字段：问题陈述、受影响场景、
   独立案例（evidence_ids）、时间跨度、workaround、反证、样本/覆盖限制、未解决问题、
   最小验证动作。
2. 向用户呈现：扫描摘要 → 排序后的痛点 → "要深入哪个？报数字。"
3. 明确写出"评论未读"（RSS 只给帖子，不给评论/分数），不得把 RSS 结果说成社区共识或生产验证。
4. 单源强信号可以形成候选，但**不能**自行满足 concept-radar 的跨源 BUILD 门槛。

### 循环 (Loop)

```text
用户目标 → investigate init（拿到状态+可用动作）
→ 选一个动作并给理由 → investigate run（校验/执行/持久化，返回 observation + allowed_next_actions）
→ 决定继续 / ask_user / finish
→ investigate propose 提交候选（控制面校验可追溯性）
```

## 2B. Preset fetch loop

Process feeds sequentially in YAML order. Do not launch parallel helper invocations.
For each feed:

1. Invoke:

   ```bash
   python3 scripts/reddit_rss.py SUBREDDIT --sort SCAN_SORT --limit SCAN_LIMIT
   ```

   The helper routes through `http://127.0.0.1:7890` by default; use `--proxy ""` for a direct
   connection. It is single-request and single-subreddit; preset iteration, request spacing,
   filtering, state updates, and aggregation happen in this skill.

2. Handle the result without discarding state already written for earlier feeds:
   - Exit 0: parse and diff the feed, then continue below.
   - Exit 2 (`rate_limited`): wait `retry_after_rate_limit_seconds`, retry up to `retry_limit`,
     then record `rate-limited` and continue to the next feed.
   - Exit 3 (`not_found`): record `missing/private` and continue.
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

A preset run is successful when its configuration is valid and at least one feed completes acquisition,
even if no eligible new posts remain. Report partial failures explicitly; never describe an unscanned
feed as successful.

## 3. 跨区段疼痛分析 (Cross-segment pain analysis)

For each recurring problem you find across posts, record:

- **frequency** — how many posts mention it
- **verbatim language** — the exact phrases users use to describe it
- **pain / urgency** — low / medium / high
- **tried solutions** — what they've already attempted
- **why they fail** — the gap those attempts leave
- **willingness to pay** — explicit ("I'd pay for this"), implicit (frustration + no free fix), or none

In preset mode, also record `source_subreddits` and `source_segments` for each problem. Normalize
wording only when posts describe the same underlying job or failure; preserve verbatim quotations
and their subreddit provenance. Update a subreddit's profile (`state/subreddit_profiles/{sub}.md`)
only from that feed's eligible new posts — never filtered-out posts or posts from a failed fetch.

Use four evidence labels:

- **Technical recurrence** — repeated in `agent-builders`.
- **Commercial recurrence** — repeated in `founders`.
- **Buyer recurrence** — repeated in `automation-buyers` or `chinese-market`.
- **Cross-segment validation** — supported by at least two distinct segments.

Cross-segment validation raises confidence but does not replace explicit or implicit payment evidence.

Start ranking with `frequency × urgency × willingness_to_pay`. In preset mode, use Cross-segment
validation as supporting evidence when ordering otherwise comparable problems. Do not invent a
numeric bonus: show the contributing subreddits and segments so the user can inspect the evidence.
Pick the top problem as the primary opportunity.

## 4. 输出 JSON (Output shapes)

Single mode submits a `PainClusterCandidate` via `investigate propose` and preserves the existing
single-subreddit shape:

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

Preset mode writes `output/reddit_opportunities.json`:

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

The full preset output lists all configured subreddits and one scan-summary row per feed; the
shortened example above demonstrates the shape. Present the scan summary first, then the ranked
opportunity table, then ask: "Deep dive on any of these? Say a number."

## 5. State files

| File | Shape |
|------|-------|
| `state/subreddit_profiles/{sub}.md` | per-subreddit community profile, updated only from eligible new posts |
| `state/reddit/{sub}.jsonl` | one JSON object per line: `{id, title, author, permalink, published, selftext, category, first_seen}` |
| `state/reddit/last_scan.json` | `{ "r/SaaS": {"last_scan": "ISO8601", "newest_post_id": "...", "post_count": 25} }` |
| `config/reddit_feeds/{preset}.yaml` | versioned feed inventory + scan policy; read-only at runtime |
| `output/reddit_opportunities.json` | shape above |

Timestamps are ISO 8601 UTC. Create directories (`state/reddit`, `state/subreddit_profiles`) if missing.

## 6. Error handling

| Symptom | Single mode | Preset mode |
|---------|-------------|-------------|
| `rate_limited` (exit 2) | The control plane owns source calls, budget, and retry; surface the observation and stop | Wait configured delay, retry configured count, record `rate-limited`, continue |
| `not_found` (exit 3) | Report missing/private and stop | Record `missing/private`, continue |
| network / parse / HTTP error | Report and stop | Record `failed`; do not append or advance that feed; continue |
| no new posts | Report and stop | Record `no-new-posts`, continue |
| all new posts filtered | Not applicable | Advance the raw cursor, record `filtered-empty`, continue |

## Guardrails

- 只读公开帖子、只写本地状态，绝不发帖。
- 候选是给用户验证的；不部署、不收款。
- 被用户选中的候选，走 `concepts.adapters.reddit` / `concepts.handoffs` 交给 concept radar
  （`comments_read: false`，`independence_key` 按共同上游去重，绝不把转述算成多个案例）。

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

## Conversational flow

**Single mode:** determine subreddit → `investigate init` → choose actions until stop condition →
`investigate propose` → present → ask to deep-dive.

**Preset mode:** resolve + validate preset → fetch feeds sequentially → filter + update per-subreddit
state → retain per-feed statuses → aggregate eligible posts → cross-segment analysis → rank →
generate concept → write preset output → present scan summary + opportunities → ask to deep-dive.
