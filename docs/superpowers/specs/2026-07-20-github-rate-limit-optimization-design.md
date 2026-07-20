# GitHub API Rate Limit Optimization

## 日期
2026-07-20

## 目标
重写 `GitHubClient` 为异步架构，内置缓存、并发控制、主动 rate limit 管理，并优化 follow 命令的 API 调用量。

## 架构

```
GitHubClient (async)
├─ CacheStore      — 文件系统响应缓存 + ETag 条件请求
├─ RateLimiter     — X-RateLimit-Remaining 检查 + 自动等待
└─ Semaphore(5)    — 并发控制，防止 secondary rate limit
```

## 组件

### 1. CacheStore (`collect/github/cache.py`)
- 文件系统缓存目录 `snapshots/cache/`
- Key: `md5(method:url:params)`
- 存储: `<key>.json`（status, headers, body）+ `<key>.meta`（etag, cached_at, ttl）
- TTL: repo=1h, user=24h, starred=30m, search=5m
- ETag 流程: 存 ETag → 下次带 If-None-Match → 304 返回缓存
- force_refresh 参数跳过缓存

### 2. RateLimitTracker (`collect/github/rate_limit.py`)
- 解析 X-RateLimit-Remaining / X-RateLimit-Reset
- remaining < 50 → 计算 sleep 时间 → asyncio.sleep
- 处理 429 (primary) 和 403+retry-after (secondary)
- 日志输出消耗统计

### 3. GitHubClient 重写
- httpx.AsyncClient
- semaphore=5 控制并发
- 所有公开方法保持语义不变（返回类型不变）
- 新增 `_request()` 核心方法：cache check → semaphore → http → rate limit check → cache store

### 4. Follow 优化
- `_fetch_metrics`: 用 `/search/repositories?q=user:{actor}+fork:true` 替代 `get_repos()` 分页
- Search API 直接返回 total_count（stars 总和），1 次调用替代 N 页
- 降级: search 失败时回退到原 get_repos 分页方式

### 5. Pipeline 并发
- `_collect_all`: 用 asyncio.gather 并发拉取多个账号
- 保持信号顺序和错误隔离

## 错误处理

| 场景 | 处理 |
|------|------|
| 401 | 立即抛出 |
| 429 | 解析 Retry-After，等待后重试 |
| 403 + retry-after | 同上（secondary rate limit） |
| 5xx / 网络错误 | 指数退避，最多 3 次 |
| 缓存损坏 | 自动清除，重新请求 |
| Search API 不可用 | 降级为分页 get_repos |

## 测试
- `test_collect/test_cache.py`: 缓存命中/未命中/过期/ETag 304
- `test_collect/test_rate_limit.py`: rate limit 触发/等待/恢复
- `test_collect/test_client.py`: 并发安全、重试、降级
- 用 pytest-httpx mock HTTP

## 文件变更

| 文件 | 操作 |
|------|------|
| `collect/github/cache.py` | 新增 |
| `collect/github/rate_limit.py` | 新增 |
| `collect/github/client.py` | 重写 |
| `collect/github/mapper.py` | 不变 |
| `pipeline.py` | asyncio.gather 并发 |
| `cli.py` | async follow / run |
| `config.py` | 新增 cache/rate_limit 配置项 |
| `config.yaml` | 新增 cache/rate_limit 配置 |
| `tests/test_collect/test_cache.py` | 新增 |
| `tests/test_collect/test_rate_limit.py` | 新增 |
| `pyproject.toml` | 依赖无变化（httpx 已支持 async） |
