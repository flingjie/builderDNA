# BuilderDNA 2.0 系统重构设计

**日期**: 2026-07-21
**状态**: 已确认

---

## 1. 重构目标与原则

### 1.1 核心理念

BuilderDNA 2.0 的本质是 **技术供需能量场分析与决策自进化系统**。它通过捕捉 GitHub 生态中的**供给信号**（Repos, Commits, Releases, Stars）与**需求痛点信号**（Issues, Discussions），构建动态 **Signal Graph**，利用 **Human Control Plane** 与 **Builder Memory** 进行人机协同，持续输出高价值的技术趋势与创业机会。

### 1.2 重构原则

- **每步可运行** — 不一次性全部到位，Phase 间保持系统可用
- **保留不改稳的** — 现有 `GitHubClient`, `OpenAIClient`, `FastAPI`, `React 前端` 不重写
- **先迁后改** — 先复制到新目录结构，再在新位置重构

### 1.3 当前系统问题分析

| 问题 | 根因 | 解决方案 |
|------|------|---------|
| 两套 Opportunity/Insight 模型并存 | `models/` 和 `backend/models/` 各自定义 | 统一到 `signal/models.py` |
| 两套 store 系统 | SQLite JSON blob vs 关系型并存 | SQLite (CRUD) + DuckDB (分析) |
| LLM 聚类不稳定 | 每次聚类结果可能不同 | HDBSCAN 确定性聚类 + LLM 命名 |
| LLM 调用成本线性增长 | 每个 issue 过 LLM 打分 | embedding batch + 一次聚类 |
| 无人类反馈闭环 | 全自动，人只能事后看报告 | HCP + Builder Memory |
| 无关系建模 | 数据散落在独立 store 里 | Signal Graph (NetworkX) |
| 厂商追踪拼凑 | Discovery/Vendor 作为 engine 后置代码耦合在 radar 里 | 合并到 Trend Engine 作为统一趋势检测 |

---

## 2. 架构总览

```
                           +-------------------------------------+
                           |      GitHub / Community Sources      |
                           +-------------------------------------+
                                              |
                                              v
                           +-------------------------------------+
                           |     Collector & Signal Pipeline     |
                           +-------------------------------------+
                                              |
                                              v
                           +-------------------------------------+
                           |     Signal Lake & Vector Store      |
                           |     (DuckDB + SQLite + ChromaDB)     |
                           +-------------------------------------+
                                              |
     =========================================|=========================================
                                              v
                           +-------------------------------------+
                           |            Signal Graph             |
                           |           (NetworkX)                 |
                           +-------------------------------------+
                                              |
     +----------------------------------------+----------------------------------------+
     |                                        |                                        |
     v                                        v                                        v
+-----------------------+          +-----------------------+          +-----------------------+
|  Trend Engine         |          |  Pain Mining Engine   |          |                       |
|  (Velocity & Growth)  |          |  (Demand DNA)         |          |                       |
+-----------------------+          +-----------------------+          +-----------------------+
     |                                        |                                        |
     +----------------------------------------+----------------------------------------+
                                              |
                                              v
                           +-------------------------------------+
                           |   Opportunity Engine + Critic       |
                           +-------------------------------------+
                                              |
     =========================================|=========================================
                                              |
                                              v
     +---------------------------------------------------------------------------------+
     |                   Human Control Plane (HCP) - LangGraph                          |
     |                                                                                 |
     |    +--------------------+    +--------------------+    +--------------------+   |
     |    | Feedback Gate      |    | Interrupt & Review |    | Dynamic Policy     |   |
     |    +--------------------+    +--------------------+    +--------------------+   |
     +---------------------------------------------------------------------------------+
                                         ^         |
                                 Feedback|         |Constraints
                                         |         v
                           +-------------------------------------+
                           |      Builder Memory Engine          |
                           +-------------------------------------+
                                              |
                                              v
                           +-------------------------------------+
                           |  Builder Intelligence Report / CLI  |
                           +-------------------------------------+
```

---

## 3. 技术栈决策

