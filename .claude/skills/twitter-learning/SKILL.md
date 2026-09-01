---
name: twitter-learning
description: >
  Daily Twitter/X learning on a specified topic (default: agent): discover, filter,
  and score high-signal posts by Learning Score, then deeply analyze the Top 10 with
  a 7-angle framework to extract transferable insights, and grow a personal knowledge
  asset. Use when the user wants to LEARN from Twitter/X on a topic ("做今天的 X 情报",
  "帮我研究 Y 的推特", "今天 X 上有什么值得学的", "有哪些值得学习的高质量推文",
  "twitter learning", "daily twitter learning"), or to build a topic-specific knowledge
  base from daily signal. Defaults to the agent domain (Agent Engineering / Agent
  Solution / FDE / AI Engineering). Focuses only on learning (Top 10 high-value posts);
  for finding posts worth replying to or discussing, use twitter-discussion instead.
---

# Twitter Learning

你是一名 **{主题领域} Expert**（未指定主题时默认 **Agent Solution Expert**）。每天用 `opencli` 从 Twitter/X 挖掘、筛选、分析指定主题领域**值得学习**的高价值内容，产出**可复用认知**而不是信息搬运。

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 发现 → 筛选 → 评分 → 深度分析（七角） | 无脑抓取、堆数量 |
| 产出 Top 10 学习日报 + 沉淀个人知识资产 | 把「热门」当「高质量」 |
| 提炼可迁移到 {主题领域} 的认知 | 找值得回复 / 讨论的推文（那是 twitter-discussion 的事）|
| 只学 X / 建 X 知识库的请求走这里 | 跨源验证 / 概念卡片（那是 concept-radar 的事）|

核心原则：**不追求「抓得多」，追求「值得学习、值得沉淀」。**

## 主题参数 (Topic)

每次运行先确定**主题领域**：

- 从用户请求里提取主题（如 "MCP"、"developer tools"、"LLM evaluation"、"agent 评测"）。
- **未指定 → 默认 `agent`**，沿用内置预设：Agent Engineering / Agent Solution / FDE / AI Engineering（见 `references/topics.md`）。
- 主题驱动四件事，后文与 references 里的 `{主题领域}` 占位符都替换成这个主题：

| 主题驱动 | 文件 |
|---------|------|
| 搜索词 | `references/topics.md` |
| 评分迁移基准 | `references/scoring-rubric.md`（Transferability 维度） |
| 分析 persona | `references/analysis-guide.md`（"我是 {主题领域} Expert"） |
| 报告标题 + 知识库 taxonomy | `references/report-template.md` / `references/knowledge-base.md` |

## 每日执行流程

每次运行按下面五步一次跑完。SKILL.md 只给主线，走到哪一步就加载哪个 reference。

1. **搜索** — 读 `references/opencli-twitter.md`（命令）＋ `references/topics.md`（主题），用 `opencli` 拉候选推文。
2. **筛选** — 去重（本次运行内 + 跨天 `state/seen_tweets.json`），按 `references/scoring-rubric.md` 的「直接丢弃 / 优先保留」清单过滤。
3. **评分** — 读 `references/scoring-rubric.md`，用 Learning Score 评分，降序取 Top 10。
4. **分析** — 读 `references/analysis-guide.md`，对 Top 10 用七角（要解决什么问题 / 读者是谁 / 读完该做什么 / 清晰度 / 具体性 / 可信度 / 可执行性）提炼「值得学习的点」。
5. **沉淀** — 读 `references/report-template.md` 生成学习日报（写入 `state/reports/YYYY-MM-DD.md` 并打印到终端），读 `references/knowledge-base.md` 更新知识资产。

## 5 个必问问题

这 5 问是进 Top 10 之前的**预筛硬门槛**；深度分析时再用 `analysis-guide.md` 的七角展开（见第 4 步）。

每条候选进 Top 10 之前，先回答：

1. 这条内容为什么值得我看？
2. 作者真正解决了什么问题？
3. 这里有没有我以前不知道的东西？
4. 这个经验能不能迁移到 {主题领域}？
5. 我能不能基于它形成一个自己的观点？

第 5 问答案是「No」的，通常不值得进 Top 10。最终评价标准不是「今天读了多少」，而是「今天增加了多少可复用的认知」。

## 最终目标

这个 Skill 不该停在「Twitter 抓取器」，而要演化成个人 {主题领域} Expert 的 **Daily Learning Loop**：

> 发现行业 → 学习优秀实践 → 验证自己的判断 → 沉淀方法论 → 输出自己的观点。

（想找值得互动 / 讨论的推文、设计回复，用 `twitter-discussion`。）

（被选中的发现可以进入跨源验证——喂给 `concept-radar` 走 Inbox → Watch → Verify → Build/Drop；方向不可逆，`concept-radar` 不会把单源学习任务反向派回来。）

## Reference Files

- `references/opencli-twitter.md` — opencli 命令、X 操作符、前置条件、输出列
- `references/topics.md` — 主题参数 → 搜索词（agent 为默认预设；任意主题用同一套三类角度构造）
- `references/scoring-rubric.md` — 过滤规则 + 100 分 Learning Score + 防质量下降
- `references/analysis-guide.md` — 深度分析原则 + 七角 + Top 10 条目格式
- `references/report-template.md` — 学习日报模板
- `references/knowledge-base.md` — 个人知识资产（taxonomy + 演化管线 + state 结构）
