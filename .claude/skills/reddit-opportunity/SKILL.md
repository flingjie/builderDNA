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
  evidence thresholds; you decide the next action from evidence. RSS returns posts only —
  no comments, no scores. After every run, present the pain cluster and ask whether to
  deep-dive.
---

# reddit-opportunity Skill

You discover product opportunities from a Reddit community when the user has **no product yet**.
You run a **thin agent loop over a thick control plane**: `builderdna investigate` owns source
calls, budget, state, and persistence; you own the judgment — which evidence gap to close next.

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 从 Reddit 发现重复痛点与付费意愿，产出 PainCluster 候选 | 回复帖子、私信、获客（超出本项目范围）|
| 通过 `investigate` 控制面动态决定下一步动作 | 从 X 学习技术信号（那是 twitter-learning 的事）|
| 把被选中的候选交给 concept radar 做跨源验证 | 跨源验证概念（那是 concept-radar 的事）|

## 目标 (Goal)

用尽量少的动作，确定一个**可行动、可验证**的痛点候选：明确受影响场景 + 最小验证动作，
而不是一篇更长的报告。默认预算：最多 8 个动作、最多 3 轮补证、每个主题最多 1 个候选
（这些是可配置参数，不是领域真理）。

## 可用动作 (Available actions)

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

## 停止条件 (Stop condition)

满足任一即结束：

1. 信息收益低——新一轮动作不再改变痛点判断；
2. 动作预算或补证轮数用尽；
3. 已找到明确反证或成熟解法，候选降级为"待验证/不成立"；
4. 候选的证据已可追溯、覆盖限制已写明。

诚实报告缺口：没有可靠证据就结束为"待验证"，不要强行生成机会。

## 输出要求 (Output requirements)

1. 用 `investigate propose` 提交 PainClusterCandidate，字段：问题陈述、受影响场景、
   独立案例（evidence_ids）、时间跨度、workaround、反证、样本/覆盖限制、未解决问题、
   最小验证动作。
2. 向用户呈现：扫描摘要 → 排序后的痛点 → "要深入哪个？报数字。"
3. 明确写出"评论未读"（RSS 只给帖子，不给评论/分数），不得把 RSS 结果说成社区共识或生产验证。
4. 单源强信号可以形成候选，但**不能**自行满足 concept-radar 的跨源 BUILD 门槛。

## 循环 (Loop)

```text
用户目标 → investigate init（拿到状态+可用动作）
→ 选一个动作并给理由 → investigate run（校验/执行/持久化，返回 observation + allowed_next_actions）
→ 决定继续 / ask_user / finish
→ investigate propose 提交候选（控制面校验可追溯性）
```

## Guardrails

- 只读公开帖子、只写本地状态，绝不发帖。
- 候选是给用户验证的；不部署、不收款。
- 被用户选中的候选，走 `concepts.adapters.reddit` / `concepts.handoffs` 交给 concept radar
  （`comments_read: false`，`independence_key` 按共同上游去重，绝不把转述算成多个案例）。
