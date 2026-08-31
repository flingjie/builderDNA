# opencli Twitter 命令速查

这是「怎么搜」的准确命令面。命令签名会随 opencli 更新漂移——**不确定就现场 `opencli twitter <cmd> -h`**，不要硬背本文档里的参数。`opencli list -f json` 是 registry 的唯一事实源。

## 前置条件（重要）

Twitter/X 的 opencli adapter 几乎都是 `cookie` / `ui` / `intercept` 策略，需要：

- Chrome 已登录 x.com
- 已安装 OpenCLI 扩展（Chrome Web Store：opencli）
- `opencli doctor` 通过（浏览器桥接正常）

运行前先自检登录态：

```bash
opencli twitter whoami -f yaml   # 显示当前登录账号；未登录则报错
opencli twitter login            # 若未登录，打开登录并等待鉴权
```

若 `whoami` 失败，后续所有读/写命令都不会有结果——先解决登录，再继续。

## 通用参数

- `-f json | yaml | table | plain | md | csv` — agent 优先 `json` 或 `yaml`
- `--limit N` — 返回条数（不同命令默认不同，见 `-h`）
- `--top-by-engagement N` — 按加权互动重排取前 N（`likes×1 + retweets×3 + replies×2 + bookmarks×5 + log10(views+1)×0.5`）。适合「只看高互动」，但会引入热度偏差，与「Likes ≠ Quality」原则冲突，慎用。
- `--window foreground|background`、`--site-session ephemeral|persistent` — 浏览器会话控制，一般用默认即可。

## 搜索（Step 1 主力）

```bash
opencli twitter search "<query>" [--from <user>] [--has <type>] [--exclude <type>] [--product <tab>] [--limit N] -f json
```

- `query` 直接透传原始 X 操作符：`"exact phrase"`、`#tag`、`OR`、`-`（排除）、`lang:en`、`since:YYYY-MM-DD`、`until:YYYY-MM-DD`、`from:`、`min_faves:`、`min_retweets:` 等。
- `--from <user>` 限定作者（等价 `from:<user>`，自动去 `@`）
- `--has media|images|videos|links|replies`
- `--exclude replies|retweets|media|links`
- `--product top|live|photos|videos`（对应 X 的搜索 tab；`live` 最新）

输出列：`id, author, bio, text, created_at, likes, views, url, has_media, media_urls, media_posters, card, quoted_tweet`

注意：**search 输出没有 retweets / replies / bookmarks 计数**，只有 `likes` 和 `views`。需要完整互动数据时看 `timeline` 或 `tweets`。

## 补充来源

```bash
opencli twitter timeline --type for-you|following --limit N -f json   # 首页：做信号来源之一，别当主力（关注列表噪声高时价值有限）
opencli twitter tweets <username> --limit N -f json                  # 某作者近期推文（chronological，排除置顶）
opencli twitter thread <tweet-id|url> --limit N -f json              # 读一条推文的完整 thread（原始+回复）
opencli twitter trending --limit N -f json                           # 趋势话题（做信号，别当内容）
opencli twitter profile <username> -f json                           # 作者画像：bio/stats，判断是否「高价值作者」
opencli twitter article <tweet-id> -f json                           # 长文（long-form）导出 Markdown，适合深度阅读
```

`timeline` / `tweets` / `thread` 输出列比 `search` 全：含 `likes, retweets, replies, views`。

## 互动（Step 4 用，必须经用户确认）

```bash
opencli twitter reply <url> <text>     # 回复
opencli twitter quote <url> <text>     # 引用转推
opencli twitter like <url>             # 点赞
opencli twitter bookmark <url>         # 收藏（沉淀到书签，便于回看）
opencli twitter retweet <url>          # 转推
```

原则：**只生成回复草稿，每一条都等用户点头再发。** 不要把 `reply` 当成「自动发推」。

## 搜索策略

主次分明——定向 search 是主力，关注流是信号，作者扫描是放大器：

1. **主力**：`opencli twitter search` 按主题/问题/经验三类词各拉一批候选（见 `topics.md`）。
2. **信号**：`opencli twitter timeline --type following` 扫一眼关注流，只当发现新作者/新话题的引子。若关注列表里非 Agent 内容多、RT 占比高，就别在它身上花太多时间——直接跳到第 1、4 步。
3. **深读**：对候选里「值得深读」的，用 `opencli twitter thread <id>` 拉完整上下文；作者长文用 `opencli twitter article <id>`。
4. **放大器**：用 `opencli twitter tweets <作者>` 对「高价值作者」定向扫近期推文，比关注流更接近一手内容。

## 失败回退

- 命令因站点改版失败 → `--trace retain-on-failure` 重跑，拿到 adapter 源路径后按 `opencli-autofix` 修（最多 3 轮）。
- Twitter adapter 完全不可用 → 退到 `smart-search` 的 `grok` AI 源（面向 Twitter/X 语境）拿信号，明确标注「非原始推文」。
- 不要因为单条搜索失败就中止整个日报——记录缺口，继续其他主题。
