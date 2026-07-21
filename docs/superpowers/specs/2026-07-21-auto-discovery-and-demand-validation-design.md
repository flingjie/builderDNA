# BuilderDNA 自动发现与需求验证优化设计

**日期**: 2026-07-21
**状态**: 已确认

---

## 1. 背景与目标

### 1.1 当前系统的局限

BuilderDNA 现有 Radar 系统虽然能追踪技术趋势，但存在以下关键不足：

1. **方向硬编码** — Radar 只追踪 `config.yaml` 中预配置的固定 topics，无法自动发现新兴热点领域
2. **厂商盲区** — Follow 系统仅按 star/follower 打分，不知道厂商在具体押注什么方向
3. **需求信号单一** — Pain Mining 只扫 GitHub Issues，无法交叉验证需求的真实性
4. **无中外对比视角** — 国内 AI 厂商和海外厂商的动态混在一起，差异不清晰

### 1.2 优化目标

- **自动发现**新兴垂直领域和快速增长的赛道
- **追踪国内外 AI 厂商**的技术投入方向和战略变化
- **交叉验证需求**，提高 Opportunity 输出的可信度

---

## 2. 总体架构

在现有 3 阶段 Radar（Trend → Pain → Opportunity）基础上，增加一条水平贯穿的信号增强层：

```
                      现有                         本次新增
                ┌──────────────┐           ┌──────────────────┐
                │  Trend Radar │           │  Theme Discovery  │
                │  (固定topics) │           │  (自动发现新方向)  │
                └──────┬───────┘           └────────┬─────────┘
                       │                            │
                ┌──────▼───────┐           ┌────────▼─────────┐
                │  Pain Mining │           │  Vendor Tracking  │
                │  (Issues)    │           │  (厂商行为追踪)    │
                └──────┬───────┘           └────────┬─────────┘
                       │                            │
                ┌──────▼───────┐           ┌────────▼─────────┐
                │ Opportunity  │◄──────────┤ Demand Validation │
                │ Engine       │           │ (需求交叉验证)     │
                └──────────────┘           └──────────────────┘
```

### 核心设计原则

- 新模块不改变现有 pipeline 结构，作为并行/后置增强
- 所有模块输出统一写入独立 store，通过 API 汇入前端
- 中外标签体系在 Vendor Tracking 层统一管理

---

## 3. 模块一：Theme Discovery（自动发现新方向）

### 3.1 要解决的问题

topics 硬编码在 `config.yaml`，系统只能追踪已知方向，看不到未想到的新赛道。

### 3.2 工作流程

```
GitHub Search API                 LLM                           Output
(宽搜索，不限关键词)    →    主题聚类 + 命名    →    新增/淘汰的 TopicTrend
                              + 热度评分
```

**Step 1 — 宽搜索**

- 不按 `topic:X` 搜索，按 `stars:>100 created:>YYYY-MM-DD` 结合语言过滤
- 同时扫描 `follow_groups` 中所有账号的最新 starred repos
- 每周运行一次，与现有 Radar 互不冲突

**Step 2 — 主题聚类**

- 取 repo 的 `description` + `topics` + `README 前 500 字`
- 用 LLM 做开放式聚类（不预定义类别），LLM 自主命名每个 cluster
- 聚类粒度：合并语义相近的话题，拆分内部差异大的组

**Step 3 — 热度判定**

- 对每个新发现话题计算：`velocity`（增速）、`repo_count`（项目数）、`contributor_diversity`（贡献者多样性）、`org_presence`（厂商参与度）
- 生命周期分级：🆕 emerging / 🔥 accelerating / ➡️ stable / 📉 cooling
- 与上一周期做 delta 对比

### 3.3 输出

每周生成 **新方向简报**：

- Top 5 新兴方向（值得关注但在 config 之外）
- 建议加入 `config.yaml domains.X.topics` 的新 topic
- 正在降温的方向

### 3.4 与现有系统的关系

不替代现有 Radar，作为**上游供给源**。发现的新方向可一键加入 domains 配置，由 Radar 开始常规追踪。

### 3.5 配置扩展

```yaml
discovery:
  enabled: true
  schedule: "weekly"         # weekly | daily
  max_results: 100           # 每次宽搜索获取的 repo 数
  language_filter:           # 排除语言（避免噪声）
    exclude:
      - JavaScript
      - CSS
      - HTML
      - PHP
      - Ruby
    include:                 # 仅保留（优先级高于 exclude）
      - Python
      - TypeScript
      - Rust
      - Go
      - C++
      - Jupyter Notebook
  min_stars: 100
  lookback_days: 30          # 只看最近 N 天创建的 repo
```