| 层级 | 决策 | 说明 |
|------|------|------|
| 包管理 | **uv** (替换 pip/venv) | 极速包管理 |
| 编排 | **LangGraph** | DAG 编排 + `interrupt` 暂停机制实现 Feedback Gate |
| LLM 抽象 | **现有 OpenAIClient** (不改) | 功能足够覆盖 DeepSeek/OpenAI 兼容 API |
| CLI | **Typer + Rich** (从 Click 迁移) | 类型提示语法更现代 |
| 事务存储 | **SQLite (JSON blob)** | 保留现有 store 模式用于快照和元数据 |
| 分析查询 | **DuckDB + Parquet** | 时间序列聚合、趋势对比 |
| 向量存储 | **ChromaDB (embedded)** | Issue 语义检索 |
| 聚类 | **HDBSCAN** | 无监督文本聚类，替代 LLM 聚类 |
| 图数据结构 | **NetworkX** (内存图) | PageRank、中心度分析、co-occurrence 检测 |
| HTTP | **现有 httpx + tenacity** (保留) | GitHub API 客户端 |
| API | **现有 FastAPI** (保留) | 前端数据服务 |
| 前端 | **现有 Next.js 14** (不改) | React Dashboard |

### 移除的依赖

| 移除 | 原因 |
|------|------|
| Click | → Typer |
| pip/venv | → uv |

---

## 4. 新目录结构

```text
BuilderDNA/
├── cli/                        # Typer CLI (NEW)
│   ├── main.py                 # builderdna radar/opportunities/analyze
│   └── formatters.py           # Rich 渲染
│
├── pipeline/                   # LangGraph 编排 (NEW)
│   ├── graph.py                # DAG 节点编排
│   ├── state.py                # AgentState
│   └── gates.py                # Feedback Gate (interrupt)
│
├── collector/                  # 数据采集 (REORGANIZED)
│   ├── github/
│   │   ├── client.py           # 现有异步客户端 (保留)
│   │   ├── cache.py            # 现有缓存层 (保留)
│   │   ├── repo.py             # 新增：Repo & Release 采集
│   │   ├── issue.py            # 新增：Issue & Discussion 采集
│   │   └── star_history.py     # 新增：Star 时序数据采集
│   └── normalizer.py           # 原始数据 → Signal 统一模型
│
├── signal/                     # Signal Lake + Graph (NEW)
│   ├── models.py               # Signal, TopicTrend, RepoTrend, VendorProfile 统一模型
│   ├── store.py                # SQLite (事务) + DuckDB (分析)
│   └── graph.py                # NetworkX Signal Graph
│
├── intelligence/               # 分析引擎 (REORGANIZED)
│   ├── trend/
│   │   ├── detector.py         # 合并 radar.py + discovery.py + vendor.py
│   │   └── velocity.py         # 二阶导数计算逻辑
│   ├── pain/
│   │   ├── models.py           # PainIssue, PainCluster, PainSnapshot
│   │   ├── issue_miner.py      # Issue 嵌入抽取 (迁移 pain.py 采集逻辑)
│   │   ├── cluster.py          # HDBSCAN 聚类
│   │   └── severity.py         # 痛苦指数公式
│   └── opportunity/
│       ├── models.py           # OpportunityCard + CriticReview + ValidationResult
│       ├── generator.py        # LLM 推理 (合并两套 opportunity)
│       ├── critic.py           # 风险反思 Agent (NEW)
│       └── scorer.py           # 三维评分 + validation (合并 evaluator.py)
│
├── control_plane/              # HCP & Builder Memory (NEW)
│   ├── hcp.py                  # Control Plane 主逻辑
│   ├── policy.py               # Trigger Score 评估
│   └── memory.py               # Builder Memory 存储 + 检索 + 注入
│
├── llm/                        # LLM (KEPT + EXTENDED)
│   ├── client.py               # 现有 OpenAIClient (不改)
│   └── prompts/                # 结构化 Prompt 模板目录 (NEW)
│
├── report/                     # 报告生成 (MIGRATED from output/)
│   └── builder_report.py
│
├── backend/                    # FastAPI (KEPT, simplified)
│   ├── main.py
│   ├── dependencies.py
│   └── router/radar.py         # 精简为前端 API，核心逻辑在 intelligence/
│
├── frontend/                   # Next.js (UNCHANGED)
├── snapshots/                  # DuckDB + SQLite + Parquet
├── tests/
├── config.yaml
└── pyproject.toml
```

