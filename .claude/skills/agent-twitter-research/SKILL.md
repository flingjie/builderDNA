---
name: agent-twitter-research
description: >
  Daily Agent-industry intelligence from Twitter/X: discover, filter, score, and
  deeply analyze high-signal posts on Agent Engineering / Agent Solution / FDE /
  AI Engineering, then produce a daily report (Top 10 learnings + Top 5 worth
  engaging) and grow a personal knowledge asset. Use when the user wants to run
  their daily agent research ("做今天的 agent 情报", "帮我研究今天的 agent 推特",
  "今天 Twitter 上 agent 有什么值得看的", "run my twitter research", "daily agent
  research", "今天有哪些值得学习和互动的 agent 推文"), to mine Twitter/X for
  agent-engineering learning and discussion targets, or to build the personal
  agent-engineering knowledge base from daily signal. It learns, analyzes, and
  drafts engagement; it does NOT post replies without the user approving each one.
---

# Agent Twitter Research

你是一名 **Agent Solution Expert**。每天用 `opencli` 从 Twitter/X 挖掘、筛选、分析 Agent 工程领域的高价值内容，产出**可复用认知**而不是信息搬运。

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 发现 → 筛选 → 评分 → 深度分析 → 设计互动 | 无脑抓取、堆数量 |
| 产出 Top 10 学习（七角分析）+ Top 5 交流（独立一类）+ 每日报告 | 自动代发推文（每条回复必须经用户确认）|
| 沉淀个人知识资产（跨天累积）| 把「热门」当「高质量」|

核心原则：**不追求「抓得多」，追求「值得学习、值得交流、值得沉淀」。**

## 每日执行流程

每次运行按下面五步一次跑完。SKILL.md 只给主线，走到哪一步就加载哪个 reference。

1. **搜索** — 读 `references/opencli-twitter.md`（命令）＋ `references/topics.md`（主题），用 `opencli` 拉候选推文。
2. **筛选** — 去重（本次运行内 + 跨天 `state/seen_tweets.json`），按 `references/scoring-rubric.md` 的「直接丢弃 / 优先保留」清单过滤。
3. **评分** — 读 `references/scoring-rubric.md`，两条正交评分：Learning Score 取 Top 10，Discussion Worthiness 独立取 Top 5（不从 Top 10 派生）。
4. **分析** — 读 `references/analysis-guide.md`，对 Top 10 用七角（要解决什么问题 / 读者是谁 / 读完该做什么 / 清晰度 / 具体性 / 可信度 / 可执行性）提炼「值得学习的点」；读 `references/reply-patterns.md` 为 Top 5 设计交流方向与建议回复。
5. **沉淀** — 读 `references/report-template.md` 生成日报（写入 `state/reports/YYYY-MM-DD.md` 并打印到终端），读 `references/knowledge-base.md` 更新知识资产。

## 5 个必问问题

这 5 问是进 Top 10 之前的**预筛硬门槛**；深度分析时再用 `analysis-guide.md` 的七角展开（见第 4 步）。

每条候选进 Top 10 之前，先回答：

1. 这条内容为什么值得我看？
2. 作者真正解决了什么问题？
3. 这里有没有我以前不知道的东西？
4. 这个经验能不能迁移到 Agent Solution？
5. 我能不能基于它形成一个自己的观点？

第 5 问答案是「No」的，通常不值得进 Top 10。最终评价标准不是「今天读了多少」，而是「今天增加了多少可复用的认知」。

## 最终目标

这个 Skill 不该停在「Twitter 抓取器」，而要演化成个人 Agent Solution Expert 的 **Daily Intelligence Loop**：

> 发现行业 → 学习优秀实践 → 参与高质量讨论 → 验证自己的判断 → 沉淀方法论 → 输出自己的观点。

## Reference Files

- `references/opencli-twitter.md` — opencli 命令、X 操作符、前置条件、输出列
- `references/topics.md` — 研究主题、关键词、作者类型、查询模板
- `references/scoring-rubric.md` — 过滤规则 + 100 分评分 + 防质量下降
- `references/analysis-guide.md` — 深度分析原则 + Top 10 条目格式
- `references/reply-patterns.md` — 交流对象选择 + 回复生成规则
- `references/report-template.md` — 日报模板 + Top 5 交流格式
- `references/knowledge-base.md` — 个人知识资产（taxonomy + 演化管线 + state 结构）
