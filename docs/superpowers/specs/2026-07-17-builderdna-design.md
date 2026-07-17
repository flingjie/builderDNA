# BuilderDNA — 设计规格

> 架构围绕用户价值组织，而不是技术实现组织。

## 1. 项目概述

BuilderDNA 是一个独立 AI Agent 应用，分析 GitHub 上指定 Builder（开发者）的公开活动，提取其技术栈、兴趣方向、能力画像，最终输出可行动的 **Opportunity（机会洞察）**。

### 1.1 核心生命线

```
Collect ────────► Understand ────────► Recommend
(Signal)          (Insight)            (Opportunity)
```

| 阶段 | 做什么 | LLM 角色 |
|------|--------|----------|
| **Collect** | 从 GitHub API 拉取原始数据，归一化为 Signal | 不参与 |
| **Understand** | L1 规则聚合 → 量化信号簇，L2 LLM → 语义 Insight | L2 语义理解 |
| **Recommend** | 从 Insight 推理 Opportunity，评估 Gap | 推理 + 打分 |

### 1.2 关键约束

- **LLM 是 Utility，不是层**。业务逻辑不依赖特定模型。
- **Signal 是统一输入模型**。GitHub、未来 Twitter/HN/ArXiv 都归一化为 Signal。
- **Opportunity 是 SSOT**。CLI、Markdown、未来 dashboard 都只是它的 View。
- **增量对比**：每次运行存快照（SQLite），下次运行只拉取增量数据，对比趋势变化。

---

## 2. 领域模型

### 2.1 Signal — 统一信号

```python
class Signal(BaseModel):
    id: str                  # 唯一标识 "gh_star_<repo_id>_<actor>"
    source: str              # "github"
    type: str                # "star" | "repo" | "commit" | "issue" | "pr"
    timestamp: datetime
    weight: float            # 预设权重，由 config.yaml 覆盖
    actor: str               # Builder 账号
    target: str              # 实体标识（repo full_name 等）
    meta: dict               # 结构化摘要 {language, topics, description, ...}
    raw: dict                # 完整原始 API 响应，不丢信息
```

**信号类型与默认权重：**

| type | weight | 含义 |
|------|--------|------|
| `repo` | 5.0 | 创建/拥有一个仓库（最高信号：他在 build） |
| `commit` | 3.0 | 代码贡献（他在写代码） |
| `pr` | 2.5 | 提交 Pull Request（协作能力） |
| `issue` | 1.5 | 提 Issue（发现问题/需求） |
| `star` | 1.0 | Star 仓库（兴趣关注） |

### 2.2 Insight — 语义洞察

```python
class Insight(BaseModel):
    id: str
    tags: list[str]          # ["MCP", "Agent", "Tool-Use"]
    summary: str             # LLM 生成的描述
    strength: float          # 基于 Signals 加权和
    trend: str               # "rising" | "stable" | "fading"
    signal_count: int        # 支撑信号数量
    evidence: list[str]      # 关键证据（repo 名、commit message 摘要）
    created_at: datetime
```

**Insight 生产流程：**

1. **L1（规则层）**：时间窗口聚合 + topic 共现 + 频率统计 → 量化信号簇（`SignalCluster`）
2. **L2（LLM 层）**：将量化簇喂给 GPT → 产出 `Insight`（summary + trend 判断 + tags）

`SignalCluster` 是内部中间结构，不对外暴露：

```python
class SignalCluster(BaseModel):
    """L1 产物：一组相关 Signal 的量化聚合"""
    signals: list[str]        # 参与的 signal id 列表
    topics: list[str]         # 共现的 topic
    languages: list[str]      # 涉及的语言
    total_weight: float       # 权重和
    time_span_days: int       # 时间跨度
    growth_rate: float        # 增速（近期权重 / 总权重）
```

### 2.3 Opportunity — 机会洞察