---

## 5. 模块详细设计

### 5.1 Collector & Signal Lake

**职责：** 从 GitHub REST API 获取多维事件，转换为统一的 `Signal` 数据模型。

```python
class Signal(BaseModel):
    """统一的不可变事件抽象。所有上游数据归一化到此模型。"""
    id: str                                    # uuid
    source: Literal["github"]
    type: Literal[
        "repo_created",     # 新仓库
        "star_growth",      # star 增长事件
        "issue_opened",     # issue 创建(含 body 文本)
        "issue_commented",  # issue 讨论活跃度
        "release",          # 版本发布
        "fork",             # fork 事件
        "discussion",       # discussion 创建
    ]
    actor: str                                 # 发起者 (developer/org login)
    target_repo: str                           # 目标仓库 full_name
    timestamp: datetime
    velocity: float = 0.0                      # 瞬时增速
    impact: float = 0.0                        # 影响权重 (0-1)
    payload: dict[str, Any]                    # 原始数据快照
```

**normalizer.py 职责：** 替代 `collect/github/mapper.py`，将 GitHub API raw dict 统一转为 Signal。

**存储策略：**
- SQLite：快照元数据 + 用户反馈 + 运行日志（保留现有 pattern）
- DuckDB：时间序列聚合（"最近 30 天 velocity Top N"、topic 月度趋势）
- Parquet：归档旧 snapshot

**数据流：**
```
GitHub API → client.py (复用) → repo/issue/star_history → normalizer → Signal list
                                                                          │
                                                          ┌──────────────┴──────────────┐
                                                          │ Signal Store                 │
                                                          │  ├─ SQLite: 快照 + 元数据     │
                                                          │  └─ DuckDB: 时序分析查询     │
                                                          └─────────────────────────────┘
```

### 5.2 Signal Graph

**职责：** 用 NetworkX MultiDiGraph 对 Developer-Repo-Issue-Topic-Opportunity 关系建模。

**图模型：**
```
Developer ──[CREATES]──→ Repo
Developer ──[STARS]────→ Repo
Developer ──[COMMENTS_ON]──→ Issue
Repo ──────[HAS]───────→ Issue
Issue ────[CLUSTERS_IN]──→ PainPoint
Repo ──────[BELONGS_TO]───→ Topic
Topic ────[ACCELERATES]───→ Trend
PainPoint ──[REQUIRES]──→ Opportunity
Trend ────[ENABLES]───→ Opportunity
```

**核心接口：**
```python
class SignalGraph:
    def build_from_signals(self, signals: list[Signal]) -> None
    def get_developer_influence(self, login: str) -> float        # PageRank
    def find_bridging_repos(self, topic_a: str, topic_b: str) -> list[str]
    def get_co_occurring_topics(self, min_edge_weight: int) -> list[tuple[str, str]]
    def export_for_engine(self, engine: str) -> dict
```

**设计决策：**
- 内存图，按需从 DuckDB 构建——不持久化图，Signal Lake 是 source of truth
- 边带权重和 last_seen 时间戳
- 按引擎导出子图，避免整张图丢给 LLM

### 5.3 Trend Engine

**职责：** 合并现有 3 个引擎（radar.py + discovery.py + vendor.py + follow/）为一个统一的趋势检测引擎。

**核心升级：**
1. 从固定 topic 列表 → 双向发现（配置 topics + Signal Graph co-occurrence）
2. 默认启用二阶加速度计算（需要 star_history 时序数据）
3. 厂商追踪作为趋势分析的一个维度（"哪些厂商在该方向上活跃"）

**核心接口：**
```python
class TrendEngine:
    def compute_acceleration(self, repo_signals: list[Signal], window_days: int = 30) -> float
    def detect_emerging(self, graph: SignalGraph, threshold: float) -> list[TopicTrend]
    def detect_vendor_activity(self, graph: SignalGraph, vendors: VendorConfig) -> list[VendorProfile]
```

**迁移关系：**

