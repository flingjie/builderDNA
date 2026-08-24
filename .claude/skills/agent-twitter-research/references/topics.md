# 研究主题与搜索词

这是「搜什么」。三大主题 + 三类搜索角度 + 高价值作者画像。每天不必全搜——按当日重点选 2-4 个主题词展开。

## 三大研究主题

### Agent Engineering

Agent Architecture · Agent Runtime · Agent Harness · Agent Loop · Agent Graph · Agent Evaluation · Agent Reliability · Agent Memory · Agent Context Engineering · Agent Observability · Agent Replay · Multi-Agent · Tool Use · MCP · Computer Use

### Agent Solution / FDE

AI Solution Architecture · AI Solution Engineering · Forward Deployed Engineer · Customer Engineering · Enterprise AI · AI Consulting · AI Transformation · AI Workflow · AI Automation · Production Agent

### AI Engineering

LLM Engineering · Coding Agent · Claude Code · Codex · Gemini CLI · OpenAI · Anthropic · Open Source Agent · Vibe Coding · Evaluation / Evals · Production AI

## 三类搜索角度

不同角度捞到不同质量的内容。优先「Experience」与「Problem」，再补「Topic」。

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

不要只丢单个名词。按「主题 + 目标 + 限定」构造，并利用原始 X 操作符限定时间与语言：

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

优先关注并定向扫其推文（`opencli twitter tweets <username>`）：

- Agent Framework 作者
- AI Infra 工程师
- AI Researcher
- Founder
- FDE / Customer Engineer / AI Engineer
- 开源项目作者
- 经常分享真实生产经验的人

判断依据是**内容本身**（一手经验、数据、代码、失败案例），不是粉丝数。`Likes ≠ Quality · Views ≠ Insight · Followers ≠ Expertise`。
