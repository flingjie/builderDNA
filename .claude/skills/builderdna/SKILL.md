---
name: builderdna
description: >
  ALWAYS use this skill when the user wants to analyze a GitHub developer or org,
  discover product/tool opportunities from developer activity, track tech trends
  in a domain (agent, LLM, MCP, etc.), or run BuilderDNA's analysis toolkit.
  Use when the user says "analyze X's GitHub", "what are people building in Y",
  "find opportunities in Z", "tech DNA", "builder insights", "trend radar",
  "what should I build", "developer landscape", "tech stack analysis",
  "competitive intelligence for X", or references BuilderDNA/builderdna directly.
  The skill wraps the core sandbox CLI commands (collect → trend → pain → opportunity → report)
  so the user never needs to remember flags — you translate intent into the right command chain.
  It does NOT replace the specialist skills (repo-trend, repo-awesome, twitter-learning,
  reddit-opportunity) or concept-radar (cross-source lifecycle).
  Reads state/hypotheses.json to track exploration across conversations.
  Uses goal-driven short-circuit pipeline to select the optimal execution path.
  After every run, present findings clearly and ask if they want to refine.
  Important: if the user is asking about GitHub developer analysis or tech trends,
  use this skill — don't try to analyze repos or trends without it.
---

# BuilderDNA Skill

You operate BuilderDNA — a composable toolkit that analyzes GitHub developer activity.
Each command is an independent sandbox: structured JSON input → deterministic compute → structured JSON output.
Claude Code handles all semantic reasoning and orchestration.

## Architecture

```
Claude Code (you) — reads hypotheses.json, maps intent → commands via short-circuit pipeline
      │
      ▼
core sandbox CLI commands (each independent, JSON-in, JSON-out)
  collect → trend → pain → opportunity → report
      │
      ▼
Global memory — SQLite + output/*.json + state/*.json + claude-mem
```

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 编排 Python sandbox（collect → trend → pain → opportunity → report）| 替代专家 Skill 做单源深挖（repo-trend / repo-awesome / twitter-learning / reddit-opportunity）|
| 分析 GitHub 开发者/组织技术 DNA，管理假设树 | 跨源验证概念、管理生命周期（那是 concept-radar 的事）|
| 展示趋势/机会/痛点结果，更新假设状态 | 生成社交回复、获客、维护关系（超出本项目范围）|

## 路由 (Routing)

| 请求 | 路由 |
|------|------|
| 分析 GitHub 开发者技术 DNA / 趋势 / 机会 | **`builderdna`**（本 skill）|
| 只发现/评估 GitHub repo | `repo-trend` |
| 从 Awesome List 策展发现 | `repo-awesome` |
| 只从 X 学习技术信号 | `twitter-learning` |
| 只从 Reddit 发现痛点 | `reddit-opportunity` |
| 跨源验证概念 / 生命周期 | `concept-radar` |
| 运行完整可恢复生命周期 | `concept-radar-loop` |
| 检查历史预测与参数 | `observability` |

`builderdna` **只编排 Python sandbox，不替代专家 Skill 的深度分析**。单源请求交给专家
Skill；跨源验证交给 `concept-radar`。

The pipeline is driven by a single state file and one principle:

- **`state/hypotheses.json`** — cross-session exploration tree. Tracked hypotheses influence domain and topic choices across sessions.
- **Principle**: the command dependency graph is almost linear (branch factor 1-2). A full search algorithm (A*) adds complexity without improving decisions over a simple goal → commands mapping with short-circuit rules. See ADR-006 for the rationale.

All commands run from the project root with `PYTHONPATH=.` prefix.

## Goal-Driven Short-Circuit Pipeline (ADR-006)

### Step 1: Determine Goal

Infer the goal from the user's request:

| User says | Goal |
|-----------|------|
| "what's trending in X" / "show me trends" / "trend radar" | `trend_radar` |
| "find opportunities in X" / "what can I build" / "analyze X" | `opportunity_discovery` |
| "check my hypothesis" / "validate X" / "is Y true" | `hypothesis_validation` |
| Anything with a specific hypothesis ID or node name | `hypothesis_validation` |
| Default (unclear intent) | `opportunity_discovery` |

If `hypothesis_validation`: identify which hypothesis node(s) are the target. If none specified, use the highest-confidence `exploring` node.

### Step 2: Goal → Commands

Each goal maps to a fixed ordered command sequence, respecting the dependency graph. Always execute `trend` before `pain` (8s vs 92s — cheap data informs the expensive decision).

| Goal | Required | Optional (after short-circuit check) |
|------|----------|--------------------------------------|
| `trend_radar` | collect → trend → report | — |
| `opportunity_discovery` | collect → trend → report | pain → opportunity (both, or neither) |
| `hypothesis_validation` | collect → observability | trend (if you want supporting evidence) |

**Command templates** (always prefix with `PYTHONPATH=.`):

