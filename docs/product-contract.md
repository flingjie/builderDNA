# BuilderDNA 产品契约（Product Contract）

本文档定义 BuilderDNA 的**产品边界**：它是什么、不是什么，核心对象、Skill 路由，以及不可逾越的硬边界。它是 CLAUDE.md、README.md 和 Skill descriptions 的单一事实来源。

## 1. 定位

BuilderDNA 是独立的 **Technology Intelligence Sandbox Toolkit**：

> 分析开发者、仓库和社区信号，理解技术变化，发现痛点，验证值得学习或构建的方向。

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

`BuilderProblem` 记录**外部 builder 正在处理的具体问题及其变化**：问题陈述、触发场景、任务目标、现有绕过办法、主要成本、来源证据、`observed / confirmed / resolved` 状态。轨迹通过追加 `ProblemEvent` 保留，不覆盖旧信息。跨人比较只按“任务 + 障碍”分组，不按关键词聚类；比较达到足够相似后才输出 `ProblemOpportunityCard`。

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

> **注意：** digest/distill 的 `cognitive_patterns`（技术理解的盲点与掌握度追踪）是**技术认知**关注点，属于 digest 的 `state/digest_gaps.jsonl`，**不属于**兴趣画像。兴趣画像不写入任何价值观、信念、人格或写作风格字段。

## 4. Skill 路由

### 4.1 核心技术情报

| 请求 | 唯一负责 Skill |
|------|----------------|
| 分析 GitHub 开发者技术 DNA | `builderdna` |
| 只发现/评估 GitHub repo | `repo-trend` |
| 从 Awesome List 策展发现 | `repo-awesome` |
| 只从 X 学习技术信号 | `twitter-learning` |
| 只从 Reddit 发现痛点 | `reddit-opportunity` |
| 跨源验证概念 | `concept-radar` |
| 运行完整可恢复生命周期 | `concept-radar-loop` |
| 重建开发迭代 + 传播/反馈分析 + 交互式 HTML 报告 | `repo-evolution-learning` |
| 检查历史预测与参数 | `observability` |

### 4.2 辅助认知工具

| Skill | 职责（收敛后） |
|-------|----------------|
| `reflect` | 仅复盘技术判断过程 |
| `distill` | 仅合成阶段性技术认知 |
| `digest` | 检查对技术概念/仓库/论文的真实理解 |
| `note` | 捕获与技术探索相关的观察 |
| `value-discovery` | 只输出 BuilderInterestProfile 所需信息 |
| `trace-classify` | 分析 builderDNA 自身工具执行轨迹 |
| `optimize` | 基于诊断改进确定性分析能力 |

### 4.3 路由规则

- 同一用户请求只命中**一个**主要 Skill。
- 单源请求交给专家 Skill；跨源才走 `concept-radar`。
- `concept-radar` 只接收被选中的单源发现，不反向接管单源搜索。
- `builderdna` 只编排 Python sandbox，不替代专家 Skill 的深度分析。
- `twitter-learning` 的**被选中发现**可以进入跨源验证（feed 进 `concept-radar`），方向不可逆。
- X 只负责学习信号；Reddit 只负责痛点和机会信号。

## 5. 非目标（Non-Goals）

- 不做社交回复、引用帖、私信或原创内容草稿。
- 不做获客、维护客户关系、建立个人写作风格。
- 不管理 PeerProfile、关系阶段、对话历史。
- 不接入、调用或依赖 Finch 或其他特定下游项目。
- 不输出面向特定项目的专有协议 handoff。
- 不增加 Web 服务或通用 Agent Runtime。

## 6. 职责边界

| 职责 | 所有者 |
|------|--------|
| 技术情报（采集/趋势/痛点/机会/DeveloperDNA/BuilderProblem） | Python CLI + `builderdna` Skill |
| 概念验证（Inbox→Watch→Verify→Build/Drop） | `concept-radar` / `concept-radar-loop` |
| 个性化排序（只影响优先级） | `BuilderInterestProfile` |
| 自校准（预测 vs 后续事实） | `observability` / `optimize` |
