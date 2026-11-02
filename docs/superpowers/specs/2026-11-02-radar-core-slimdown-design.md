# Radar-Core Slimdown 设计

日期：2026-11-02
状态：已确认（用户逐节批准）

## 背景与目标

上一轮 "aggressive slimdown" 之后，项目仍有约 91 个非测试 Python 文件、2.8 万行代码、929 个测试。近两个月实际使用的只有 **concept + radar**（概念生命周期与雷达扫描）。本次目标：以 concept-radar 为保留内核，激进删除其余未使用的管道、模块与 skill，降低维护面。

处置原则：未使用模块**直接删除**（git 历史可找回），不做归档分支。

## 保留边界（已验证闭合）

依赖排查确认保留集的依赖边界闭合：

- `cli/commands/{concept,radar}.py` 依赖 `concepts/`、`models/{concept,radar_payload}.py`、`experiments/`、observability 的 `RunTelemetry`/`OutputLevel`/`vprint`。
- `concepts/adapters/{manual_x,reddit}.py` 仅以类型方式依赖 `signals/models.py` 的 `Signal`。
- Reddit 信号摄入链：`investigations/actions.py` → `concepts/adapters/reddit.py` → concept evidence。`reddit-opportunity` skill 是 `investigate` 命令的薄封装。**investigations/ 与 reddit-opportunity 绑定保留。**
- `radar experiment` 子命令被 concept-radar skill 引用 → `experiments/` 整包保留。

## 第 1 节：删除清单

### 整包删除
- `collector/` — GitHub 采集（client/cache/rate_limit/normalizer），只服务 collect
- `intelligence/` — 全部：trend、pain、opportunity、developer_dna、builder_problems
- `signals/store.py` — SQLite 信号存储（保留 `signals/models.py`）
- `observability/` 中的 `behavior.py`、`snapshot.py`、`hypothesis.py`、`diagnostics.py`、`metrics.py`

### CLI 命令删除（`cli/main.py` 同步修改）
- 删：collect、trend、pain、pain-finalize、opportunity、report、observability、dna、builders 及 `cli/commands/` 对应文件
- 留：concept、radar、investigate、config

### 模型删除
- 删：`models/payload.py`、`models/builder_problem.py`、`models/builder_interest_profile.py`
- 留：`models/concept.py`、`models/radar_payload.py`

### Skill 删除（`.claude/skills/`）
- 删：`builderdna`、`observability`、`optimize`、`value-discovery`、`trace-classify`
- 留：`concept-radar`、`reddit-opportunity`、`twitter-learning`、`repo-trend`、`repo-awesome`、`repo-evolution-learning`

### 随动删除
- 被删模块对应的全部测试文件（预计砍掉一半以上测试）
- 失效 state 文件：`state/hypotheses.json`、`state/behavior_log.jsonl`、`state/builder_interest_profile.json`、`state/bootstrap.json`
- `references/repo-scout/` 等参考材料：逐一核对，仅被已删 skill 引用的删除（repo-trend/repo-awesome 仍引用的保留）
- `config.yaml` 中只服务采集管道的段：embedding、vendors、accounts/domains 等

## 第 2 节：保留集的裁剪

- **`concepts/adapters/github.py` 删除** — 无任何非测试代码引用（孤儿适配器）。
- **`cli/commands/schema_validation.py` 删除** — 只被 trend/pain/opportunity 与 `models/payload.py` 引用。
- **`observability/` 收缩为 `telemetry.py` + `output.py`** — 重写 `__init__.py`，只导出保留集实际使用的符号（`RunTelemetry`、`OutputLevel`、`vprint` 等）。
- **`signals/` 收缩为 `models.py`** — 保持 `from signals.models import Signal` 导入路径不变，避免无谓改动面。
- **`config.py` + `config` 命令保留** — 成本低，排查配置有用。
- **`experiments/`、`investigations/` 整包保留不动。**
- **依赖清理** — 删除后扫描 `pyproject.toml`，去掉不再被导入的依赖（预计含 scikit-learn/TF-IDF、Ollama embedding 相关；httpx 是否可删以 investigations 的实际导入为准）。

## 第 3 节：文档与契约同步

- **`CLAUDE.md` 重写** — Commands 只留 concept/radar/investigate/config；Architecture 重画为 concepts + investigations + experiments 三支；Skills 表与 Key Files 表同步删行。
- **`schema.md` 收缩** — 只留 concept/radar/investigate 相关 payload 说明。
- **`docs/product-contract.md` 更新** — 产品边界改为「concept-radar 生命周期 + 信号源 skill」，routing 规则删除指向已删 skill 的条目。
- **`.env.example` 清理** — 删 EMBEDDING_BASE_URL 等失效变量；GITHUB_TOKEN 以保留代码的实际引用为准决定去留。
- **`tests/test_skill_routing.py` 改写**（非删除）— 使其校验新的 skill 集合与路由契约。

## 第 4 节：执行顺序与验证

按依赖方向从叶到根删除，每步结束跑 `uv run pytest tests/ -q`：

1. 删 `intelligence/`、`collector/`、`signals/store.py` + 对应 CLI 命令与测试 → 测试
2. 删 `models/{payload,builder_problem,builder_interest_profile}.py`、`schema_validation.py`、`concepts/adapters/github.py` + 对应测试 → 测试
3. 收缩 `observability/`、改写 `cli/main.py` → 测试
4. 删 skill 目录 + state 文件 + `config.yaml` 段 + `pyproject.toml` 依赖清理 → 测试
5. 文档同步（第 3 节全部）
6. 终验：
   - 全量测试通过
   - 保留命令冒烟：`concept list`、`radar scan --radar agent-reliability`、`investigate start --preset production-agent-failures`（或 dry-run 等价操作）、`config --show`
   - `rg` 全仓扫描被删模块名（`intelligence`、`collector`、`payload`、`builder_problem` 等），确认代码、skill、文档零残留引用

## 非目标

- 不重构保留集内部结构（如拆分 888 行的 `radar.py`）——本次只做删除与随动收缩
- 不改变保留命令的行为与输出 schema
- 不动 `~/.claude/skills/` 下的个人认知类 skill（不属于本产品）