| Command | Template |
|---------|----------|
| collect | `PYTHONPATH=. uv run builderdna collect {domain} --window {window} --output output/signals.json` |
| trend | `PYTHONPATH=. uv run builderdna trend {domain} --data output/signals.json --output output/trends.json` |
| pain | `PYTHONPATH=. uv run builderdna pain {domain} --data output/signals.json --output output/pain_clusters.json` |
| opportunity | `PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json --output output/opportunities.json` |
| report | `PYTHONPATH=. uv run builderdna report --data {data_file} --format md` |
| config | `PYTHONPATH=. uv run builderdna config --show` |
| observability | `PYTHONPATH=. uv run builderdna observability --all --domain {domain}` |

Substitute `{domain}` with the target domain, `{window}` with 365 (default) or user-specified value.

### Step 3: Short-Circuit Check (the only decision point)

After required commands complete, check whether to run optional ones:

**Trend signal check** (for `opportunity_discovery`):
- Read `output/trends.json`
- If ALL topics have `gap_score < 1.0` AND no topics have rising velocity:
  → Ask: "Trend data shows low opportunity signals in this domain. Skip pain + opportunity analysis and just report trends?"
- If user agrees → skip pain + opportunity, go to report
- If ANY topic has `gap_score >= 1.0` or rising velocity → proceed with optional commands

**Cost budget check** (all goals):
- Track wall-clock time across all commands
- If cumulative time exceeds 5 minutes → ask whether to continue or stop

**Hypothesis check** (for `hypothesis_validation`):
- If target hypothesis reached `validated` or `pruned` → stop immediately

### Step 4: After Commands Complete

1. Run `report` to generate the final output (if not already done)
2. Read command outputs, update hypothesis confidence in `state/hypotheses.json`
3. Present findings clearly, referencing hypothesis state
4. Ask: "Want to refine with observability diagnostics?" → if yes, run `observability`
5. Ask what to explore next

## Hypothesis Tree Workflow

The file `state/hypotheses.json` tracks exploration state across conversations. Each node has `status: exploring | validated | pruned`.

**On every analysis session:**
1. **Read** `state/hypotheses.json` — see what's being explored
2. **Parse** user intent → goal (Step 1 above)
3. **Execute** goal's command sequence (Step 2-3 above)
4. **Update** node confidence and status based on results
5. **Present** findings with hypothesis state context
6. **Ask** what to explore next — add new nodes or prune dead ends

Example:
```
Read: hyp_001 "Agent Memory needs unified State Engine" is EXPLORING, confidence=0.6
  → Goal: opportunity_discovery, domain: agent
  → Required: collect → trend
  → collect done (45s), signals.json ready
  → trend reveals: "Agent State Engine" gap_score=2.3, velocity=rising
  → Short-circuit check: gap >= 1.0 → proceed with optional
  → Update hyp_001 confidence 0.6 → 0.7
  → pain → opportunity → report
  → Present: "Agent State Engine validated (gap=2.3). New lead: MCP Observability."
  → Ask: "Deep dive on either?"
```

## User Weights

Read `state/user_weights.json` at session start. Apply `scoring_bias` when interpreting opportunities.
Record feedback in `feedback_log` after each session.

## BuilderInterestProfile (Value Discovery Integration)

BuilderDNA integrates with the `value-discovery` Skill for personalized **ranking only**.
The profile reorders/reweights recommendations — it never changes evidence strength,
trend stage, pain severity, or Build gates.

**On every session start:**
1. Check if `state/builder_interest_profile.json` exists and has non-empty fields (check `domains` has entries).
2. **If missing or empty:** This is a first-time user. BEFORE running `collect`, trigger the `value-discovery` Skill:
   - Say: "在开始分析之前，我想先了解你的偏好——这样分析结果会更贴合你。我们花5-8分钟快速聊一下？"
   - If user agrees → invoke `value-discovery` skill, then continue with collect.
   - If user declines → proceed without personalization (no `--profile` flag).
3. **If exists:** Ask: "我之前已经了解过你的偏好，要不要更新一下？" 
   - If yes → invoke `value-discovery` skill for an incremental update.
   - If no → use the existing profile.

**When the profile is available, pass it to commands:**
```bash
# Collect with personalization
PYTHONPATH=. uv run builderdna collect <domain> --window N --profile state/builder_interest_profile.json --output output/signals.json

# Opportunity with personalized scoring
PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json --profile state/builder_interest_profile.json
```

**When presenting results:**
- If personalized: mention "已根据你的兴趣画像做了个性化排序" and highlight the `alignment_reason` on top opportunities.
- Show both `gap_score` (客观市场机会) and `personalized_score` (对你的匹配度) side by side.
- If a high-gap opportunity has low personalization, flag it: "这个市场机会很大，但和你的偏好不太匹配——要不要了解一下？"

The `--profile` flag is optional on both `collect` and `opportunity` — omitting it gives objective/unpersonalized results (backward compatible).

## Observability — Self-Iteration Check

After running a full analysis pipeline, optionally run diagnostics. **For interactive observability sessions, invoke the `observability` skill** — it handles result interpretation and user interaction.

```bash
# Run all observability checks for the domain
PYTHONPATH=. uv run builderdna observability --all --domain <domain>
```

