# Builder's Lens — 从 builder 视角分析项目的方法论

当用户要求"从 builder 角度分析这个项目"或"挖掘值得借鉴的做法"时，使用此框架。
结合 `gh api` 获取 commit 历史、release 记录、PR 数据，然后按以下 10 个维度解读。

## 数据采集

```bash
# Commit 历史（最近 40 条）
gh api repos/{owner}/{repo}/commits --jq '.[:40] | .[] | {sha: .sha[0:7], date: .commit.author.date, message: .commit.message | split("\n")[0]}'

# Release 历史
gh api repos/{owner}/{repo}/releases --jq '.[:10] | .[] | {tag: .tag_name, date: .published_at, name: .name}'

# 贡献者统计
gh api repos/{owner}/{repo}/stats/contributors

# PR 合并记录
gh api "repos/{owner}/{repo}/pulls?state=closed&per_page=20" --jq '.[] | {title, merged: .merged_at, user: .user.login}'

# Commit 频率分布（按日聚合）
gh api "repos/{owner}/{repo}/commits?per_page=100" --jq '.[].commit.author.date' | cut -c1-10 | sort | uniq -c

# 总 commit 数（分页遍历）
# 第一个也是最后一个 commit 的日期
```

## 10 维度分析框架

对采集到的数据，从以下 10 个维度做定性解读。每条必须给出具体证据（日期/数字/commit message 原文）。

### 1. 价值量化策略

- 项目第一天有没有 benchmark 或量化数据？
- 数据来自真实场景还是 toy example？
- benchmark 是否可复现（有脚本/方法论文档）？
- 关注 commit 中 benchmark 相关 message 的密度

### 2. 版本号策略

- 初始版本号是什么？有无跳跃？
- release 频率（总 releases / 项目天数）
- release notes 的风格（技术型 vs 人格化）
- 版本号是否用于建立信任感？

### 3. 平台覆盖策略

- 支持多少平台/agent？
- 横向扩展的节奏（从核心平台到外围）
- 每个平台的适配成本（代码量 + 时间）
- 是 plugin/hook 层还是规则文件层？
- commit 中平台相关 message 的占比

### 4. README 信息架构

- 第一屏有什么？（标语/数据/安装命令）
- 有没有 Before/After 示例？
- benchmark 数据是否在前 300 行？
- 安装指南的复杂度（几个步骤？几个平台？）
- 篇幅分布：概念 vs 数据 vs 安装 vs 命令参考

### 5. Benchmark 可信度

- 有可复现的 benchmark 吗？
- 是否有对照组（control arm）？
- 是否处理了质疑/issue 中的质疑？
- benchmark 方法论文档的深度
- 是否有模型/场景维度的对比分析？

### 6. Commit 规范

- 是否使用 conventional commits（feat/fix/docs/test/chore）？
- message 是否包含"为什么"而不仅是"做了什么"？
- issue 关联率（#NNN 出现的频率）
- 单日最高 commit 数和分布模式

### 7. 核心 IP 定位

- 项目的核心 IP 是什么？（思维模型？算法？集成？）
- 这个 IP 能否在一页纸/30 秒内讲清？
- 是否依赖特定平台/API？
- 围绕核心 IP 的 commit 占比 vs 周边工作

### 8. 贡献者门槛梯度

- 有几层贡献门槛？（翻译/修 bug/新平台/核心逻辑）
- 外部贡献者数量和贡献类型分布
- 核心维护者的 commit 占比
- 是否有贡献指南/CONTRIBUTING.md？

### 9. 开发节奏

- 按周聚合的 commit 频率曲线
- 是"爆发→稳定"还是"匀速推进"？
- 最活跃日发生了什么？（突击什么主题？）
- 当前处于哪个阶段？（活跃开发/稳定维护/放缓）

### 10. 品牌人格化

- 项目有"人格"吗？（logo/标语/release notes 风格）
- 这个人格是否一致（贯穿 README/release/issues）？
- 是否有人格化命名（命令/功能/模式的名字）？
- 人格化对传播的影响（star 增长速度作为 proxy）

## 输出格式

分析结果用中文呈现，每条维度包含：
- **观察**：具体数据/commit/行为
- **借鉴**：对 builder 的启示（怎么做/为什么有效）

示例见下方。每轮分析后问用户："要深入某个维度吗？或者分析另一个项目？"

## 示例：ponytail 的 Builder 分析

(完整分析见 `.claude/skills/builderdna/references/` 下的案例文件)
