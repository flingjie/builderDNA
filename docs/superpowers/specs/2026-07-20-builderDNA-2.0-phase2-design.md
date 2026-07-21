# BuilderDNA 2.0 Phase 2: Pain Mining — Design Spec

## Date
2026-07-20

## Goal
在 Phase 1 Trend Radar 基础上，自动对趋势 Top 5 repo 采集 Issue，通过 LLM 语义评分和聚类，
发现开发者社区的真实痛点模式，输出 PainCluster 报告。

## 核心原则
不展示原始 Issue → 展示提炼后的**痛点模式 + 根因 + 影响范围**。

## 架构增量

```
Phase 1 (已有)                              Phase 2 (新增)
─────────────────                          ─────────────────
backend/engine/radar.py                     backend/engine/pain.py
  └─ run_radar()                                ├─ fetch_issues(client, repo)
       │                    ──调用──▶             ├─ score_issues(issues, llm)
       │                                         ├─ cluster_pains(issues, llm)
       │                                         └─ run_pain_mining(client, store, llm)
       │                                               │
       ▼                                               ▼
TrendSnapshot                                  PainSnapshot
  └─ .topics[]                                     └─ .clusters[]
       └─ .top_repos[]                                  └─ .evidence[]
            └─ RepoTrend                                   └─ PainIssue
```

## 新增模型 (`backend/models/pain.py`)

```python
class PainIssue(BaseModel):
    repo: str
    issue_number: int
    title: str
    body: str                     # truncated to 500 chars
    comments: int
    participants: int
    pain_score: float             # LLM rated 1-5, aggregated
    labels: list[str]
    url: str

class PainCluster(BaseModel):
    id: str                       # auto-generated hex
    title: str                    # "Agent State Debugging"
    severity: float               # aggregated pain score
    frequency: int                # issue count
    description: str              # LLM 根因摘要
    evidence: list[PainIssue]     # top 5
    affected_repos: list[str]

class PainSnapshot(BaseModel):
    id: str
    domain: str
    created_at: datetime
    clusters: list[PainCluster]
    issue_count: int
    repos_analyzed: list[str]
```

## 新增 API

```
GET /api/pain?domain=agent
  → { clusters, issue_count, repos_analyzed }
```

## 集成点

- `run_radar()` 完成后，提取跨所有 topic 的 Top 5 repos → 调用 `run_pain_mining()`
- 结果存入独立的 `PainSnapshot`（独立 SQLite 表或 JSON 文件）
- `/api/pain` 从 PainStore 读取最新快照

## 算法

```
Pain Score per issue = LLM("rate 1-5 pain level, be strict")
                      × log(comments + 1)
                      × log(participants + 1)

Clustering = LLM("group N issues into 3-5 pain patterns,
                  name each with 5 words max,
                  describe root cause in 1 sentence,
                  tag affected repos")
```

## 文件变更

| 文件 | 操作 |
|------|------|
| `backend/engine/pain.py` | 新增 |
| `backend/models/pain.py` | 新增 |
| `backend/store/pain_store.py` | 新增 |
| `backend/router/radar.py` | 修改: 添加 /api/pain 端点 |
| `backend/engine/radar.py` | 修改: run_radar 末尾调用 pain mining |
| `frontend/src/app/opportunities/page.tsx` | 修改: 真实数据 |
| `frontend/src/components/opportunity/OpportunityCard.tsx` | 新增 |
| `frontend/src/components/opportunity/OpportunityGrid.tsx` | 新增 |

## Phase 2 范围边界

| 包含 | 不包含 (Phase 3) |
|------|---------------------|
| Issue 采集 (open, top 20 per repo) | Discussion/Pull Request 采集 |
| LLM 情绪评分 (1-5) | 多轮讨论深度分析 |
| LLM 痛点聚类 (3-5 patterns) | HDBSCAN/Embedding 聚类 |
| /api/pain 端点 | React Flow 证据图 |
| opportunities 页面真实数据 | Signal Graph / 机会推演引擎 |