```python
class Opportunity(BaseModel):
    id: str
    title: str               # "Agent Replay Visualizer"
    pain_point: str          # 核心痛点
    demand_score: float      # 需求热度 1-5
    competition_score: float # 竞争烈度 1-5（越低越好）
    gap_score: float         # demand / competition，越高越值得做
    recommended_action: str  # 建议行动
    source_insights: list[str]  # 回溯到 Insight ID
    created_at: datetime
```

---

## 3. 架构

### 3.1 分层结构

```
┌─────────────────────────────────────────────┐
│              CLI (click)                     │
│  bldr-dna run                   全量分析      │
│  bldr-dna run --compare         增量对比      │
│  bldr-dna show <account>        查看快照      │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│           pipeline.py (编排层)               │
│  1. 读 config.yaml                          │
│  2. Collect → Signals                       │
│  3. Understand (L1→L2) → Insights           │
│  4. Recommend → Opportunities               │
│  5. Snapshot → SQLite                       │
│  6. Render → CLI + Markdown + JSON           │
└──┬──────────┬───────────┬───────────────────┘
   │          │           │
┌──▼───┐ ┌───▼────┐ ┌───▼──────────┐
│collect│ │insight │ │opportunity   │
│github │ │L1:规则 │ │detector      │
│store  │ │L2:LLM  │ │evaluator     │
└──┬───┘ └───┬────┘ └───┬──────────┘
   │         │           │
   │    ┌────▼────┐      │
   │    │  LLM    │      │
   │    │ (Utility)│──────┘
   │    └─────────┘
   │
┌──▼──────────────────────────────────────────┐
│           SQLite (snapshots/)                │
│  signals | signal_clusters | insights        │
│  | opportunities | snapshots                 │
└──────────────────────────────────────────────┘
```

### 3.2 模块职责

| 模块 | 输入 | 输出 | 依赖 |
|------|------|------|------|
| `collect/github/client.py` | GitHub Token | 原始 API 数据 | `httpx` |
| `collect/github/mapper.py` | 原始数据 | `Signal[]` | `models/signal.py` |
| `collect/store.py` | `Signal[]` | SQLite 写入 | `sqlite3` |
| `insight/aggregator.py` | `Signal[]` | `SignalCluster[]` | 无 |
| `insight/classifier.py` | `SignalCluster[]` + LLM | `Insight[]` | LLM client |
| `opportunity/detector.py` | `Insight[]` + LLM | `Opportunity[]` | LLM client |
| `opportunity/evaluator.py` | `Opportunity[]` | 打分后的 `Opportunity[]` | 无 |
| `pipeline.py` | `Config` | `Snapshot` | 以上全部 |
| `output/cli.py` | `Snapshot` | 终端输出 | `rich` |
| `output/markdown.py` | `Snapshot` | `.md` 文件 | 无 |
| `output/json_out.py` | `Snapshot` | `.json` 文件 | 无 |
| `config.py` | `config.yaml` | `Config` | `pydantic` |

### 3.3 LLM 作为 Utility

LLM 不占有架构中的一层。它像一个"智能函数"，在各模块中被按需调用：

```python
# insight/classifier.py
def classify(clusters: list[SignalCluster], llm: LLMClient) -> list[Insight]:
    """将量化簇转化为语义洞察。LLM 只做它擅长的事：理解和总结。"""
    prompt = build_classification_prompt(clusters)  # 纯数据→文本
    response = llm.complete(prompt, response_format=InsightList)
    return parse_insights(response)

# opportunity/detector.py
def detect(insights: list[Insight], llm: LLMClient) -> list[Opportunity]:
    """从洞察中推理机会。LLM 做推理和评估。"""
    prompt = build_detection_prompt(insights)
    response = llm.complete(prompt, response_format=OpportunityList)
    return parse_opportunities(response)
```

LLM Client 接口：

```python
class LLMClient(Protocol):
    def complete(self, prompt: str, response_format: type) -> Any:
        """调用 LLM 并解析为指定类型"""
        ...
```

`OpenAIClient` 作为默认实现，后续可换模型或加 fallback。

---

## 4. 数据流

### 4.1 全量分析流程