### 3.6 新增文件

| 文件 | 职责 |
|------|------|
| `backend/engine/discovery.py` | 宽搜索 + 主题聚类 + 热度评估逻辑 |
| `backend/models/discovery.py` | `DiscoveredTheme`, `DiscoverySnapshot` 数据模型 |
| `backend/store/discovery_store.py` | SQLite 存储，支持 `save()` / `get_latest()` / `get_delta()` |

---

## 4. 模块二：Vendor Tracking（厂商行为追踪）

### 4.1 要解决的问题

- 哪些厂商在集体押注什么方向？
- 国产 AI 厂商 vs 海外厂商的技术重点差异？
- 某个厂商最近投入方向是否突然转向？

### 4.2 数据模型

```python
VendorProfile:
    accounts: list[str]          # 关联的 GitHub 账号
    tags: list[str]              # ["🇨🇳 国产", "大模型", "推理引擎"]
    comparison_group: str        # "domestic" | "overseas"
    active_directions: [         # 当前活跃方向
        {topic: str, intensity: float, trend: "↑"|"→"|"↓"}
    ]
    recent_signals: [            # 近期信号
        {type: str, repo: str, timestamp: datetime}
    ]
```

### 4.3 追踪维度

| 维度 | 数据来源 | 说明 |
|------|---------|------|
| 组织动态 | `orgs/X/repos` | 新仓库创建、活跃度、Star 增长 |
| 成员动向 | org 成员的个人 starred/forked | 成员在个人号上关注什么 |
| 招聘信号 | org 成员 profile 变更、README hiring 标记 | 扩张方向判断 |
| 发布节奏 | Release 频率、版本号跳跃 | 产品化程度和战略重心 |

### 4.4 标签体系

在现有 `config.yaml` 扩展 `vendors` 分区：

```yaml
vendors:
  domestic:    # 🇨🇳 国产
    - deepseek-ai
    - QwenLM
    - THUDM
    - MoonshotAI
    - 01-ai
    - baichuan-inc
    - MiniMax
    - Tencent-Hunyuan
  overseas:    # 🌍 海外
    - anthropics
    - langchain-ai
    - NousResearch
    - browser-use
    - crewAIInc
    - vllm-project
    - sgl-project
```

### 4.5 差异化对比输出

每次分析生成 `VendorDiff`：

```
Agent 框架方向
  🇨🇳 国产: MoonshotAI+browser-use, QwenLM+agent-framework
  🌍 海外: anthropics+mcp-python, langchain-ai+langgraph
  📊 共性: 都在卷工具调用  |  ⚡ 差异: 国产偏应用集成 / 海外偏协议标准
```

### 4.6 与模块一的关系

Theme Discovery 发现新赛道 → Vendor Tracking 反向查询哪些厂商在该赛道已有动作 → 标记为 "早期占位信号"。

### 4.7 新增文件

| 文件 | 职责 |
|------|------|
| `backend/engine/vendor.py` | 厂商四维追踪 + 中外对比逻辑 |
| `backend/models/vendor.py` | `VendorProfile`, `VendorSnapshot`, `VendorDiff` 数据模型 |
| `backend/store/vendor_store.py` | SQLite 存储 |

---

## 5. 模块三：Demand Validation（需求交叉验证）

### 5.1 要解决的问题

Pain Mining 数据源太窄，需要交叉验证需求真实性。

### 5.2 三路验证模型

```
          ┌─────────────────────┐
          │  需求信号            │
          │  GitHub Issues      │  ← Pain Mining (已有，增强)
          │  + Discussions      │
          │  + Feature Requests │
          └─────────┬───────────┘
                    │
          ┌─────────▼───────────┐
          │  投入信号            │
          │  厂商 repo 活跃度    │  ← Vendor Tracking (模块2)
          │  招聘方向            │
          │  版本发布频率        │
          └─────────┬───────────┘
                    │
          ┌─────────▼───────────┐
          │  采纳信号            │
          │  依赖网络分析        │  ← 新增
          │  (谁在用谁的库)       │
          │  下游生态活跃度       │
          └─────────────────────┘
```

### 5.3 信心评分

三路信号汇总 → LLM 做信心评分：

