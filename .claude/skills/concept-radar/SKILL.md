---
name: concept-radar
description: >
  Cross-source concept lifecycle radar that turns weak signals into validated,
  falsifiable builds. Use when the user wants to track an idea from a hunch to
  evidence across multiple sources ("validate an idea", "weak signals to
  validated builds", "hypothesis and evidence", "should I build or drop this",
  "concept radar", "track this concept", "cross-source signal", "雷达", "验证一个想法"),
  or asks to capture, scan, verify, review, build, or source-audit a concept,
  or to run / resume a full radar cycle ("run the concept radar loop",
  "继续跑概念雷达", "resume my radar run").
  Owns cross-source synthesis and the Inbox → Watch → Verify → Build/Drop
  lifecycle. Single-source requests route to the specialist skills instead:
  X learning → twitter-learning (X may also surface public problem clues),
  Reddit pain/opportunity discovery → reddit-opportunity, GitHub-only
  discovery → repo-trend. X reply/engagement
  and customer outreach are out of scope for this project. Deterministic schemas, persistence, scoring, and gates live in the
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
| 判定「证据状态」与「组合决策」两条线 | 让用户画像直接写入证据强度或成熟度 |

核心原则：**单源交给专家，跨源交给 radar；证据决定成熟度，决策决定阶段。**

## 路由 (Routing)

先判断请求属于哪一类，再决定用哪个 skill。跨源才走 `concept-radar`。

| 请求 | 路由 |
|------|------|
| 只学 X / 建 X 知识库（X 也可提供公开问题线索） | `twitter-learning` |
| 只挖 Reddit 痛点/潜在需求 | `reddit-opportunity` |
| 只发现/评估 GitHub repo | `repo-trend` |
| 跨源弱信号、假设+证据、验证想法、生命周期 | **`concept-radar`**（本 skill）|

X 回复/互动（找值得回复的推文、设计回复）与获客**超出本项目范围**——没有对应
Skill，直接说明不在范围内，不要路由到任何 Skill。

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

## 完整生命周期循环 (Full Lifecycle Loop)

需要跑一轮完整雷达时，按下面顺序手工编排——状态与门槛在 CLI，检索与语义判断在本 skill。中断后从最近未完成步骤继续；不另设 checkpoint 引擎。

1. **Capture / Import** — 用专家 skill 采集证据，经 `builderdna concept capture` 写入候选卡片（必要时 `--into <ID>` 合并）。
2. **Scan** — `builderdna radar scan --radar <name>` 按雷达配置聚合证据。
3. **Verify** — `builderdna radar verify <CONCEPT_ID>` 过硬门槛；缺口由 `repo-trend` / `reddit-opportunity` / `twitter-learning` 补证据后再 verify。
4. **Decide** — `builderdna concept move` / `score` / `outcome` 推进或否决；Build 前必须满足硬门槛。
5. **Experiment** — `builderdna radar experiment <CONCEPT_ID> --format fde-gym` 生成有界最小实验。
6. **Review** — `builderdna radar review`（或 `concept review`）做周回顾与校准。
7. **Source-audit** — `builderdna radar source-audit --radar <name>` 审计覆盖与独立性。

停止条件（不要伪造证据、不要盲重试）：认证失败、CLI 返回 `ok: false`、模糊合并候选需用户消歧、任何外部平台写操作（发帖/PR/推送）一律禁止。本 skill 不自调度 cron/daemon。

## Reference Files

- `references/schema.md` — 四个规范契约（ConceptCard / ConceptEvidence / RadarReview / RadarRunPayload）与六条不变量

Python CLI 契约（Pydantic 模型、JSON schema）由代码维护，与此处人类可读 schema 保持同源。
