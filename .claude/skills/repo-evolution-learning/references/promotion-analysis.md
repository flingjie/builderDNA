# 传播内容分析（步骤 D–F）

## D. 搜索传播内容

先调用 `<skill_dir>/scripts/tavily_search.py` 做全网检索，再对实际出现的平台补定向检索。Tavily 不可用或缺少 `TAVILY_API_KEY` 时记录失败（`coverage_notes`），不要用仓库搜索替代全网覆盖结论。调用方式、参数和结果映射见 `references/tavily-search.md`。

### 查询模板

```text
"github.com/owner/repo"
"项目名" "作者名"
"项目名" launch
"项目名" release
"项目名" tutorial
"项目名" review
"项目名" 发布
"项目名" 教程
site:<平台域名> "项目名" "作者名"
```

候选平台：X/Twitter、Hacker News、Reddit、LinkedIn、Product Hunt、V2EX、掘金、知乎、微信公众号、小红书、DEV、Medium、个人博客。Tavily 的 `include_domains` 可用于定向到这些平台，但第一轮先不要过度限定，保留全网覆盖。

### 记录

- 每次查询写一条 `SearchRecord` 到 `search-log.jsonl`。`engine` 固定为 `tavily`；`results[].snippet` 使用 Tavily 返回的 `content` 摘要，不要假设已读过全文。
- 命中的候选链接写 `SourceRecord`（`kind=search_result`，`fetch_status=partial`）到 `sources.jsonl`。

### 身份与去重

1. 先用仓库链接、官网链接、作者关系确认内容身份（`repo_match`）。
2. 名称相同但无支持材料的内容 → `probable` / `rejected`，不进主平台统计。
3. 去 URL 跟踪参数；按 canonical URL 与正文相似度去重。
4. 保留转载关系（转载不重复计数）；平台原生与转载分别计数。

规则：主要平台结论基于「本次找到的独立内容 + 作者持续发布情况 + 可见互动 + 检索覆盖」。不要宣称获得完整平台传播量。

## E. 拉取文章与讨论

优先拉：首发、重要版本发布、深度解释、用户实践、有依据的质疑。每种至少尝试一条；不存在不补造。

- 用 opencli 拉正文：`opencli <site> read …`、`opencli web read --url …`、站点适配器。
- 保留正文、发布时间、身份、链接、可见指标。浏览器回退按 opencli 工具权限（串行）。
- 访问受限：保存可读摘要 + `missing_scope`。
- `fetch_status` 如实：`full` / `partial` / `blocked` / `failed`。

规则：评论只代表采集到的讨论，不代表全部用户。保留上下文，避免把引用或反讽写成作者主张。

## F. 分析表达与反馈

### 文章分析（七角，复用 twitter-learning/references/analysis-guide.md 契约）

目标读者 · 痛点 · 核心承诺 · 开场方法 · 解释结构 · 演示证据 · 行动要求 · 承诺边界。

### 反馈分析

理解困难 · 安装障碍 · 功能需求 · 实际使用案例 · 替代方案 · 质疑 · 失败报告。

### 跨平台比较

比较同一项目不同平台的表达，优先接近的版本/发布时间。说明受众、作者影响力、互动数据的限制；不要把高互动直接归因于写法。

每篇文章 → 一条 `PromotionContent`；平台分布 → `platform_stats`（带统计范围）。

### 学传播精选（学传播路径正文）

学传播正文只选两篇有差异的内容，每篇回答三问，其余内容折叠进证据：

1. 从全部 `promotion_contents` 里选 2 篇有差异的内容（不同平台或不同作者类型），标 `featured=true`；其余保留完整但不进正文。
2. 每篇 featured 内容补写 `borrowable`：哪句表达/框架值得借用、为什么。
3. 三问：别人怎样介绍它（`audience` / `hook` / `promise`）、用了什么证据（`proof`）、哪些表达值得借用（`borrowable`）。
4. 少于两篇时如实说明，不补造；正文只展示已采集到的内容。