| 需求信号 | 投入信号 | 采纳信号 | 结论 |
|---------|---------|---------|------|
| 🟢 强 | 🟢 强 | 🟢 强 | 高度确定 |
| 🟢 强 | 🟡 中 | 🔴 弱 | 真实用户痛点，可能缺供给 |
| 🔴 弱 | 🟢 强 | 🟡 中 | 厂商前瞻布局，观察窗口 |
| 🟢 强 | 🔴 弱 | 🔴 弱 | 潜在长尾，暂不优先 |

### 5.4 集成点

增强现有 `opportunity.py` 输出，每张 `OpportunityCard` 附加 `validation` 字段：

```python
class OpportunityCard:
    ...
    validation: ValidationResult | None  # 新增
    # {demand_score: 0.8, supply_score: 0.5, adoption_score: 0.3, confidence: "medium"}
```

### 5.5 新增/修改文件

| 文件 | 变更 |
|------|------|
| `backend/engine/validation.py` | 新增：三路信号收集 + 信心评分 |
| `backend/engine/opportunity.py` | 修改：集成 validation 字段 |
| `backend/models/opportunity.py` | 修改：增加 `ValidationResult` 模型 |

---

## 6. 前端展示方案

### 6.1 新增 Tab

| 位置 | 名称 | 展示内容 |
|------|------|---------|
| +1 tab | **Explorer** | 模块 1 输出：自动发现的 Top 新方向，卡片 + 一键加入追踪 |
| +1 tab | **Vendors** | 模块 2 输出：中外厂商对比矩阵 + 厂商详情 |

### 6.2 现有 Tab 增强

| Tab | 增强点 |
|------|--------|
| Executive Radar | Topic 卡片加厂商活跃度标签、新发现 badge |
| Trend Landscape | 无需改动 |
| Opportunity Map | 卡片加 `验证信号: 🟢强/🟡中/🔴弱` 指示灯 |

### 6.3 新增前端组件

| 组件 | 功能 |
|------|------|
| `ExplorerGrid` | 自动发现的新方向卡片，热度趋势、样本 repo、一键加入追踪按钮 |
| `VendorMatrix` | 中外厂商 × 技术方向的交叉热度矩阵 |
| `VendorDetail` | 单厂商详情页：活跃方向、招聘信号、最近动态时间线 |
| `ValidationBadge` | 需求验证三色指示灯（复用性组件） |

### 6.4 新增 API 端点

| 端点 | 功能 | 参数 |
|------|------|------|
| `GET /api/explorer` | 获取本期新发现方向 | `domain`, `window` |
| `GET /api/vendors` | 厂商概览（支持标签过滤） | `tag=domestic\|overseas` |
| `GET /api/vendors/{name}` | 单厂商详情 | `name` |
| `GET /api/compare` | 中外对比矩阵 | `dimension` |

---

## 7. 实施计划

### Phase 1: Theme Discovery（预计 1 周）

- 新建 `backend/engine/discovery.py`、`backend/models/discovery.py`、`backend/store/discovery_store.py`
- 实现宽搜索 + LLM 聚类 + 热度评估
- 新增 `GET /api/explorer` 端点
- 前端新增 Explorer Tab + ExplorerGrid 组件

### Phase 2: Vendor Tracking（预计 1 周）

- 新建 `backend/engine/vendor.py`、`backend/models/vendor.py`、`backend/store/vendor_store.py`
- 实现四维追踪 + 中外对比
- 扩展 `config.yaml` 的 vendors 配置
- 新增 `GET /api/vendors`、`GET /api/vendors/{name}`、`GET /api/compare` 端点
- 前端新增 Vendors Tab + VendorMatrix、VendorDetail 组件

### Phase 3: Demand Validation（预计 1 周）

- 新建 `backend/engine/validation.py`
- 实现三路信号交叉验证
- 增强 `OpportunityCard` 模型和 `opportunity.py`
- 前端添加 ValidationBadge 组件，增强 Opportunity Map tab

---

## 8. 风险与注意事项

- **GitHub Search API 限流** — 宽搜索比定向 topic 搜索消耗更多配额，需要控制频率（Phase 1 每周一次）
- **LLM 聚类质量** — 开放式聚类的准确性取决于 prompt 设计和 repo 数据质量，需要人工抽查
- **外部招聘数据不稳定** — 官网/招聘平台抓取可能受反爬限制，Phase 2 先以 GitHub 可获取信号为主
- **多模块并发** — Discovery / Vendor / Validation 不应阻塞主 Radar 流程，实施时采用 try/except 包裹，失败不影响主流程
