# BuilderDNA

分析 GitHub 开发者，提取技术 DNA，发现产品机会。

## 概述

BuilderDNA 是一个多阶段分析管道，输入一个或多个 GitHub 账号，通过规则聚类和 LLM 语义分析，输出该开发者的**技术洞察**和**产品/工具机会**。

```
GitHub API → 信号采集 → 规则聚类(L1) → LLM分类(L2) → 机会发现+评分 → 报告
```

## 管道

| 阶段 | 名称 | 做什么 | 用什么 |
|------|------|--------|--------|
| 1 | 采集 (Collect) | 从 GitHub 拉取 repos、stars，归一化为统一 Signal 模型 | GitHub API |
| 2 | 理解 (Understand) | L1: Jaccard 相似度聚类 → L2: LLM 语义分类生成洞察 | 规则 + LLM |
| 3 | 推荐 (Recommend) | LLM 从洞察中发现机会，按缺口评分排序 | LLM + 评分算法 |

### 详细流程

```
config.yaml  ──▶  加载配置，解析 ${ENV} 变量
    │
    ▼
Pipeline.run()
    │
    ├─ Phase 1: Collect
    │   ├─ GitHubClient.get_repos(actor)     ──▶ 仓库列表
    │   ├─ GitHubClient.get_starred(actor)   ──▶ 收藏列表
    │   └─ mapper.map_all()                  ──▶ list[Signal]（归一化）
    │
    ├─ Phase 2: Understand
    │   ├─ aggregate(signals)                ──▶ list[SignalCluster]（L1 规则）
    │   └─ classify(clusters, llm)           ──▶ list[Insight]（L2 LLM）
    │
    └─ Phase 3: Recommend
        ├─ detect(insights, llm)             ──▶ list[Opportunity]（LLM 发现）
        └─ evaluate(opportunities)           ──▶ 按 gap_score 排序
```

## 项目结构

```
BuilderDNA/
├── cli.py                  # CLI 入口 (click + rich)
├── pipeline.py             # 管道编排器
├── config.py               # 配置系统 (YAML + 环境变量)
├── config.yaml             # 配置文件
├── pyproject.toml          # 项目元数据
│
├── models/                 # 领域模型 (pydantic)
│   ├── signal.py           #   Signal + SignalCluster
│   ├── insight.py          #   Insight
│   └── opportunity.py      #   Opportunity
│
├── collect/                # 采集层（无 LLM）
│   ├── github/
│   │   └── client.py       #   GitHub API 客户端（含重试）
│   │   └── mapper.py       #   原始数据 → Signal 映射
│   └── store.py            #   SQLite 快照存储
│
├── insight/                # 理解层
│   ├── aggregator.py       #   L1 规则聚类（Jaccard + Union-Find）
│   └── classifier.py       #   L2 LLM 语义分类
│
├── opportunity/            # 推荐层
│   ├── detector.py         #   LLM 机会发现
│   └── evaluator.py        #   缺口评分排序
│
├── llm/
│   └── client.py           #   LLM 客户端（OpenAI 协议，含重试）
│
├── output/                 # 输出层
│   ├── cli.py              #   终端渲染 (rich)
│   ├── markdown.py         #   Markdown 报告
│   └── json_out.py         #   JSON 报告
│
├── follow/                  # 账号关注价值评估
│   └── scorer.py            #   Stars + Followers 评分
│
├── snapshots/              # SQLite 快照文件
└── tests/                  # 测试（63 个）
    ├── test_collect/
    ├── test_insight/
    ├── test_opportunity/
    ├── test_follow/
    ├── test_llm/
    ├── test_models/
    ├── test_pipeline/
    ├── test_config.py
    └── test_e2e.py
```

## 快速开始

### 环境要求

- Python >= 3.11
- GitHub Personal Access Token
- LLM API Key（支持任意 OpenAI 兼容接口）

### 安装

```bash
git clone <repo-url>
cd BuilderDNA
pip install -e ".[dev]"
```

### 配置

1. 创建 `.env` 文件：

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxx
LLM_BASE_URL=https://your-llm-gateway/v1   # 可选
```

2. 编辑 `config.yaml`：

```yaml
accounts:
  - 目标GitHub账号1
  - 目标GitHub账号2

