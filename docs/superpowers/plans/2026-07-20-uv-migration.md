# uv 迁移 + 清华镜像源 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目从 pip 完整迁移到 uv，配置清华 TUNA 镜像源

**Architecture:** 纯配置变更，不涉及源代码改动。在 `pyproject.toml` 添加 `[tool.uv]` 配置清华源，删除冗余的 `requirements.txt`，更新 README 中的命令，重建虚拟环境

**Tech Stack:** uv 0.4.x, Python 3.11+, setuptools

## Global Constraints

- Python >= 3.11（来自 `pyproject.toml`）
- uv 已安装（系统中有 uv 0.4.30）
- 清华源 URL: `https://pypi.tuna.tsinghua.edu.cn/simple`
- 不影响任何源代码、测试、.env 配置

---

### Task 1: 配置 pyproject.toml + 清理冗余文件

**Files:**
- Modify: `pyproject.toml` (末尾追加)
- Delete: `requirements.txt`

**Interfaces:**
- Produces: `pyproject.toml` 包含 `[tool.uv]` 段，后续 Task 2 依赖此配置

- [ ] **Step 1: 在 pyproject.toml 末尾添加 [tool.uv] 配置**

现有 pyproject.toml 末尾内容：
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

在此之后追加：
```toml

[tool.uv]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

- [ ] **Step 2: 删除 requirements.txt**

```bash
rm requirements.txt
```

- [ ] **Step 3: 提交变更**

```bash
git add pyproject.toml
git rm requirements.txt
git commit -m "chore: migrate to uv with Tsinghua mirror, remove legacy requirements.txt"
```

---

### Task 2: 重建虚拟环境并锁定依赖

**Files:**
- Create: `.venv/` (重建)
- Modify: `uv.lock` (重新生成)

**Interfaces:**
- Consumes: `pyproject.toml` 中的 `[tool.uv]` 清华源配置

- [ ] **Step 1: 删除旧的虚拟环境和 lock 文件**

```bash
rm -rf .venv
rm uv.lock
```

- [ ] **Step 2: 安装依赖（从清华源）**

```bash
uv sync --dev
```

观察输出，确认包下载 URL 包含 `tuna.tsinghua.edu.cn`。

- [ ] **Step 3: 确认 uv.lock 已生成**

```bash
ls -la uv.lock
```

- [ ] **Step 4: 提交变更**

```bash
git add uv.lock
git commit -m "chore: regenerate uv.lock from Tsinghua mirror"
```

---

### Task 3: 更新 README 命令

**Files:**
- Modify: `README.md`

**Interfaces:**
- 无程序接口依赖

- [ ] **Step 1: 更新安装命令**

找到以下行：
```markdown
git clone <repo-url>
cd BuilderDNA
pip install -e ".[dev]"
```

替换为：
```markdown
git clone <repo-url>
cd BuilderDNA
uv sync --dev
```

- [ ] **Step 2: 更新运行命令**

找到"运行"段的全部 `python cli.py`，替换为 `uv run bldr-dna`。

具体来说，将：
```markdown
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
```

替换为：
```markdown
```bash
# 完整分析
uv run bldr-dna run

# 强制不对比
uv run bldr-dna run --no-compare

# 指定配置文件
uv run bldr-dna run -c custom-config.yaml

# 查看某个账号的信号
uv run bldr-dna show <账号名>

# 查看历史快照
uv run bldr-dna snapshots

# 对比两个快照
uv run bldr-dna diff <snapshot1> <snapshot2>

# 账号关注价值评估
uv run bldr-dna follow alice bob charlie
uv run bldr-dna follow alice bob --top 5  # 只看前5名
```
```

- [ ] **Step 3: 更新测试命令**

找到：
```markdown
pytest tests/ -v
```

替换为：
```markdown
uv run pytest tests/ -v
```

- [ ] **Step 4: 提交变更**

```bash
git add README.md
git commit -m "docs: update README commands from pip to uv"
```

---

### Task 4: 验证

- [ ] **Step 1: 确认 CLI 入口点正常**

```bash
uv run bldr-dna --help
```

预期：输出 click 生成的帮助信息，无错误。

- [ ] **Step 2: 运行测试**

```bash
uv run pytest tests/ -v
```

预期：63 个测试全部通过。

- [ ] **Step 3: 确认 pip 痕迹已完全清除**

```bash
grep -r "pip install" . --include="*.md" --include="*.py" --include="*.toml" --exclude-dir=.git --exclude-dir=.venv 2>/dev/null
```

预期：无输出。