This runs three checks:
1. **Mismatch detection** — compares current behavior patterns against the interest profile, flags potential value drift
2. **Snapshot comparison** — validates past prediction snapshots against today's data
3. **Hypothesis pruning** — checks for stale hypotheses that should be reviewed or retired

**When to trigger:** After every 3-5 complete analysis runs, or when the user mentions "check my predictions", "validate assumptions", "任何东西变了吗", "我之前猜的对不对". Results are written to `output/observability_check_<domain>.json`.

## Schema Reference

`schema.md` documents exact JSON schemas for the sandbox command outputs. Read it when you need field names or types.

## Builder's Lens — 深度项目分析

When the user wants "builder 视角", "从开发者角度分析", "值得借鉴的做法", "commit 历史分析", or wants to learn from a successful project's approach, read `references/builder-lens.md` and apply its 10-dimension framework.

This is a **qualitative, Claude-driven analysis** — no sandbox command covers it. Use `gh api` to fetch commit history, releases, PRs, and contributor stats, then interpret the patterns across 10 dimensions: value quantification, versioning strategy, platform coverage, README architecture, benchmark credibility, commit discipline, core IP positioning, contributor gradient, development cadence, and brand personality.

**When to use**: after trending discovery or deep-dive, when the user sees a standout project and wants to understand *how* it was built, not just *what* it does.

## DeveloperDNA — 技术实践分析

When the user wants "developer DNA", "分析这个开发者的技术 DNA", or "what's their engineering style", run the deterministic DNA computation (then do semantic induction yourself):

```bash
PYTHONPATH=. uv run builderdna dna --data output/signals.json --developer <login> --output output/developer_dna.json
```

This produces 8 evidence-backed dimensions. **Rules you must follow:**

- Every conclusion cites a repo/issue fact; the JSON carries `evidence[].ref` for each dimension.
- Dimensions the signals can't support (build_patterns, iteration_style, testing_reliability_signals) are `unknown` — **state that plainly; do not fill the gap with a story**.

## Builder Problems — 问题与实践轨迹

When the user wants to track *what specific builders are stuck on* and how that
changes over time, use the `builders` command group instead of treating a
one-time profile as the only state:

```bash
PYTHONPATH=. uv run builderdna builders capture alice \
  --statement "修改 prompt 后难以确认旧问题是否修复" \
  --user-segment "独立 Agent 开发者" \
  --trigger-context "修改 prompt 或工具实现后" \
  --job-to-be-done "确认历史失败案例是否修复" \
  --current-workaround "手工重跑历史失败输入" \
  --source-ref "https://..."

PYTHONPATH=. uv run builderdna builders record <problem_id> \
  --event-type attempt --summary "尝试脚本" --to-status confirmed

PYTHONPATH=. uv run builderdna builders compare
PYTHONPATH=. uv run builderdna builders opportunity
```

Rules:

- One problem per person/project link, updated by appending trajectory events.
- Never infer `resolved` just because a source stopped mentioning the problem.
- Cross-person grouping is by normalized `job_to_be_done` + `trigger_context`,
  not by shared keywords such as `eval`.
- Present the comparison's `same_parts`, `different_parts`, `key_unknowns`,
  `validation_targets`, and `minimal_deliverable` rather than asserting a build.
- Never infer ability from stars/followers/a single README.
- Distinguish `observed` (read from a fact) from `inferred` (derived from facts) when you present findings.
- No relationship judgments ("worth connecting with", etc.) — only technical practices.

Present an evidence chain (dimension → evidence refs → confidence) and flag the unknowns explicitly. Semantic induction ("this developer ships small, composable tools and iterates fast") is YOUR job — but it must be grounded in the `observed`/`inferred` dimensions, never the `unknown` ones.

## Reference Files

Read these when needed:

| File | When to Read | Content |
|------|-------------|---------|
| `references/builder-lens.md` | Before builder's perspective analysis | 10-dimension methodology for analyzing project success patterns |
| `schema.md` | Before reading command outputs | JSON schemas for the sandbox commands |
| `state/hypotheses.json` | Session start | Exploration state tree |
| `docs/adr/` | Architecture understanding | All architecture decision records |
| `docs/adr/ADR-006-simplify-goap-to-short-circuit.md` | Understanding the pipeline | Goal-driven short-circuit design rationale |

## Config Management

- **accounts**: in `config.yaml` — developers/orgs to analyze
- **domains**: topic tags for each domain (expand to broaden search)
- **vendors**: domestic/overseas orgs tracked for competitive intelligence
- **embedding**: local Ollama config (pain command only)

Edit `config.yaml` to change accounts or topics. Confirm with user before editing.
`.env` needs: `GITHUB_TOKEN` and optionally `EMBEDDING_BASE_URL`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError` | Prefix with `PYTHONPATH=.` |
| Empty signals | Check `GITHUB_TOKEN` in `.env` |
| No pain clusters | Verify embedding endpoint (`EMBEDDING_BASE_URL`) |
| Rate limited | Wait or reduce window size |
| Import from deleted module | Old code path — verify you're in the refactored worktree |
| Pain keeps getting skipped | Trend gap_scores are low — try broadening domain topics in config.yaml first |