github:
  token: ${GITHUB_TOKEN}

llm:
  provider: openai
  model: deepseek-v4-pro       # 或其他模型
  api_key: ${OPENAI_API_KEY}
  base_url: ${LLM_BASE_URL}

weights:                        # 信号权重
  repo: 5.0
  star: 1.0
  commit: 3.0

output:
  dir: ./output
  formats:
    - markdown
    - json

collect:
  time_range_days: 365          # 采集时间范围

compare:
  enabled: true                 # 增量对比模式
```

### 运行

```bash
# 完整分析
python cli.py run

# 强制不对比
python cli.py run --no-compare

# 指定配置文件
python cli.py run -c custom-config.yaml

# 查看某个账号的信号
python cli.py show <账号名>

# 查看历史快照
python cli.py snapshots

# 对比两个快照
python cli.py diff <snapshot1> <snapshot2>

# 账号关注价值评估
python cli.py follow alice bob charlie
python cli.py follow alice bob --top 5  # 只看前5名
```

### 运行测试

```bash
pytest tests/ -v
```

## 核心模型

### Signal（信号）

统一的开发者活动单元，所有数据源归一化到此模型。

```python
Signal(
    id="gh_repo_alice_toolkit",   # 唯一标识
    source="github",               # 数据来源
    type="repo",                   # 类型: repo/star/commit
    timestamp=datetime(...),       # 时间戳
    weight=5.0,                    # 预设权重
    actor="alice",                 # 被分析的开发者
    target="alice/toolkit",        # 实体标识
    meta={"topics": [...], ...},   # 结构化摘要
    raw={...},                     # 完整 API 原始响应
)
```

### Insight（洞察）

从信号聚类中通过 LLM 语义理解生成的技术洞察。

```python
Insight(
    id="in_001",
    tags=["llm", "agent", "python"],     # 技术标签
    summary="该开发者专注于...",           # 中文摘要
    strength=1338.0,                      # 加权强度
    trend="rising",                       # 趋势: rising/stable/fading
    signal_count=1294,                    # 支撑信号数
    evidence=["alice/agent-kit"],         # 支撑证据
    source_cluster_id="cluster_abc123",   # 来源聚类ID
)
```

### Opportunity（机会）

从洞察中发现的单条产品/工具机会。

```python
Opportunity(
    id="op_001",
    title="AI驱动的文档解析平台",           # 中文标题
    pain_point="多格式文档解析复杂...",     # 核心痛点
    demand_score=4.0,                      # 需求热度 1-5
    competition_score=2.0,                 # 竞争强度 1-5（越低=越少竞争）
    gap_score=2.0,                         # demand / competition
    recommended_action="开发集成LLM...",    # 中文建议行动
    source_insights=["in_001"],            # 支撑洞察ID
)
```

## 输出格式

### 终端 (CLI)

使用 Rich 渲染，彩色面板展示洞察和机会摘要：

```
╭─────────────────╮
│ BuilderDNA 分析 │
╰─ 快照: 7c0447c5─╯

技术洞察
╭─── tags ───────────────────────────────────────────╮
│ 中文摘要内容                                        │
│ 关键仓库: owner/repo1, owner/repo2                   │
╰─────────────────────────────────────────────────────╯

机会
 #  标题        缺口  建议
 1  机会标题    2.00  行动建议...
```

### Markdown

完整的分析报告，含洞察详情和机会详情，有来源归属（关联账号、关键仓库）。

### JSON

结构化全量数据，包含所有信号、洞察、机会的完整字段。

## 设计原则

| 原则 | 说明 |
|------|------|
| 原始数据永不丢弃 | 每个 Signal 保留 `raw` 字段存储完整 API 响应 |
| 管道可追溯 | 每层输出可追溯到源头（cluster → insight → opportunity） |
| LLM 仅用于语义判断 | 确定性计算（聚类、评分）不依赖 LLM |
| 中文输出 | 洞察摘要、机会标题/痛点/建议均为中文 |
| 优雅降级 | LLM 不可用时自动 fallback 到规则生成 |

## 许可证

MIT
