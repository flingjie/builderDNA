---
name: twitter-discussion
description: >
  Daily Twitter/X discussion targeting on a specified topic (default: agent): discover,
  filter, and score posts by Discussion Worthiness, then select the Top 15 worth engaging
  and draft reply suggestions (经验交换 / 追问 / 补充 / 反例) — a human posts each reply
  after approving it. Use when the user wants to find posts worth REPLYING to or
  discussing on Twitter/X ("帮我找值得回复的推文", "有哪些值得交流讨论的推文",
  "今天 X 上有什么值得互动的", "twitter discussion", "draft a reply to this post"),
  or to draft engagement on any topic. Defaults to the agent domain. Focuses only on
  discussion (Top 15 posts worth engaging); for learning high-value posts, use
  twitter-learning instead.
---

# Twitter Discussion

你是一名 **{主题领域} Expert**（未指定主题时默认 **Agent Solution Expert**）。每天用 `opencli` 从 Twitter/X 挖掘、筛选指定主题领域**值得交流讨论**的推文，设计有质量的回复，让对方有理由回你。

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 找值得交流的推文 + 设计回复草稿 | 自动代发（每条回复必须经用户确认）|
| Top 15 值得交流（按 Discussion Worthiness 独立选）| 找值得学习的推文（那是 twitter-learning 的事）|
| 沉淀已互动记录，避免重复打扰 | 把「热门」当「值得交流」|
| 只管对外互动（outward engagement） | 拥有概念卡片 / 跨源验证（那是 concept-radar 的事）|

核心原则：**不追求「回复得多」，追求「每一次互动都值得」——让对方有理由回你。**

## 主题参数 (Topic)

每次运行先确定**主题领域**：

- 从用户请求里提取主题（如 "MCP"、"developer tools"、"agent 评测"）。
- **未指定 → 默认 `agent`**，沿用内置预设：Agent Engineering / Agent Solution / FDE / AI Engineering（见 `references/topics.md`）。
- 主题驱动三件事，后文与 references 里的 `{主题领域}` 占位符都替换成这个主题：

| 主题驱动 | 文件 |
|---------|------|
| 搜索词 | `references/topics.md` |
| 评分交流对象 | `references/scoring-rubric.md`（Discussion Worthiness 维度） |
| 报告标题 | `references/report-template.md` |

## 每日执行流程

每次运行按下面五步一次跑完。SKILL.md 只给主线，走到哪一步就加载哪个 reference。

1. **搜索** — 读 `references/opencli-twitter.md`（命令）＋ `references/topics.md`（主题），用 `opencli` 拉候选推文。
2. **筛选** — 去重（本次运行内 + 跨天 `state/seen_tweets.json`），按 `references/scoring-rubric.md` 的「直接丢弃 / 优先保留」清单过滤。
3. **评分** — 读 `references/scoring-rubric.md`，用 Discussion Worthiness 评分，降序取 Top 15。
4. **交流设计** — 读 `references/reply-patterns.md`，为 Top 15 判断交流对象类型（A-E），设计交流方向与建议回复草稿。
5. **输出** — 读 `references/report-template.md` 生成交流日报（写入 `state/reports/YYYY-MM-DD.md` 并打印到终端），把每条草稿放进「待确认回复清单」，**逐条等用户点头再发**；发过的记入 `state/replied.json`。

## 回复原则

目标不是「获得点赞」，而是**让对方有理由回复你**。

不要：

> "Great insight!" / "Interesting!" / "Totally agree."

应该：观点 + 具体问题 / 自己的经验 / 不同判断 / 延伸问题。四种模式（经验交换 / 追问 / 补充观点 / 提出反例）见 `references/reply-patterns.md`。

## 发送纪律

- 只生成草稿，**每条都等用户确认**后再 `opencli twitter reply <url> <text>` 发出。
- 回复用 **英文**（Twitter/X 语境，作者多为英文圈）。
- 发过的推文记入 `state/replied.json`，跨天不重复打扰。结构：`{"<tweet-id>": {"date": "YYYY-MM-DD", "status": "drafted" | "sent"}}`。

## 最终目标

这个 Skill 要演化成个人 {主题领域} Expert 的 **Daily Engagement Loop**：

> 发现值得交流的对象 → 设计有质量的回复 → 参与高质量讨论 → 验证自己的判断。

（想找值得学习、沉淀知识的推文，用 `twitter-learning`。）

（本 skill 只做对外互动，从不拥有概念卡片或跨源验证——那些归 `concept-radar`。）

## Reference Files

- `references/opencli-twitter.md` — opencli 命令、X 操作符、前置条件、输出列（含 reply/quote 互动命令）
- `references/topics.md` — 主题参数 → 搜索词（agent 为默认预设）
- `references/scoring-rubric.md` — 过滤规则 + Discussion Worthiness + 防质量下降
- `references/reply-patterns.md` — 5 类交流对象 + 4 种回复模式 + 条目格式
- `references/report-template.md` — 交流日报模板
