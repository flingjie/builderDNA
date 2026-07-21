# BuilderDNA 2.0 Phase 3: Opportunity Intelligence — Design Spec

## Date
2026-07-20

## Goal
在 Phase 1 (Trend Radar) 和 Phase 2 (Pain Mining) 基础上，用 LLM 作为"AI VC Strategist"进行 Chain-of-Thought 推理，识别具体的产品/商业机会，输出 OpportunityCard，完成 BuilderDNA 2.0 完整闭环。

## 核心原则
> 回答终极问题："在 AI 基础能力日新月异的今天，我明天到底应该 Coding 什么？"

## 架构

```
run_radar()
  ├─ Phase 1: Trend Detection → TrendSnapshot (已有)
  ├─ Phase 2: Pain Mining → PainSnapshot (已有)
  └─ Phase 3: Opportunity Engine → OpportunitySnapshot (新增)
        │
        ├─ 输入: TrendSnapshot + PainSnapshot
        ├─ LLM Chain-of-Thought 推理
        └─ 输出: 3-5 OpportunityCard
```

## 新增模型 (`backend/models/opportunity.py`)

```python
class OpportunityEvidence(BaseModel):
    trends: list[str] = Field(default_factory=list)     # topic names
    pain_clusters: list[str] = Field(default_factory=list)  # pain titles
    key_issues: list[str] = Field(default_factory=list)   # GitHub URLs
    key_repos: list[str] = Field(default_factory=list)    # repo full_names

class OpportunityCard(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str                        # "Agent Replay Infrastructure"
    why_now: str                      # "Agent enters production phase"
    problem: str                      # "Cannot reproduce agent failures"
    evidence: OpportunityEvidence = Field(default_factory=OpportunityEvidence)
    existing_solutions: list[str] = Field(default_factory=list)
    gap: str = ""                     # "No deterministic replay"
    mvp: str = ""                     # "1. Capture 2. Replay 3. Compare"
    score: float = 0.0               # 1-10
    risk: Literal["low", "medium", "high"] = "medium"

class OpportunitySnapshot(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cards: list[OpportunityCard] = Field(default_factory=list)
```

## 新增 API

```
GET /api/opportunities?domain=agent
  → { cards: [OpportunityCard, ...] }

GET /api/evidence/:opportunity_id
  → { card: OpportunityCard, trends: [...], pains: [...], issues: [...] }
```

## LLM Prompt Template

```
You are a top-tier AI venture strategist. Identify 3-5 product opportunities
from these tech signals.

TREND SIGNALS:
{topic_name}: stage={stage}, velocity={velocity}, top repos={repos}

PAIN SIGNALS:
{pain_title}: severity={severity}, root_cause={description}, affected={repos}

For each opportunity, reason step by step:
1. WHY NOW
2. WHY NOT EXISTING SOLUTIONS
3. MVP
4. SCORE (1-10) and RISK (low/medium/high)

Return JSON: {"opportunities": [{title, why_now, problem,
  evidence: {trends:[], pain_clusters:[]},
  existing_solutions:[], gap, mvp, score, risk}, ...]}
```

## 集成点

`run_radar()` 在 pain mining 后调用 opportunity engine，完整管道：
```
Trend → Pain → Opportunity → 一次 CLI 调用全产出
```

## 文件变更

| 文件 | 操作 |
|------|------|
| `backend/models/opportunity.py` | 新增 |
| `backend/engine/opportunity.py` | 新增 |
| `backend/store/opportunity_store.py` | 新增 |
| `backend/router/radar.py` | 修改: /api/opportunities 真实数据, /api/evidence/:id |
| `backend/engine/radar.py` | 修改: run_radar 末尾调用 opportunity engine |
| `frontend/src/app/opportunities/page.tsx` | 修改: OpportunityCard 展示 |
| `frontend/src/app/evidence/[id]/page.tsx` | 修改: 证据详情 |
| `frontend/src/components/opportunity/OpportunityCard.tsx` | 新增 |
| `frontend/src/lib/types.ts` | 添加类型 |
| `frontend/src/lib/api.ts` | 添加 fetchOpportunities, fetchEvidence |

## Phase 3 范围边界

| 包含 | 不包含 |
|------|--------|
| LLM 机会推演 (3-5 cards) | 机会矩阵公式计算 |
| 文本证据面板 | React Flow 图可视化 |
| /api/opportunities + /api/evidence | Neo4j 图数据库 |
| pipeline 集成 | 独立的 graph 引擎 |