```
config.yaml ─► pipeline.run()
                  │
                  ├─► collect.github.client fetches repos, stars, commits
                  │       │
                  │       ▼
                  ├─► collect.github.mapper maps to Signal[]
                  │       │
                  │       ▼
                  ├─► collect.store saves signals to SQLite
                  │       │
                  │       ├─► insight.aggregator: L1 rules → SignalCluster[]
                  │       │       │
                  │       │       ▼
                  │       ├─► insight.classifier: L2 LLM → Insight[]
                  │       │       │
                  │       │       ▼
                  │       ├─► opportunity.detector: LLM → Opportunity[]
                  │       │       │
                  │       │       ▼
                  │       ├─► opportunity.evaluator: score → Opportunity[]
                  │       │
                  │       ▼
                  ├─► snapshot stored (signals + insights + opportunities)
                  │
                  ▼
               output/ → cli.py + markdown.py + json_out.py
```

### 4.2 增量分析流程

```
config.yaml ─► pipeline.run(compare=True)
                  │
                  ├─► load last snapshot from SQLite
                  ├─► collect only signals since last snapshot time
                  │       (GitHub API: since=<last_run>)
                  ├─► diff: new_signals vs historical
                  │       │
                  │       ├─► Signal-level diff (确定性):
                  │       │     - new signal count by type
                  │       │     - weight change by topic
                  │       │     - new repos/languages
                  │       │
                  │       ├─► Re-run L1 + L2 on ALL signals (old + new):
                  │       │     - L1 re-aggregates full dataset
                  │       │     - L2 compares new clusters vs old → trend: rising/stable/fading
                  │       │
                  │       ▼
                  ├─► opportunity.detector on updated insights
                  │       │
                  │       ▼
                  ├─► new snapshot stored
                  ▼
               output/ highlights "what changed since last run"
```

### 4.3 SQLite Schema

```sql
-- 每次运行的快照元数据
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    accounts TEXT,           -- JSON array of analyzed accounts
    signal_count INTEGER,
    insight_count INTEGER,
    opportunity_count INTEGER
);

-- 信号存储（追加，不覆盖）
CREATE TABLE signals (
    id TEXT PRIMARY KEY,
    source TEXT,
    type TEXT,
    timestamp TIMESTAMP,
    weight REAL,
    actor TEXT,
    target TEXT,
    meta JSON,
    raw JSON,
    snapshot_id TEXT REFERENCES snapshots(id)
);

-- 信号簇（每次运行重新生成）
CREATE TABLE signal_clusters (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    topics JSON,
    languages JSON,
    total_weight REAL,
    time_span_days INTEGER,
    growth_rate REAL
);

-- 洞察（每次运行重新生成）
CREATE TABLE insights (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    tags JSON,
    summary TEXT,
    strength REAL,
    trend TEXT,
    signal_count INTEGER,
    evidence JSON
);

-- 机会（每次运行重新生成）
CREATE TABLE opportunities (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    title TEXT,
    pain_point TEXT,
    demand_score REAL,
    competition_score REAL,
    gap_score REAL,
    recommended_action TEXT,
    source_insights JSON
);
```

---

## 5. 配置文件

### 5.1 config.yaml

```yaml
# BuilderDNA 配置文件

# 分析目标账号
accounts:
  - github_username_1
  - github_username_2

# GitHub API
github:
  token: ${GITHUB_TOKEN}     # 支持环境变量

# LLM 配置
llm:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}

# 信号权重
weights:
  repo: 5.0
  commit: 3.0
  pr: 2.5
  issue: 1.5
  star: 1.0

# 输出
output:
  dir: ./output
  formats:
    - markdown
    - json

# 增量对比
compare:
  enabled: true
```

### 5.2 Config 模型

```python
class Config(BaseModel):
    accounts: list[str]
    github: GitHubConfig
    llm: LLMConfig
    weights: WeightConfig
    output: OutputConfig
    compare: CompareConfig
```

---

## 6. 错误处理

### 6.1 分层策略

