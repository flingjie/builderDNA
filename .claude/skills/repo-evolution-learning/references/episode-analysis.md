# 开发迭代分析（步骤 A–C）

## A. 确认仓库身份

1. 校验 URL / `owner/repo`，识别是仓库、PR 还是 Issue。
2. `builderdna repo-learning init --repo … [--entry-url …]` 建立 run 工作区。
3. `builderdna repo-learning collect --run-dir <dir>`（PR 入口加 `--entry-url`）。
4. 读 `sources.jsonl` 的 `github_repo`（元数据）与 `github_readme`，收集：
   - 项目别名（旧名、新名、别称）
   - 官网链接（`homepage`）
   - 公开作者账号（README 或官网明确链接的）
5. 身份关系要有来源（写进 `repo_identity.identity_evidence`）。
6. 排除同名项目：名称相同但无支持材料的搜索结果只进候选区，不进主统计。

规则：

- 仓库迁移/改名时保留旧名与新名（`project_names`）。
- 作者身份优先依据仓库或官网的明确链接，不要仅凭相似昵称认定。
- 无法确认的，`repo_match=probable` 或 `rejected`。

## B. 选择开发迭代

1. 读限定范围内的 Issue / PR 元数据（仓库入口时 `collect` 已拉 `candidate_episodes` 个候选）。
2. 优先选「有问题描述 + 方案讨论 + Review 修改 + 测试或后续修复」的案例。
3. 记录选择理由与排除理由（可写进 `episode` 的 `coverage_notes` 或 `analysis.coverage_notes`）。
4. 选中后 `collect --run-dir <dir> --entry-url <PR>` 拉全量：普通评论、Review、行内评论、提交、文件差异。
5. 按需读历史版本的相关代码（`github_commit` / `github_file`）。
6. 读有明确链接或主题匹配的后续记录（`github_issue` follow-ups），标记匹配依据。

规则：

- 不要把 README 的当前架构解释直接当成早期设计理由。
- Squash 或缺早期提交时，说明无法完整还原（写进 `coverage_notes`）。

## C. 重建决策

按时间整理：问题出现 → 初始方案 → 评审反馈 → 实现调整 → 验证 → 后续结果。

每个决策回答五问：

1. 作者当时知道什么？
2. 有哪些选项？
3. 什么约束推动选择？
4. 牺牲了什么？
5. 最终验证了什么？

规则：

- 作者没提过的替代方案，标「分析者提出」，写成 `evidence_status=inferred`，不要写成作者已比较过的方案（那应是 `sourced` 且带引用）。
- 合并状态与效果证据分开记录：`validation` 里区分「作者称」（sourced + 引用作者原话）与「已验证结果」（sourced + 引用测试/日志）。
- 每个 `Claim` 的 `evidence_status` 精确：材料直接支持才 `sourced`；你的重建推断是 `inferred`；两者都不是则 `unknown`。
