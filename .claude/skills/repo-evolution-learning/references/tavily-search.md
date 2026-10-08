# Tavily 搜索（步骤 D）

## 前置条件

运行前设置 `TAVILY_API_KEY`。推荐写入 BuilderDNA 根目录的本地 `.env`，不要硬编码在 skill 文件、日志或 `analysis.json` 中。脚本会按当前目录 `.env`、BuilderDNA 根目录 `.env` 的顺序自动加载；也可用 `--env-file <path>` 显式指定。

```bash
export TAVILY_API_KEY="tvly-..."
```

## 命令

脚本位于本 skill 的 `scripts/tavily_search.py`。用 `<skill_dir>` 表示本 skill 的绝对目录；运行前先确认该目录存在。

```bash
python <skill_dir>/scripts/tavily_search.py \
  --query '"github.com/tt-a1i/archify"' \
  --max-results 10 \
  --search-depth basic \
  --topic general \
  --env-file <builder_dir>/.env \
  --include-domains '' \
  --exclude-domains ''
```

常用参数：

- `--query`：必填，搜索词。
- `--max-results`：1–20，默认 10。
- `--search-depth`：`basic`（快）或 `advanced`（更慢、更完整）。
- `--topic`：`general`、`news`、`finance`。
- `--include-answer`：需要 Tavily 合成答案时加。
- `--include-raw-content`：需要原文全文时加，结果会显著增大。
- `--include-domains` / `--exclude-domains`：逗号分隔域名。平台定向检索用 `include_domains`。
- `--days`：只取最近 N 天。
- `--env-file`：可选，显式指定含 `TAVILY_API_KEY` 的 `.env` 文件。

## 查询模板

第一轮保持全网覆盖，不要先加平台域名。

```text
"github.com/owner/repo"
"项目名" "作者名"
"项目名" launch
"项目名" release
"项目名" tutorial
"项目名" review
"项目名" 发布
"项目名" 教程
```

候选平台：X/Twitter、Hacker News、Reddit、LinkedIn、Product Hunt、V2EX、掘金、知乎、微信公众号、小红书、DEV、Medium、个人博客。

第二轮再对已出现的平台补定向查询，例如：

```bash
python <skill_dir>/scripts/tavily_search.py \
  --query '"项目名" "作者名"' \
  --include-domains 'x.com,twitter.com'
```

## 输出映射

脚本 stdout 是一个 JSON 对象。把其中字段写入 `search-log.jsonl` 的 `SearchRecord`：

| 脚本字段 | SearchRecord 字段 |
|---|---|
| `engine` | `engine`（固定为 `tavily`） |
| `query` | `query` |
| `searched_at` | `searched_at` |
| `results[].title` | `results[].title` |
| `results[].url` | `results[].url` |
| `results[].snippet` | `results[].snippet` |
| `coverage_notes` | `coverage_notes` |

`id` 使用：

```text
tavily:<searched_at>:<sha1(query)[:12]>
```

只有搜索摘要时，把候选链接写为 `SourceRecord`，`kind=search_result`、`fetch_status=partial`。不要把 `snippet` 当成已读全文。

## 失败处理

- 缺少 `TAVILY_API_KEY`：脚本返回 `ok=false`、`results=[]` 和 `coverage_notes=["engine unavailable: TAVILY_API_KEY is not set"]`。保留该记录，不要用仓库搜索替代全网覆盖结论。
- HTTP 4xx/5xx 或网络错误：有限重试一次；仍失败则写失败记录，继续已有分析。
- 不要把 API key 或响应中的 token 写入 `search-log.jsonl`、`sources.jsonl` 或 `analysis.json`。
