# BuilderDNA 产品契约（Product Contract）

本文档定义 BuilderDNA 的**产品边界**：它是什么、不是什么，核心对象、Skill 路由，以及不可逾越的硬边界。它是 CLAUDE.md、README.md 和 Skill descriptions 的单一事实来源。

## 1. 定位

BuilderDNA 是独立的 **Technology Intelligence Sandbox Toolkit**：

> 从 Agent 开发者与 AI 使用者的真实任务中发现问题，保留可追溯证据，验证潜在需求，帮助决定下一步值得研究或构建什么。同时保留技术趋势、仓库发现与技术学习，作为"提示新可能性"的信号；需求判断回到任务、障碍、已有办法与实际代价。

核心闭环：

```text
采集外部信号
→ 识别趋势与痛点
→ 形成可证伪假设
→ 跨源验证
→ 决定 Watch / Verify / Build / Drop
→ 用后续事实校准判断
```

北极星指标：**有多少技术判断经后续证据验证，并真正改变了学习或构建决策。**

## 2. 硬边界（不可逾越）

- BuilderDNA **独立运行**，不接入、调用或依赖任何外部下游项目（含 Finch）。
- 不共享数据库、状态文件、Python 包、Skill、CLI 或输出契约。
- 不输出面向特定下游项目的 handoff。
- 不管理 PeerProfile、关系阶段、对话历史或个人写作风格。
- **不生成社交回复、引用帖、私信或原创内容草稿。**
- **不做获客、不维护客户关系。**
- 不增加 Web 服务或通用 Agent Runtime。

Claude Code 负责语义推理与编排；Python CLI 负责确定性数据、评分、状态和门禁。

## 3. 核心对象

### 3.1 外部世界模型

```text
Signal          — 统一不可变事件（所有来源归一化到此）
RepoSignal      — 仓库信号
IssueSignal     — issue 信号
TopicTrend      — 主题趋势
PainCluster     — 痛点聚类
OpportunityCard — 机会卡片
DeveloperDNA    — 开发者技术实践分析（非关系管理档案）
BuilderProblem  — 外部 builder 的问题记录与实践轨迹（非关系管理档案）
ProblemEvent    — 不可变轨迹事件
ProblemOpportunityCard — 由跨人问题比较得到的可验证机会卡
```

`DeveloperDNA` 是对**外部开发者技术实践**的分析：问题域、构建模式、技术选型、迭代风格、维护行为、测试可靠性信号、开源协作、从想法到交付的证据。它**不是**关系管理档案，不生成「是否值得结交」类判断。

`BuilderProblem` 记录**外部 builder 正在处理的具体问题及其变化**：问题陈述、触发场景、任务目标、障碍、现有绕过办法、主要成本、来源证据、`observed / confirmed / resolved` 状态。轨迹通过追加 `ProblemEvent` 保留，不覆盖旧信息。跨人比较只按”任务 + 障碍”分组，不按关键词聚类；比较达到足够相似后才输出 `ProblemOpportunityCard`。

两个人群共用同一套 `BuilderProblem` 模型，通过 `user_segment` 区分，不为 AI 使用者另建数据管线：

- **Agent 开发者**：调试、评测与失败恢复，核心观察复现、验收、返工与人工补救。
- **AI 使用者**：学习与知识管理，核心观察具体任务、知识调用、核验与跨工具操作。

无 GitHub 账号或公开身份也可记录；未知身份只使用来源内的局部引用，不虚构独立人物。人物信息（来源身份、用户角色、项目与任务上下文）只用于问题判断，不用于关系管理。

### 3.2 概念验证模型

```text
ConceptCard        — 概念卡片
ConceptEvidence    — 概念证据
RadarReview        — 雷达回顾
ExperimentProposal — 最小实验提案
OutcomeEvidence    — 结果证据
```

生命周期：

```text
INBOX → WATCH → VERIFY → BUILD
                    └──→ DROP
```

**成熟度描述证据状态，阶段描述用户决策，两者分离。**

### 3.3 用户相关模型

`BuilderInterestProfile`（原泛化的 `user_dna` 收敛而来）只表达：

```text
domains
technical_adjacencies
problem_preferences
build_constraints
learning_goals
risk_tolerance
```

它**只能改变排序和推荐优先级**，不能改变：证据强度、趋势阶段、痛点严重度、假设成熟度、Build 硬门槛。

> **注意：** 兴趣画像不写入任何价值观、信念、人格或写作风格字段。个人认知工具（note/reflect/distill/digest）已迁出本仓，不属于产品对象。

## 4. Skill 路由

### 4.1 核心技术情报

| 请求 | 唯一负责 Skill |
|------|----------------|
| 分析 GitHub 开发者技术 DNA | `builderdna` |
| 只发现/评估 GitHub repo | `repo-trend` |
| 从 Awesome List 策展发现 | `repo-awesome` |
| 只从 X 学习技术信号 | `twitter-learning` |
| 只从 Reddit 发现痛点 | `reddit-opportunity` |
| 跨源验证概念 / 完整雷达生命周期 | `concept-radar` |
| 重建开发迭代 + 传播/反馈分析 + 交互式 HTML 报告 | `repo-evolution-learning` |
| 检查历史预测与参数 | `observability` |

### 4.2 辅助产品工具

| Skill | 职责（收敛后） |
|-------|----------------|
| `value-discovery` | 只输出 BuilderInterestProfile 所需信息 |
| `trace-classify` | 分析 BuilderDNA 自身工具执行轨迹 |
| `optimize` | 基于诊断改进确定性分析能力 |

### 4.3 路由规则

- 同一用户请求只命中**一个**主要 Skill。
- 单源请求交给专家 Skill；跨源才走 `concept-radar`。
- `concept-radar` 只接收被选中的单源发现，不反向接管单源搜索。
- `builderdna` 只编排 Python sandbox，不替代专家 Skill 的深度分析。
- `twitter-learning` 的**被选中发现**可以进入跨源验证（feed 进 `concept-radar`），方向不可逆。
- X 可提供公开问题线索；Reddit 可提供痛点与机会线索。单源请求仍走各自专家 Skill，跨源整合仍归 `concept-radar`，方向不可逆。

## 5. 非目标（Non-Goals）

- 不做社交回复、引用帖、私信或原创内容草稿。
- 不做获客、维护客户关系、建立个人写作风格。
- 访谈研究方面：只"设计研究问题、分析用户提供的研究材料"；不"联系对象、准备开场、记录关系与跟进"（这些属下游项目）。
- 不管理 PeerProfile、关系阶段、对话历史。
- 不接入、调用或依赖 Finch 或其他特定下游项目。
- 不输出面向特定项目的专有协议 handoff。
- 不增加 Web 服务或通用 Agent Runtime。

## 6. 职责边界

| 职责 | 所有者 |
|------|--------|
| 技术情报（采集/趋势/痛点/机会/DeveloperDNA/BuilderProblem） | Python CLI + `builderdna` Skill |
| 概念验证（Inbox→Watch→Verify→Build/Drop） | `concept-radar` + `concept`/`radar` CLI |
| 个性化排序（只影响优先级） | `BuilderInterestProfile` |
| 自校准（预测 vs 后续事实） | `observability` / `optimize` |
