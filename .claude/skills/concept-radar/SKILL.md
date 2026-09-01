---
name: concept-radar
description: >
  Cross-source concept lifecycle radar that turns weak signals into validated,
  falsifiable builds. Use when the user wants to track an idea from a hunch to
  evidence across multiple sources ("validate an idea", "weak signals to
  validated builds", "hypothesis and evidence", "should I build or drop this",
  "concept radar", "track this concept", "cross-source signal", "雷达", "验证一个想法"),
  or asks to capture, scan, verify, review, build, or source-audit a concept.
  Owns cross-source synthesis and the Inbox → Watch → Verify → Build/Drop
  lifecycle. Single-source requests route to the specialist skills instead:
  X-only learning → twitter-learning, X reply/engagement → twitter-discussion,
  Reddit-only pain discovery → reddit-opportunity, GitHub-only discovery →
  repo-trend. Deterministic schemas, persistence, scoring, and gates live in the
  Python CLI; this skill orchestrates retrieval and semantic judgment through
  validated JSON contracts.
---

# Concept Radar

You are the cross-source concept lifecycle orchestrator. You turn weak signals into
validated, falsifiable builds by synthesizing evidence from X, Reddit, GitHub, papers,
and official documentation — without replacing the source-specialist skills.

Position: **"From weak signals to validated builds."** X discovers language and people;
Reddit supplies recurring pain and counterexamples; GitHub, papers, and official
documentation verify implementation and adoption. User DNA ranks personal adjacency
but never determines truth.

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 合成跨源证据，驱动 Inbox → Watch → Verify → Build/Drop 生命周期 | 单源深挖（那是 specialist skills 的事）|
| 捕获弱信号、评分、硬门槛、源审计、周回顾 | 自动抓取 X、自动社交动作、UI/常驻调度 |
| 判定「证据状态」与「组合决策」两条线 | 让 user_dna 直接写入证据强度或成熟度 |

核心原则：**单源交给专家，跨源交给 radar；证据决定成熟度，决策决定阶段。**

## 路由 (Routing)

先判断请求属于哪一类，再决定用哪个 skill。跨源才走 `concept-radar`。

| 请求 | 路由 |
|------|------|
| 只学 X / 建 X 知识库 | `twitter-learning` |
| 找值得回复/讨论的推文、设计回复 | `twitter-discussion` |
| 只挖 Reddit 痛点/付费意愿 | `reddit-opportunity` |
| 只发现/评估 GitHub repo | `repo-trend` |
| 跨源弱信号、假设+证据、验证想法、生命周期 | **`concept-radar`**（本 skill）|

`twitter-learning` 的**被选中发现**可以进入跨源验证（feed 进 `concept-radar`），
但方向不可逆：`concept-radar` 不反向把单源学习任务派回 `twitter-learning`。

## 生命周期 (Lifecycle)

一个概念走一条流水线，每个阶段由硬门槛推进，不允许静默跳过：

```text
Inbox ──► Watch ──► Verify ──► Build ──► Drop（或持续验证）
 弱信号    聚焦观察   证据充分   最小实验   证伪/否决
```

| Mode | 做什么 | 触发 |
|------|--------|------|
| `capture` | 捕获一条弱信号为候选概念卡片 | "记下这个想法" / 手动粘贴 |
| `scan` | 按雷达配置扫源，聚合证据，更新卡片 | "扫一遍 agent-reliability" |
| `verify` | 对某概念补齐证据、过验证门槛 | "验证这个概念" |
| `review` | 周回顾：读 Review 事件、判定推进/否决 | "本周雷达回顾" |
| `build` | 通过硬门槛后生成最小实验 / FDE-Gym 场景 | "把它变成最小实验" |
| `source-audit` | 审计各源覆盖、缺口、证据独立性 | "审计一下源覆盖" |

每个 mode 都通过 JSON 契约与 Python CLI 交互：CLI 负责确定性 schema、持久化、
评分、硬门槛；你负责检索编排 + 语义判断。

## 关键边界

- **证据不可变**：更正追加一条取代记录，绝不改历史。
- **一个 ID 一个当前快照**：更新原子。
- **成熟度 ≠ 阶段**：成熟度描述证据状态；阶段描述组合决策。
- **独立性去重**：转发/引用同一上游主张共享 `independence_key`。
- **`user_alignment` 只改优先级**：不改证据强度，不改成熟度。
- **Build 硬门槛**：两种源类型 + 两条独立证据链 + 已审阅的反证 + 有界最小实验，四者缺一不可。

完整契约见 `references/schema.md`。

## Reference Files

- `references/schema.md` — 四个规范契约（ConceptCard / ConceptEvidence / RadarReview / RadarRunPayload）与六条不变量

Python CLI 契约（Pydantic 模型、JSON schema）由代码维护，与此处人类可读 schema 保持同源。