| 现有文件 | 去向 |
|---------|------|
| `backend/engine/radar.py` | `intelligence/trend/detector.py` (核心公式保留) |
| `backend/engine/discovery.py` | 合并到 detector.py (broad search → co-occurrence) |
| `backend/engine/vendor.py` | 合并到 detector.py |
| `follow/scorer.py` | 废弃 (star/follower 打分被图算法替代) |
| `backend/models/trend.py` | 迁移到 `signal/models.py` (作为 Signal 聚合视图) |

### 5.4 Pain Mining Engine

**职责：** Issue 语义聚类 + 痛苦指数评分。核心变化：用 embedding + HDBSCAN 替代 LLM 聚类。

**工作流：**
```
Issues (GitHub API) → 文本提取 → embedding (LLM API embedding endpoint) → ChromaDB
                                                                              │
                                                                       HDBSCAN 聚类
                                                                              │
                                                                    severity.py 评分
                                                                   (comments × participants × sentiment)
                                                                              │
                                                                       LLM 命名 + root cause
                                                                              │
                                                                       PainCluster[]
```

**核心接口：**
```python
class IssueMiner:
    async def fetch_and_embed(self, repos: list[str], client, embedding_client) -> list[IssueEmbedding]

class PainClusterer:
    def __init__(self, min_cluster_size: int = 5, min_samples: int = 2, metric: str = "cosine")
    def fit(self, embeddings: list[IssueEmbedding]) -> list[IssueCluster]

def compute_severity(issue: Signal, sentiment_score: float) -> float:
    """pain_score × log(comments+1) × log(participants+1) × sentiment_multiplier"""
```

**关键设计决策：**
- 用 LLM API 的 embedding 端点（OpenAI 兼容），不引入 sentence-transformers
- HDBSCAN 替代 LLM 聚类：一次 fit vs 每个 issue 过 LLM，且结果确定可复现
- 情绪词密度：规则匹配（"broken/crash/frustrating/cannot/blocked"），不调 LLM
- LLM 只负责：cluster 命名 + root cause 描述

**迁移关系：**

| 现有文件 | 去向 |
|---------|------|
| `backend/engine/pain.py` | 拆分为 `issue_miner.py` (采集) + `cluster.py` (聚类) + `severity.py` (评分) |
| `backend/models/pain.py` | 迁移到 `intelligence/pain/models.py` |
| `insight/aggregator.py` | 废弃 (union-find 被 Signal Graph 替代) |
| `insight/classifier.py` | 废弃 (LLM 聚类被 HDBSCAN 替代) |
| `models/insight.py` | 废弃 (被 PainCluster + TopicTrend 替代) |

### 5.5 Opportunity Engine

**职责：** 联合 Trend + Pain + Signal Graph，用 LLM CoT 生成机会，新增 Critic Agent 独立审阅。

**工作流：**
```
TrendEngine Output          PainMining Output          Signal Graph
(TopicTrend[])              (PainCluster[])            (bridging repos, 竞争格局)
      │                           │                         │
      └───────────────────────────┼─────────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │    generator.py          │
                    │    LLM CoT 推理          │
                    │    → OpportunityCard[]   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │    critic.py             │  ← NEW
                    │    独立 LLM call         │
                    │    挑战每个机会的假设     │
                    │    评分: 可行性/市场/时机 │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │    scorer.py             │
                    │    critic × trend × pain │
                    │    × validation signals  │
                    │    → 最终排名             │
                    └─────────────────────────┘
```

**Critic Agent 设计：**
```python
class CriticReview(BaseModel):
    feasibility: int = 0      # 技术可行性 1-10
    market_size: int = 0      # 市场规模 1-10
    timing: int = 0           # 时机合适度 1-10
    blind_spots: list[str]    # Generator 忽略的风险
    counter_view: str         # 反向观点 (一句话)
```

Critic 使用不同于 Generator 的系统 prompt，刻意持怀疑立场。

**迁移关系：**

| 现有文件 | 去向 |
|---------|------|
| `backend/engine/opportunity.py` | `intelligence/opportunity/generator.py` |
| `opportunity/detector.py` | 合并到 generator.py |
| `opportunity/evaluator.py` | `intelligence/opportunity/scorer.py` |
| `backend/engine/validation.py` | 合并到 scorer.py |
| `backend/models/opportunity.py` | `intelligence/opportunity/models.py` |
| `backend/models/validation.py` | 合并到 opportunity/models.py |

