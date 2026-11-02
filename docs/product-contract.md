# BuilderDNA 产品契约（Product Contract）

本文档定义 BuilderDNA 的**产品边界**：它是什么、不是什么，核心对象、Skill 路由，以及不可逾越的硬边界。它是 CLAUDE.md、README.md 和 Skill descriptions 的单一事实来源。

## 1. 定位

BuilderDNA 是 **concept-radar 生命周期 + 信号源 skill 编排**：

> 从弱信号与单源发现中形成可证伪概念，跨源验证证据，经 Inbox → Watch → Verify → Build/Drop 决定下一步值得研究或构建什么。GitHub / X / Reddit / Awesome List 等信号源 skill 负责各自的单源发现；跨源综合与门禁归 `concept-radar`。

核心闭环：

```text
单源发现（repo / X / Reddit / awesome）
→ 选中线索进入概念 Inbox
→ 跨源验证与评分
→ 决定 Watch / Verify / Build / Drop
→ 用后续结果证据校准判断
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

Claude Code 负责语义推理与编排；Python CLI 负责确定性概念状态、评分、调查控制平面和门禁。

## 3. 核心对象

### 3.1 信号与调查

```text
Signal                 — 统一不可变事件类型（adapters 归一化到此）
Investigation          — 有界 Reddit 痛点调查（状态机 + budget）
ActionRecord           — 不可变动作与观测记录
EvidenceRecord         — 调查侧证据（SourceHandoffItem + 稳定 ID）
PainClusterCandidate   — 单源发现产物（不是 ConceptCard）
```

Reddit 调查经 `concepts/adapters/reddit.py` 将证据摄入概念体系；`reddit-opportunity` skill 是 `investigate` 命令的薄封装。

### 3.2 概念验证模型

```text
ConceptCard        — 概念卡片
ConceptEvidence    — 概念证据
RadarReview        — 雷达回顾
RadarRunPayload    — 雷达运行摘要（按源覆盖）
ExperimentProposal — 最小实验提案（FDE-Gym 导出）
OutcomeEvidence    — 结果证据
```

生命周期：

```text
INBOX → WATCH → VERIFY → BUILD
                    └──→ DROP
```

**成熟度描述证据状态，阶段描述用户决策，两者分离。**

## 4. Skill 路由

### 4.1 核心技术情报（6 owners）

| 请求 | 唯一负责 Skill |
|------|----------------|
| 只发现/评估 GitHub repo | `repo-trend` |
| 从 Awesome List 策展发现 | `repo-awesome` |
| 只从 X 学习技术信号 | `twitter-learning` |
| 只从 Reddit 发现痛点 | `reddit-opportunity` |
| 跨源验证概念 / 完整雷达生命周期 | `concept-radar` |
| 重建开发迭代 + 传播/反馈分析 + 交互式 HTML 报告 | `repo-evolution-learning` |

### 4.2 路由规则

- 同一用户请求只命中**一个**主要 Skill。
- 单源请求交给专家 Skill；跨源才走 `concept-radar`。
- `concept-radar` 只接收被选中的单源发现，不反向接管单源搜索。
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
| 概念验证（Inbox→Watch→Verify→Build/Drop） | `concept-radar` + `concept`/`radar` CLI |
| Reddit 有界调查 → 概念证据 | `reddit-opportunity` + `investigate` CLI |
| 单源 GitHub / Awesome / X 发现与学习 | `repo-trend` / `repo-awesome` / `twitter-learning` / `repo-evolution-learning` |
| 配置检视 | `config` CLI |
