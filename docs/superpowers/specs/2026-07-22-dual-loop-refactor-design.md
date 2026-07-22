# BuilderDNA 双环架构重构 Spec

**日期**: 2026-07-22
**方案**: C — Claude 替换编排层，最简落地
**状态**: 已确认，待实现

---

## 1. 设计原则

- **Claude Code 是大脑**：决策、解读、迭代由 Claude 完成
- **BuilderDNA 是工具箱**：每个命令是独立沙盒，结构化输出，用完即弃
- **人类反馈是引力场**：异步、软约束，不是硬性 gate
- **确定性计算留在 Python**：聚类、速度计算、评分用数学公式，不依赖 LLM

---

## 2. 架构拓扑

```
                        ┌──────────────────────┐
                        │  Human Feedback       │
                        │  (对话中的偏好/权重)    │
                        └──────────┬───────────┘
                                   │ 软约束
                                   ▼
┌──────────────────────────────────────────────────┐
│  Outer Loop: Claude Code (Skill)                  │
│                                                   │
│  hypotheses.json  ←── 假说树维护                  │
│  user_weights.json ←── 偏好权重                   │
│                                                   │
│  派生 Sandbox Task ──→ 等待结果 ──→ 更新假说树     │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
┌──────────┐  ┌──────────┐  ┌──────────────┐
│ collect  │  │  trend   │  │    pain      │
│ 沙盒 #1  │  │ 沙盒 #2  │  │   沙盒 #3    │
└────┬─────┘  └────┬─────┘  └──────┬───────┘
     │             │               │
     └─────────────┼───────────────┘
                   │ 结构化 JSON Payload
                   ▼
┌──────────────────────────────────────────────────┐
│  Global Memory                                    │
│  signals/store.py → DuckDB                        │
│  output/*.json    → 历史 payload                  │
│  claude-mem       → 跨会话记忆                    │
└──────────────────────────────────────────────────┘
```

---

## 3. 文件变更清单

### 3.1 删除

| 路径 | 原因 |
|------|------|
| `pipeline/` | LangGraph DAG，Claude 替代编排 |
| `pipeline.py` | v1 编排器 |
| `control_plane/` | HCP gate，对话即反馈 |
| `backend/` | FastAPI，不需要 web |
| `llm/` | OpenAI client，Claude 替代 LLM |
| `cli.py` | v1 Click CLI 入口 |
| `cli/main.py` | v2 Typer 入口，重写为 commands/ |
| `cli/formatters.py` | 终端渲染，不再需要 |
| `output/cli.py` | Rich 渲染，不再需要 |

### 3.2 保留并调整

| 路径 | 调整 |
|------|------|
| `collector/` | 保留核心逻辑，去掉 LangGraph 引用 |
| `signals/` | 保留 store + graph，精简 |
| `models/` | 精简为 payload schema |
| `report/` | 降级为纯格式化函数 |
| `config.py` | 简化，去 backend 引用 |
| `config.yaml` | 保留，去无用字段 |
| `.env` | 精简（只保留 GITHUB_TOKEN + EMBEDDING_BASE_URL） |

### 3.3 新增

| 路径 | 用途 |
|------|------|
| `cli/commands/` | 5 个独立沙盒命令 |
| `state/hypotheses.json` | 假说树（初始模板） |
| `state/user_weights.json` | 用户偏好权重（初始模板） |
| `models/payload.py` | 沙盒输出的强类型 Schema |
| `schema.md` | Claude 可读的 Schema 文档 |

---

## 4. 沙盒命令设计

### 4.1 collect — 数据采集

```
用法:   builderdna collect <domain> [--window N] [--output FILE]
输入:   config.yaml (domains, accounts, vendors)
输出:   signals.json
        { signals: Signal[], stats: { total, by_type, by_source } }
依赖:   collector/, config.py, .env (GITHUB_TOKEN)
```