### 5.6 Human Control Plane & Builder Memory

**职责：** 在关键决策点插入人类审批，存储人类反馈并反哺后续决策。

**Trigger Score：**
```
TriggerScore = (1 - Confidence) × Impact × (1 - Familiarity)

Confidence:  模型对自己输出的把握 (0-1)
Impact:      决策影响力 (0-1)，从 opportunity.score 映射
Familiarity: 是否见过类似场景 (0-1)，从 Builder Memory 检索
```

**三种运行模式：**
```python
class RunMode(Enum):
    FULL_AUTO = 0     # 不中断，事后出报告
    SUPERVISED = 1    # TriggerScore > 阈值时中断
    EXPERT = 2        # 每个关键节点中断
```

**核心接口：**
```python
class HumanControlPlane:
    def __init__(self, mode: RunMode, threshold: float = 0.5)
    async def evaluate(self, confidence: float, impact: float, opportunity_desc: str, memory: BuilderMemory) -> GateDecision

class BuilderMemory:
    def record(self, decision: HumanDecision) -> None              # 存储反馈 (SQLite + ChromaDB)
    async def search(self, query: str, top_k: int = 5) -> list[MemoryRule]  # 语义检索
    def inject_constraints(self, opportunity_desc: str, prompt: str) -> str   # Prompt 注入
```

**LangGraph 集成：**
```python
workflow = StateGraph(AgentState)
workflow.add_node("collect", collect_signals)
workflow.add_node("trend", detect_trends)
workflow.add_node("pain", mine_pain)
workflow.add_node("opportunity", generate_opportunities)
workflow.add_node("critic", review_opportunities)
workflow.add_node("report", generate_report)

graph = workflow.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["opportunity"],  # HCP Gate
)
```

---

## 6. 代码迁移映射总表

### 迁移清单

| 现有路径 | 去向 | 说明 |
|---------|------|------|
| `config.py` | 保留 | 不变 |
| `config.yaml` | 保留 | 不变 |
| `pipeline.py` | `pipeline/graph.py` | LangGraph 重写 |
| `cli.py` | `cli/main.py` + `cli/formatters.py` | Click → Typer |
| `collect/github/client.py` | `collector/github/client.py` | 复制保留 |
| `collect/github/cache.py` | `collector/github/cache.py` | 复制保留 |
| `collect/github/mapper.py` | `collector/normalizer.py` | 合并重写 |
| `collect/store.py` | `signal/store.py` | 扩展 +DuckDB |
| `models/signal.py` | `signal/models.py` | 升级为统一 Signal |
| `output/*` | `report/` | 迁移 |
| `llm/client.py` | `llm/client.py` | 保留 |
| `backend/main.py` | 保留 | API 入口 |
| `backend/dependencies.py` | 保留 | DI |
| `backend/router/radar.py` | 保留 (精简) | API 路由 |
| `backend/engine/radar.py` | `intelligence/trend/detector.py` | 合并 |
| `backend/engine/pain.py` | `intelligence/pain/` | 拆分 |
| `backend/engine/opportunity.py` | `intelligence/opportunity/generator.py` | 合并 |
| `backend/engine/validation.py` | `intelligence/opportunity/scorer.py` | 合并 |
| `backend/models/trend.py` | `signal/models.py` | 迁移 |
| `backend/models/pain.py` | `intelligence/pain/models.py` | 迁移 |
| `backend/models/opportunity.py` | `intelligence/opportunity/models.py` | 升级 |
| `backend/models/validation.py` | `intelligence/opportunity/models.py` | 合并 |
| `backend/store/*` | `signal/store.py` | SQLite保留+DuckDB |
| `frontend/` | 保留 | 不改 |

### 删除清单

