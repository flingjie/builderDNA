# uv 迁移 + 清华镜像源 设计

日期: 2026-07-20
状态: approved

## 目标

- 完整迁移到 uv 进行依赖管理和运行
- 使用清华 TUNA 镜像源加速包安装
- 清理旧的 pip/requirements.txt 遗留

## 决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| pip → uv | 完整迁移 | 统一工具链，uv 更快更现代 |
| 镜像源 | 清华 TUNA | 速度快、稳定性好 |
| 配置范围 | 仅项目级 | 隔离性好，配置跟随仓库 |
| 构建后端 | 保持 setuptools | uv 完全支持，无需变动 |

## 变更清单

### 1. pyproject.toml — 新增 [tool.uv]

在文件末尾添加：

```toml
[tool.uv]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

### 2. requirements.txt — 删除

uv 以 pyproject.toml 为唯一依赖声明，requirements.txt 不再需要。

### 3. README.md — 命令更新

| 原来 | 改为 |
|------|------|
| `pip install -e ".[dev]"` | `uv sync --dev` |
| `python cli.py ...` | `uv run bldr-dna ...` 或 `uv run python cli.py ...` |
| `pytest tests/ -v` | `uv run pytest tests/ -v` |

### 4. uv.lock — 重新生成

删除旧 uv.lock，从清华源重新 `uv lock`。

### 5. .venv — 重建

删除旧 .venv，`uv sync --dev` 重建。

## 不改动

- `pyproject.toml` 的 build-system、dependencies、scripts 保持不变
- `.gitignore` 已有 `.venv/`，无需修改
- `.env` 不动
- 源代码零改动

## 验证

- `uv sync --dev` 安装成功且走清华源
- `uv run bldr-dna --help` 正常输出
- `uv run pytest tests/ -v` 全部通过