采集流程：
1. 读 config.yaml → domain topics + vendor accounts
2. GitHub Search API → 每个 topic 拉 top repos (按 stars 排序)
3. GitHub Issues API → top repos 的 demand issues (按 reactions/comments 过滤)
4. GitHub Repos API → vendor accounts 的 repo 列表
5. normalize_all → 统一 Signal 格式
6. 写入 DuckDB + 输出 signals.json

### 4.2 trend — 趋势检测

```
用法:   builderdna trend <domain> [--data FILE] [--window N] [--output FILE]
输入:   signals.json (或从 DuckDB 读)
输出:   trends.json
        { trends: TopicTrend[], domain, window_days, computed_at }
依赖:   signals/store.py, signals/graph.py, intelligence/trend/
```

计算逻辑：
```
velocity = stars / days_since_creation
trend_score = velocity × log₁₀(forks + 1) × log₁₀(contributors + 1)
stage:
  trend_score >= 80  → accelerating
  trend_score >= 50  → emerging
  trend_score >= 20  → mainstream
  trend_score <  20  → declining
```

输出每个 topic：topic, stage, confidence, growth_velocity, acceleration, evidence_count, top_repos (含 stars, forks, velocity)

### 4.3 pain — 痛点挖掘

```
用法:   builderdna pain <domain> [--data FILE] [--output FILE]
输入:   signals.json (issue 类型)
输出:   pain_clusters.json
        { clusters: PainCluster[], issue_count, repos_analyzed }
依赖:   intelligence/pain/, signals/store.py, .env (EMBEDDING)
```

计算流程：
1. 从 signals 筛选 type=issue_opened
2. 调 embedding API 获取文本向量
3. HDBSCAN 聚类
4. 计算 severity = log(comments+1) × log(participants+1) × log(reactions/2+1)
5. 输出聚类（id, title, severity, frequency, top_issues, affected_repos）

### 4.4 opportunity — 机会生成（纯规则引擎）

```
用法:   builderdna opportunity --trends FILE --pains FILE [--output FILE]
输入:   trends.json + pain_clusters.json
输出:   opportunities.json
        { opportunities: OpportunityCard[] }
依赖:   models/payload.py（纯 Python，不调 LLM）
```

评分逻辑（规则引擎，确定性）：
```
demand_score = f(
  trends.growth_velocity,           # 趋势增速
  pain_clusters.severity,           # 痛点强度
  pain_clusters.frequency           # 痛点频率
)  # 归一化到 1-10

competition_score = f(
  trends.evidence_count,            # 已有方案数量
  avg_repo_maturity                 # 平均成熟度
)  # 归一化到 1-10（越低越好=越少竞争）

gap_score = demand / competition    # >2.0 强烈机会
```

输出每张机会卡：title, demand_score, competition_score, gap_score, signals (支撑证据), recommended_action

### 4.5 report — 报告渲染

```
用法:   builderdna report --data FILE --format md|json [--output DIR]
输入:   opportunities.json（或任意结构化 result）
输出:   report.md 或 report.json
依赖:   report/（纯文本格式化，无 AI）
```

---

## 5. 数据模型

### 5.1 沙盒输出 Schema (models/payload.py)

```python
class SandboxResult(BaseModel):
    """所有沙盒命令的统一输出包装。"""
    command: str           # "collect" | "trend" | "pain" | "opportunity"
    domain: str
    computed_at: datetime
    payload: dict          # 具体数据
    stats: dict            # { total, filtered, duration_ms }

class SignalEntry(BaseModel):
    """collect 输出的单条信号。"""
    id: str
    source: str            # github
    type: str              # repo_created | issue_opened | ...
    actor: str
    target_repo: str
    stars: int = 0
    forks: int = 0
    contributors: int = 0
    velocity: float = 0.0
    topics: list[str]
    description: str = ""

class TopicTrend(BaseModel):
    """trend 输出的单条趋势。"""
    topic: str
    stage: Literal["accelerating", "emerging", "mainstream", "declining"]
    confidence: float
    growth_velocity: float
    acceleration: float
    evidence_count: int
    top_repos: list[RepoSummary]

class RepoSummary(BaseModel):
    full_name: str
    stars: int
    stars_delta: int
    forks: int
    contributors: int
    velocity: float
    description: str

class PainCluster(BaseModel):
    cluster_id: int
    title: str
    severity: float
    frequency: int
    affected_repos: list[str]
    top_issues: list[IssueSummary]

class OpportunityCard(BaseModel):
    title: str
    demand_score: float
    competition_score: float
    gap_score: float
    signals: list[str]       # 支撑证据
    recommended_action: str
```

