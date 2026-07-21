# BuilderDNA 2.0 Phase 1: Trend Radar — Design Spec

## Date
2026-07-20

## Goal
从第一性原理出发，将 BuilderDNA 从"静态个人履历提取"升级为"技术供需能量场捕捉引擎"。
Phase 1 实现 Trend Radar：按领域（domain）检测 GitHub 上加速增长的技术 Topic 和 Repo，
以二阶加速度（非静态总量）为核心算法，输出 CLI 摘要 + Next.js 交互式 Web 报告。

## 核心原则

> 不告诉 Builder "发生了什么"，而是告诉 Builder "应该关注什么、为什么、下一步做什么"。

## 架构

```
Next.js 14 + shadcn/ui + Tailwind + ECharts + React Flow (frontend)
        │  HTTP REST
FastAPI (backend)
        │
    Radar Engine
        │
    GitHubClient (async, cached, rate-limited)
        │
    GitHub API
```

## 项目结构

```
BuilderDNA/
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── router/
│   │   └── radar.py             # /api/radar, /api/trends
│   ├── engine/
│   │   └── radar.py             # compute_topic_score, aggregate_trends
│   ├── models/
│   │   └── trend.py             # DomainConfig, TopicTrend, RepoTrend, TrendSnapshot
│   ├── store/
│   │   └── trend_store.py       # SQLite trend snapshots
│   └── dependencies.py          # get_github_client()
│
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── layout.tsx       # sidebar + nav
│       │   ├── page.tsx         # / Executive Radar
│       │   ├── trends/
│       │   │   └── page.tsx     # /trends Trend Landscape
│       │   ├── opportunities/
│       │   │   └── page.tsx     # /opportunities (Phase 2/3)
│       │   └── evidence/
│       │       └── [id]/
│       │           └── page.tsx # /evidence/:id (Phase 3)
│       ├── components/
│       │   ├── radar/
│       │   │   ├── RadarCard.tsx
│       │   │   └── RadarGrid.tsx
│       │   ├── charts/
│       │   │   ├── TrendMap.tsx        # ECharts 象限图
│       │   │   └── TrendSparkline.tsx
│       │   ├── graph/
│       │   │   └── EvidenceFlow.tsx    # React Flow (Phase 3)
│       │   └── ui/                     # shadcn/ui
│       ├── lib/
│       │   ├── api.ts
│       │   └── types.ts
│       └── hooks/
│           └── use-radar.ts
│
├── collect/                     # 保留现有 (1.0)
├── cli.py                       # 保留，增强 radar 命令
└── config.yaml                  # 新增 domains 配置
```

## 数据模型

```python
class DomainConfig(BaseModel):
    name: str                              # "agent"
    topics: list[str]                      # ["mcp", "langchain", ...]
    window_days: int = 60

class RepoTrend(BaseModel):
    full_name: str                         # "modelcontextprotocol/servers"
    stars: int
    stars_delta: int                       # 周期内新增
    forks: int
    contributors: int
    contributor_growth: float
    velocity: float                        # stars/day
    trend_score: float                     # 综合趋势分

class TopicTrend(BaseModel):
    topic: str                             # "mcp"
    stage: Literal["emerging","accelerating","mainstream","declining"]
    confidence: float                      # 0-1
    growth_velocity: float
    evidence_count: int
    top_repos: list[RepoTrend]             # Top 5

class TrendSnapshot(BaseModel):
    id: str
    domain: str
    created_at: datetime
    window_days: int
    topics: list[TopicTrend]
```

## API

```
GET /api/health → {"status": "ok"}

GET /api/radar?domain=agent&window=60&refresh=false
  → TrendSnapshot + rate_limit info

GET /api/trends?domain=agent&topic=mcp
  → topic detail with full repo list

GET /api/opportunities?domain=agent  → [] (Phase 2/3)
GET /api/evidence/:id                → {nodes, edges} (Phase 3)
```

## 前端路由

| 路由 | 内容 | Phase |
|------|------|-------|
| `/` | Executive Radar (RadarGrid + TrendMap) | 1 |
| `/trends` | Trend Landscape (全屏象限图 + 时间线 + 可排序表格) | 1 |
| `/opportunities` | Opportunity Feed | 2/3 |
| `/evidence/[id]` | React Flow 证据图 | 3 |

## 算法（混合策略）

**首次运行（无快照）——一阶近似：**
```
velocity = stars / max(1, days_since_first_release)
trend_score = velocity × log₁₀(forks + 1) × log₁₀(contributors + 1)
```

**后续运行（有快照）——二阶加速度：**
```
velocity_now = (stars_current - stars_last) / Δt
velocity_prev = (stars_last - stars_prev_snapshot) / Δt
acceleration = (velocity_now - velocity_prev) / Δt
trend_score = acceleration × log₁₀(forks + 1) × log₁₀(contributor_growth + 1)
```

**Topic 聚合：** 同 topic 下所有 repo trend_score 的加权平均。

**Stage 判定：**
- >= 80: accelerating
- >= 50: emerging
- >= 20: mainstream
- < 20: declining

## 领域配置 (config.yaml)

```yaml
domains:
  agent:
    topics:
      - mcp
      - langchain
      - agent-protocol
      - llm
      - rag
      - agent-framework
      - tool-calling
      - multi-agent
```

## 输出

### CLI
```bash
$ builderdna radar agent

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 BuilderDNA Radar · Agent
 2026-07-20 · Last 60 Days
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 Top 3

 1  Agent Evaluation     92  🚀
 2  MCP Infrastructure    85  🚀
 3  Agent Memory          71  ↑

📈 Signals

 ↑ Browser Agent      +142 repos
 ↑ Agent Observability +89 repos

[GitHub] calls=24, cached=18
📊 http://localhost:8000
```

### Web
交互式仪表板，含 Radar Cards、ECharts 象限图、暗色 Bloomberg 风格主题。

## 技术栈
- **Backend:** FastAPI (Python 3.12+)
- **Frontend:** Next.js 14 + TypeScript + Tailwind CSS + shadcn/ui
- **Charts:** ECharts (象限图、趋势图)
- **Graph:** React Flow (证据图, Phase 3)
- **Existing:** httpx (async GitHub client), SQLite (snapshots)

## Phase 1 范围边界

| 包含 | 不包含 (Phase 2/3) |
|------|---------------------|
| Topic+Repo 趋势检测 | Issue/Discussion 采集 |
| 一阶+二阶速度算法 | NLP 情绪分 / 痛苦指数 |
| CLI 摘要 + Web 仪表板 | Pain Mining | 
| 趋势快照 SQLite 存储 | Signal Graph / React Flow 证据图 |
| opportunities 端点返回 [] | LLM 机会推演 |