| 删除 | 原因 |
|------|------|
| `models/insight.py` | PainCluster + TopicTrend 替代 |
| `insight/aggregator.py` | Signal Graph 替代 |
| `insight/classifier.py` | HDBSCAN 替代 |
| `insight/` (目录) | 全部废弃 |
| `opportunity/detector.py` | 合并到 intelligence/opportunity |
| `opportunity/evaluator.py` | 合并到 intelligence/opportunity |
| `opportunity/` (目录) | 全部废弃 |
| `follow/` (目录) | 合并到 intelligence/trend |
| `backend/engine/discovery.py` | 合并到 intelligence/trend |
| `backend/engine/vendor.py` | 合并到 intelligence/trend |
| `backend/store/discovery_store.py` | DuckDB 替代 |
| `backend/store/vendor_store.py` | DuckDB 替代 |
| `backend/models/discovery.py` | 合并到 signal/models.py |
| `backend/models/vendor.py` | 合并到 signal/models.py |

---

## 7. 实施路线

### Phase 1：基础层重组（预计 1 周）

**目标：统一数据模型和存储，不碰分析引擎。**

```
任务:
  ├── 安装新依赖 (uv, duckdb, chromadb, hdbscan, networkx, typer, langgraph)
  ├── 创建 signal/models.py (Signal + 聚合视图，迁移 backend/models/trend.py 等)
  ├── 创建 signal/store.py (SQLite 保留 + DuckDB 新增)
  ├── 创建 signal/graph.py (NetworkX)
  ├── 创建 collector/ (迁移 client/cache → 新增 repo/issue/star_history/normalizer)
  ├── 创建 llm/prompts/ (结构化 prompt 模板目录)
  └── 验证：现有测试全过 + 新 Signal/Graph/Store 测试通过
```

**不碰：** `backend/`、`intelligence/`、`pipeline.py`、`cli.py`、`follow/`、`insight/`、`opportunity/`

### Phase 2：引擎层迁移（预计 2 周）

**目标：分析引擎从 backend/engine/* 迁到 intelligence/，删除废弃代码。**

```
任务:
  ├── 创建 intelligence/trend/ (合并 radar + discovery + vendor + follow)
  ├── 创建 intelligence/pain/ (拆分 pain.py，新增 HDBSCAN 聚类)
  ├── 创建 intelligence/opportunity/ (合并两套 opportunity，新增 Critic)
  ├── 删除废弃代码 (insight/, opportunity/, follow/, backend/engine/*, 相关 models/store)
  ├── 验证：所有测试适配新路径 + 与旧 API 输出对照
  └── CLI 部分迁移 (Typer 替换 Click 的 radar/opportunities 命令)
```

### Phase 3：编排层 + HCP（预计 2 周）

**目标：LangGraph 编排 + HCP + Builder Memory 闭环。**

```
任务:
  ├── 创建 pipeline/graph.py + state.py + gates.py (LangGraph DAG)
  ├── 创建 control_plane/hcp.py + policy.py + memory.py
  ├── CLI 完整迁移 (Typer: analyze, radar, opportunities)
  ├── 创建 report/ (迁移 output/)
  ├── 删除 pipeline.py (旧线性 Pipeline)
  └── E2E 测试: builderdna radar agent → builderdna opportunities agent
```

### 每个 Phase 结束的验证标准

| Phase | 验证标准 |
|-------|---------|
| Phase 1 | 现有测试全过 + 新 Signal/Graph/Store 测试通过 |
| Phase 2 | Phase 1 测试 + 新引擎测试 + 与旧 API 路径对照输出 |
| Phase 3 | E2E 命令可用 + HCP 中断可触发 + Memory 可读写 |

**总预计工期：5 周**

---

## 8. 风险与注意事项

- **现有 auto-discovery PR 先合并** — 当前 branch (main) 上的 18 个 commit (Discovery/Vendor/Validation) 应在 Phase 1 开始前整合。Phase 1 的 signal 统一模型会吸收这些模块的代码。
- **现有数据兼容** — Phase 1 的 SQLite 保留确保旧 snapshot 可读。新增 DuckDB 不影响现有数据
- **API 兼容** — 前端不变，backend API 接口不 break（只精简 router 实现）
- **删除时机** — Phase 2 才删除废弃代码，Phase 1 是纯增量。万一 Phase 2 引擎迁移有问题，可以 revert 而不影响 Phase 1
- **LangGraph 学习成本** — Phase 3 放在最后，因为 HCP 是增强而非基础功能
- **HDBSCAN 参数调优** — `min_cluster_size` 和 `min_samples` 需要多次迭代确定最佳值