### 5.2 假说树 (state/hypotheses.json)

```json
{
  "version": 1,
  "nodes": []
}
```

每个节点的结构（Claude 通过 Skill 读写）：
```json
{
  "id": "hyp_<timestamp>_<seq>",
  "parent_id": null,
  "statement": "假说陈述",
  "domain": "agent",
  "confidence": 0.0,
  "human_weight": 1.0,
  "status": "exploring",
  "evidence_refs": [],
  "created_at": "",
  "updated_at": ""
}
```

status 流转：`exploring → validated → pruned`

### 5.3 用户权重 (state/user_weights.json)

```json
{
  "preferred_domains": [],
  "avoid_tags": [],
  "scoring_bias": {},
  "feedback_log": []
}
```

---

## 6. 配置简化

### config.yaml 精简为：

```yaml
accounts:
  - hwchase17

github:
  token: ${GITHUB_TOKEN}
  cache_dir: snapshots/cache
  max_concurrent: 5

# Embedding 配置（仅 pain 命令使用）
embedding:
  model: bge-m3:latest
  base_url: ${EMBEDDING_BASE_URL:-http://localhost:11434/v1}

domains:
  agent:
    topics:
      - mcp
      - langchain
      - agent-framework
      - llm
      - rag
      - tool-calling
      - multi-agent

vendors:
  domestic:
    - deepseek-ai
    - QwenLM
  overseas:
    - anthropics
    - langchain-ai

output:
  dir: ./output
  formats:
    - markdown
    - json
```

删掉的字段：llm (不再需要自己调 LLM), weights, collect.time_range_days, compare, discovery, follow_groups（功能由 accounts+vendors 覆盖，从未实装）

---

## 7. Skill 更新

SKILL.md 的调整：
- 更新命令映射表 → 5 个新命令
- 新增假说树工作流：读 hypotheses → 跑沙盒 → 更新 hypotheses → 呈现
- 新增用户权重应用：读 user_weights → 解读时加权 → 记录反馈
- 去掉 v1/v2 区分

---

## 8. 迁移路径

按依赖顺序分 4 个 phase：

| Phase | 内容 | 产出 |
|-------|------|------|
| 1 | 写 payload schema + 删 dead code | models/payload.py, 清理完成 |
| 2 | 实现 5 个沙盒命令 | cli/commands/*.py |
| 3 | 写 schema.md + 更新 Skill | Claude 可调用的完整工具链 |
| 4 | 验证端到端流程 | 跑通 collect→trend→pain→opportunity→report |

---

## 9. 成功标准

- [ ] `builderdna collect agent` 独立运行，输出合法 signals.json
- [ ] `builderdna trend agent` 独立运行，输出合法 trends.json
- [ ] `builderdna pain agent` 独立运行，输出合法 pain_clusters.json
- [ ] `builderdna opportunity` 纯规则引擎运行，输出合法 opportunities.json
- [ ] 所有命令支持 `--data FILE` 和 `--output FILE`
- [ ] 所有命令输出符合 schema.md 定义
- [ ] Skill 能引导 Claude 完成完整分析循环（至少一次）
- [ ] hypotheses.json 可被 Claude 正确读写
- [ ] 旧 pipeline/ control_plane/ backend/ llm/ 全部移除，无 import 残留
