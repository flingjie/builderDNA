# 研究主题与搜索词（主题参数）

这是「搜什么」。先确定主题领域，再把主题映射成搜索词。**未指定主题 → 默认 `agent`**（见下方默认预设）。任意主题都用同一套「三类搜索角度 + 查询构造模板 + 作者画像」展开——只有关键词列表不同。

## 默认预设：Agent

主题为 `agent` 时，三大子主题如下。每天不必全搜——按当日重点选 2-4 个主题词展开。

### Agent Engineering

Agent Architecture · Agent Runtime · Agent Harness · Agent Loop · Agent Graph · Agent Evaluation · Agent Reliability · Agent Memory · Agent Context Engineering · Agent Observability · Agent Replay · Multi-Agent · Tool Use · MCP · Computer Use

### Agent Solution / FDE

AI Solution Architecture · AI Solution Engineering · Forward Deployed Engineer · Customer Engineering · Enterprise AI · AI Consulting · AI Transformation · AI Workflow · AI Automation · Production Agent

### AI Engineering

LLM Engineering · Coding Agent · Claude Code · Codex · Gemini CLI · OpenAI · Anthropic · Open Source Agent · Vibe Coding · Evaluation / Evals · Production AI

## 任意主题的构造方法

研究非 agent 主题时，把主题当成「主题领域」，按同一结构展开：

1. **划分子主题** — 把主题拆成 2-4 个可独立搜索的领域（对应 agent 预设的三大子主题）。例如主题 `MCP` 可拆：MCP 协议设计 / MCP 生态与工具 / MCP 生产实践。
2. **给每个子主题列关键词** — 领域名 + 常见变体 + 竞品/工具名。
3. **套用下方三类搜索角度**（Topic / Problem / Experience）与查询模板——这部分主题无关，直接复用。
4. **作者画像** 同样主题无关：优先一手经验者（见下方），判断依据是内容本身而非粉丝数。

示例（主题 `MCP`）：

```text
子主题：MCP 协议设计 → MCP / Model Context Protocol / MCP spec / MCP server / MCP client
子主题：MCP 生态与工具 → MCP registry / MCP tools / MCP marketplace / MCP gateway
子主题：MCP 生产实践 → MCP in production / we built an MCP / MCP security / MCP auth
```

## 三类搜索角度

不同角度捞到不同质量的内容。优先「Experience」与「Problem」，再补「Topic」。下面示例词是 `agent` 预设——研究其他主题时，把 `agent` 换成当前主题的关键词即可，角度结构不变。

### Topic（主题词，宽）

```text
agent engineering / agent harness / agent loop / agent evaluation / agent reliability
context engineering / AI agent production / AI agent architecture / multi-agent
coding agent / Claude Code / Codex agent / MCP / computer use
forward deployed engineer / AI solution engineer / customer engineer AI / enterprise agent
```

### Problem（问题型，容易出真认知）

```text
agent failure / agent production failure / agent reliability / agent evals
agent benchmark / agent debugging / agent loop failure / agent hallucination
agent tool failure / agent context failure / agent memory failure / agent architecture problem
```

### Experience（真实经验，最优先）

```text
we built an agent / we shipped an agent / lessons learned agent
what we learned building agents / production agents / agent in production
I built an agent / agent architecture lessons
```

## 查询构造模板

不要只丢单个名词。按「主题 + 目标 + 限定」构造，并利用原始 X 操作符限定时间与语言（下例是 `agent` 预设，换主题时替换关键词）：

```text
"agent evaluation" lang:en since:<7天前>
"we built an agent" lang:en since:<7天前>
"context engineering" lang:en since:<7天前>
(agent OR "AI agent") "in production" lang:en -filter:retweets since:<7天前>
```

- 用 `since:YYYY-MM-DD` 限定近 1-7 天，避免旧内容。
- 用 `-filter:retweets`（即 `--exclude retweets`）去转发噪音。
- 用 `lang:en` 优先英文一手内容；中文作者内容按需单独搜。

## 高价值作者画像

优先关注并定向扫其推文（`opencli twitter tweets <username>`）。下面是 `agent` 预设的作者类型；其他主题按同类思路替换（领域作者 / 基础设施工程师 / 研究者 / 创始人 / 一线从业者 / 开源作者 / 常分享一手经验者）：

- Agent Framework 作者
- AI Infra 工程师
- AI Researcher
- Founder
- FDE / Customer Engineer / AI Engineer
- 开源项目作者
- 经常分享真实生产经验的人

判断依据是**内容本身**（一手经验、数据、代码、失败案例），不是粉丝数。`Likes ≠ Quality · Views ≠ Insight · Followers ≠ Expertise`。