| 层 | 错误 | 处理 |
|----|------|------|
| GitHub API | Rate limit (403) | 等待 retry-after 秒，指数退避，最多 3 次 |
| GitHub API | Token 无效 (401) | 立即终止，提示检查 token |
| GitHub API | 用户不存在 (404) | 跳过该账号，继续处理其他 |
| GitHub API | 网络超时 | 指数退避重试，3 次后跳过该请求 |
| LLM | API 错误/超时 | 重试 2 次，失败则降级：L2 失败用规则生成基础 Insight |
| LLM | 响应解析失败 | 重试 1 次（加 strict prompt），仍失败则记录原始响应并跳过 |
| SQLite | 写入失败 | 立即终止，报告路径和权限问题 |

### 6.2 降级策略

当 LLM 不可用时：
- **Insight L2** → 退化为规则生成的简单摘要（`{actor} focuses on {topics}`）
- **Opportunity** → 跳过，报告中标注"LLM 不可用，机会洞察未生成"
- 不影响 Collect 和 Insight L1 的执行

---

## 7. 测试策略

| 层级 | 测试内容 | 工具 |
|------|----------|------|
| 单元测试 | 模型序列化/反序列化、mapper 映射逻辑、aggregator 聚合算法、evaluator 打分逻辑 | pytest |
| 集成测试 | GitHub client（用 mock server）、LLM client（用 mock response）、SQLite store 读写 | pytest + httpx mock |
| 端到端 | pipeline 完整流程（用 mock 数据和 mock LLM）、CLI 命令输出 | pytest |
| 契约测试 | LLM 响应 schema 验证 | pydantic |

---

## 8. 目录结构

```text
BuilderDNA/
├── models/
│   ├── __init__.py
│   ├── signal.py
│   ├── insight.py
│   └── opportunity.py
├── collect/
│   ├── __init__.py
│   ├── github/
│   │   ├── __init__.py
│   │   ├── client.py        # GitHub API 调用
│   │   └── mapper.py        # 原始数据 → Signal
│   └── store.py             # Signal → SQLite
├── insight/
│   ├── __init__.py
│   ├── aggregator.py        # L1 规则聚合
│   └── classifier.py        # L2 LLM 语义分类
├── opportunity/
│   ├── __init__.py
│   ├── detector.py          # 机会发现
│   └── evaluator.py         # 机会评估打分
├── output/
│   ├── __init__.py
│   ├── cli.py               # 终端输出 (rich)
│   ├── markdown.py          # Markdown 报告
│   └── json_out.py          # JSON 输出
├── llm/
│   ├── __init__.py
│   └── client.py            # LLMClient 抽象 + OpenAI 实现
├── pipeline.py              # 编排层
├── config.py                # 配置加载
├── config.yaml              # 配置文件模板
├── pyproject.toml
├── requirements.txt
├── snapshots/               # SQLite 数据库
├── output/                  # 生成的报告
└── tests/
    ├── test_models/
    ├── test_collect/
    ├── test_insight/
    ├── test_opportunity/
    ├── test_llm/
    └── test_pipeline/
```

---

## 9. CLI 接口

```bash
# 全量分析（首次运行）
bldr-dna run

# 增量对比分析
bldr-dna run --compare

# 查看某个账号最新快照
bldr-dna show <account>

# 列出所有快照
bldr-dna snapshots

# 比较两次快照
bldr-dna diff <snapshot_id_1> <snapshot_id_2>
```

---

## 10. Scope 边界（v1）

### ✅ 在 v1 范围内

- GitHub 作为唯一数据源
- collect: repos（owner + starred）+ commits（activity）
- Signal 类型: `repo`, `star`, `commit`
- YAML 配置驱动、多账号
- SQLite 快照、增量拉取
- L1 规则聚合 + L2 LLM Insight
- Opportunity 发现 + Gap 评分
- CLI 输出 + Markdown + JSON 报告
- Token 认证

### ❌ 不在 v1 范围内

- Twitter, Hacker News, ArXiv 等额外数据源
- `issue`, `pr` Signal 类型（数据量大，先聚焦核心信号）
- Web Dashboard
- 实时监控/定时任务
- 多 LLM provider 切换（先只做 OpenAI）
- 组织/团队级别的横向对比
