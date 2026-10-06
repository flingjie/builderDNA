# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

BuilderDNA is an independent Technology Intelligence Sandbox Toolkit — composable CLI commands that analyze GitHub developers, repos, and community signals to understand technical change, discover pain points, and validate what's worth learning or building. Each command is an independent sandbox: structured JSON in → deterministic compute → structured JSON out. Claude Code handles all semantic reasoning and orchestration, reading JSON outputs from `output/`. No cloud LLM, no web server, no LangGraph pipeline. The product boundary and non-goals live in `docs/product-contract.md`.

## Commands

```bash
# All commands need PYTHONPATH=. prefix and config.yaml in project root
# Copy .env.example to .env and fill in: GITHUB_TOKEN

# Collect GitHub signals (repos + issues) for a domain
PYTHONPATH=. uv run builderdna collect agent --window 365 --output output/signals.json

# Compute topic trends from collected signals
PYTHONPATH=. uv run builderdna trend agent --data output/signals.json --output output/trends.json

# Group issues into candidate pain groups (offline TF-IDF; --backend embedding for optional Ollama+HDBSCAN)
PYTHONPATH=. uv run builderdna pain agent --data output/signals.json --backend tfidf --output output/pain_candidates.json

# Finalize candidate groups into pain clusters (--confirmations applies the Agent's semantic grouping)
PYTHONPATH=. uv run builderdna pain-finalize agent --candidates output/pain_candidates.json --confirmations output/pain_confirmations.json --output output/pain_clusters.json

# Generate opportunity cards from trends + pain clusters (rule engine, no LLM)
PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json

# Render any SandboxResult to Markdown or JSON
PYTHONPATH=. uv run builderdna report --data output/opportunities.json --format md

# Show resolved configuration (with sensitive values masked)
PYTHONPATH=. uv run builderdna config --show

# Run self-iteration diagnostics (mismatch detection, snapshot comparison, hypothesis pruning)
PYTHONPATH=. uv run builderdna observability --all --domain agent

# Record and compare builder problems/trajectories
PYTHONPATH=. uv run builderdna builders capture alice --statement "..." --job-to-be-done "..." --trigger-context "..."
PYTHONPATH=. uv run builderdna builders compare
PYTHONPATH=. uv run builderdna builders opportunity

# Run all tests
uv run pytest tests/ -v

# Run a single test file/class/function
uv run pytest tests/test_config.py -v
uv run pytest tests/test_signal/test_models.py::TestSignal -v
```

## Architecture

```
config.yaml ──▶ config.py (Config model, env var ${SUBSTITUTION})
     │
     ▼
cli/main.py ── Typer app (collect/trend/pain/pain-finalize/opportunity/report/config/observability + concept/radar/radar-cycle + builders)
     │
     ├─ collect  ──▶ collector/github/ (httpx client, cache, rate limiter)
     │              ▶ collector/normalizer.py (raw API → Signal model)
     │              ▶ output: models/payload.py → RepoSignal, IssueSignal
     │
     ├─ trend    ──▶ intelligence/trend/ (velocity analysis)
     │              ▶ output: models/payload.py → TopicTrend, RepoSummary
     │
     ├─ pain     ──▶ intelligence/pain/ (clean/dedupe → TF-IDF candidate grouping;
     │          │    --backend embedding for optional Ollama+HDBSCAN)
     │          │  ▶ output: models/payload.py → CandidateGroup, PainCandidate
     │
     ├─ pain-finalize ▶ intelligence/pain/summarize.py (validate refs → severity/frequency/reach)
     │              ▶ output: models/payload.py → PainCluster, IssueSummary
     │
     ├─ opportunity ▶ intelligence/opportunity/ (rule engine, gap_score = demand/competition)
     │              ▶ output: models/payload.py → OpportunityCard
     │
     ├─ builders   ──▶ intelligence/builder_problems/ (problem snapshots + trajectory events)
     │              ▶ models/builder_problem.py → BuilderProblem, ProblemEvent,
     │                ProblemComparison, ProblemOpportunityCard
     │
     ├─ report   ──▶ cli/commands/report_cmd.py (rendering only)
     │
     ├─ config   ──▶ cli/commands/config_cmd.py (show resolved config)
     │
     └─ observability ▶ cli/commands/observability_cmd.py (mismatch detection, snapshot comparison, hypothesis pruning)
     │
     ├─ concept     ──▶ cli/commands/concept.py (capture/list/show/move/merge/score/outcome/review)
     ├─ radar       ──▶ cli/commands/radar.py (scan/verify/experiment/review/source-audit)
     └─ radar-cycle ──▶ cli/commands/radar_cycle_cmd.py (start/import/decide/status/complete/finalize)

signals/ ── Unified Signal model + SQLite store
  models.py    — Signal (unified immutable event, all sources normalize to this)
  store.py     — SQLite-backed persistence with velocity queries

observability/ ── Telemetry + behavior tracking (integrated into all other commands)
  telemetry.py   — RunTelemetry, vprint, record_command
  behavior.py    — Mismatch detection between predicted and actual values
  snapshot.py    — Prediction snapshots for future validation
  hypothesis.py  — HypothesisManager for tracking exploration hypotheses
  diagnostics.py — Cross-run diagnostics: parameter sensitivity, bootstrap, comparison
  output.py      — OutputLevel enum, verbosity control, console formatting

adapters/ ── Embed BuilderDNA in agent frameworks
  interface.py   — Abstract BuilderDNAAdapter (analyze_domain, get_trends, get_diagnostics)
  cli.py         — CLIAdapter: subprocess-based, process isolation
  claude_code.py — ClaudeCodeAdapter: direct Python imports for Claude Code skills

All commands wrap output in SandboxResult{command, domain, computed_at, payload, stats, diagnostics}.
Schema contract: schema.md and models/payload.py — Claude Code reads these.
```

## Key Design Decisions

- **LLM-free pipeline (with one exception)**: After refactoring, all cloud LLM calls were removed. Trend and opportunity use deterministic algorithms (velocity, rule engine). Pain uses offline TF-IDF candidate grouping by default (semantic confirmation done by Claude Code in the skill loop); an optional `--backend embedding` path uses local Ollama embeddings (BGE-M3) — the only ML dependency, opt-in and fully offline.
- **No web layer**: FastAPI was removed. This is a CLI toolkit, not a service.
- **Two-loop architecture**: Inner loop = deterministic sandbox commands run locally. Outer loop = Claude Code reads JSON outputs and does semantic reasoning.
- **Config via YAML + env**: `config.yaml` supports `${VAR}` and `${VAR:-default}` substitution. `.env` is auto-loaded at `config.py` import time.
- **Collector cache**: `collector/github/cache.py` provides filesystem-based HTTP response caching. Rate limiter in `collector/github/rate_limit.py` proactively manages GitHub API quotas.
- **SQLite for signals**: `signals/store.py` persists normalized signals to SQLite for velocity queries across time windows.
- **Known limitation**: `contributors` field is always 0. GitHub Search API doesn't return contributor counts; fetching them would require N additional API calls (one per repo). The field exists for future enhancement.

## Skills (`.claude/skills/`)

Skills are deployed under `.claude/skills/` (`*-workspace/` dirs, when present, are skill-creator eval artifacts, not skills):

| Skill | Purpose | Trigger |
|-------|---------|---------|
| `builderdna` | Orchestrate the Python sandbox commands (collect/trend/pain/pain-finalize/opportunity), manage hypotheses | "analyze X's GitHub", "tech DNA", "find opportunities in Z" |
| `concept-radar` | Cross-source concept lifecycle radar: turn weak signals into validated, falsifiable builds (Inbox → Watch → Verify → Build/Drop) | "validate an idea", "weak signals to validated builds", "hypothesis and evidence", "should I build or drop this", "track this concept", "雷达" |
| `concept-radar-loop` | Resumable, deterministic radar-cycle orchestrator (start → import → decide → finalize) | "run the concept radar loop", "继续跑概念雷达", "resume my radar run" |
| `repo-trend` | Discover trending repos via GitHub API search, 3-tier eval | "find trending X repos", "evaluate this repo", "check my watches" |
| `repo-awesome` | Mine awesome-* lists for curated repo discovery | "mine awesome lists for X", "what do awesome lists recommend" |
| `repo-evolution-learning` | Reconstruct a repo/PR/feature's development episode + its public promotion and feedback, rendered as an interactive HTML learning report | "分析这个 PR 的设计取舍", "复盘这个仓库的迭代", "这个项目怎么宣传的", "repo evolution learning", "interactive HTML learning report" |
| `reddit-opportunity` | Discover product opportunities + pain points from a Reddit community (no product yet): RSS → Subreddit Profile → recurring problems → product concept | "find problems people will pay to solve", "what should I build from r/...", "从 Reddit 找商机" |
| `value-discovery` | Extract the user's BuilderInterestProfile (domains, problem preferences, build constraints, learning goals) | "value discovery", "what do I value", "help me understand my preferences" |
| `observability` | Run self-iteration diagnostics (mismatch, snapshot, hypothesis pruning) | "check my predictions", "validate assumptions", "任何东西变了吗" |
| `optimize` | Diagnose→Propose→Apply→Verify loop — read diagnostics, generate improvement proposals, apply and re-run | "/optimize", "improve the analysis", "fix low confidence", "优化分析" |
| `reflect` | Multi-pass adversarial reflection on conversations → self-model updates (v4 protocol) | "/reflect", "reflect on this conversation", "复盘" |
| `distill` | Synthesize accumulated reflections + digest gap reports into growth reports, propose self-model updates (including cognitive_patterns) | "/distill", "synthesize my reflections", "growth report", "蒸馏" |
| `note` | RAL recording layer — capture daily moments, amplify meaning, weekly connection review | "/note", "记一下", "take a note", "weekly review", "日复盘" |
| `digest` | 5-layer Feynman adversarial interview — verify true understanding of a book/principle/repo by exposing blind spots | "/digest", "校验我对...的掌握", "verify my grasp of", "费曼校验" |
| `trace-classify` | Classify raw tool-call traces into step-level trace files + periodic review for optimization insights | "classify the last trace", "trace this session", "review this week's traces" |
| `twitter-learning` | Daily Twitter/X learning on a topic (default: agent): discover, filter, score by Learning Score → Top 10 learnings (7-angle analysis) + knowledge asset | "做今天的 X 情报", "帮我研究 Y 的推特", "今天 X 上有什么值得学的", "有哪些值得学习的高质量推文" |

**Cross-source routing:** `concept-radar` owns cross-source synthesis and the `Inbox → Watch → Verify → Build/Drop` lifecycle. Single-source requests stay with their specialists — X-only learning/knowledge-base → `twitter-learning`, Reddit-only pain discovery → `reddit-opportunity`, GitHub-only discovery → `repo-trend`, awesome-list curation → `repo-awesome`. X reply/engagement and customer outreach are **out of scope** for this project. Selected `twitter-learning` findings may feed into `concept-radar`; never the reverse. Full routing rules: `docs/product-contract.md`.

Evals exist for builderdna (`.claude/skills/builderdna/evals/`) via the skill-creator workflow. Shared evaluation rubrics: `references/repo-scout/`. Most skills are pure Claude-orchestrated — they use `gh` CLI, not the Python codebase. The `builderdna` skill orchestrates the Python CLI sandbox commands.

**Skill path note:** Several skills (`reflect`, `distill`, `note`, `repo-trend`, `repo-awesome`, `builderdna`) reference files under `references/` at the project root (e.g., `references/reflection-protocol.md`, `references/repo-scout/eval.md`). These paths resolve because skills are always invoked from the project root — skills are not standalone/portable.

## Key Files

| File | Purpose |
|------|---------|
| `config.py` | Config loading with env var substitution + pydantic validation |
| `config.yaml` | Accounts, domains (topic tags), vendors, embedding, output config |
| `models/payload.py` | Output schemas for all data-producing commands — the contract Claude Code reads |
| `models/builder_interest_profile.py` | Public user-interest profile (domains, adjacencies, prefs, constraints, goals, risk) + migration |
| `models/user_dna_schema.py` | Internal scoring representation (Values) + domain/activity/reward mapping rule tables |
| `models/builder_problem.py` | Builder problem snapshot, append-only trajectory event, cross-person comparison, verifiable opportunity card |
| `schema.md` | Human-readable schema reference for all SandboxResult payloads (including diagnostics) |
| `signals/models.py` | Unified Signal model — all data sources normalize to this |
| `signals/store.py` | SQLite-backed persistence with velocity and topic trend queries |
| `intelligence/developer_dna.py` | Deterministic DeveloperDNA feature computation (evidence-backed, observed/inferred/unknown) |
| `intelligence/pain/` | Pain pipeline: clean.py (dedup/fingerprint), candidates.py (TF-IDF grouping), cluster.py (optional HDBSCAN), summarize.py (final cluster stats) |
| `intelligence/builder_problems/` | Builder problem store + deterministic comparison/opportunity service |
| `observability/metrics.py` | Self-calibration metrics (prediction resolution, hypothesis drop, source failure, …) |
| `observability/` | Telemetry, behavior tracking, prediction snapshots, hypothesis management, diagnostics |
| `adapters/` | Embed BuilderDNA in agent frameworks: interface.py, cli.py, claude_code.py |
| `state/bootstrap.json` | Bootstrap state — records successful run parameters for optimize skill hints |
| `state/builder_interest_profile.json` | User interest profile (domains, adjacencies, problem prefs, build constraints, learning goals, risk tolerance) — ranking only |
| `state/user_weights.json` | User preference weights for opportunity scoring bias |
| `state/reflections.jsonl` | Reflection event log for /reflect and /distill skills |
| `state/digest_gaps.jsonl` | Feynman verification gap reports — blind-spot tracking (digest skill, created on first use) |
| `state/distill_reports/` | Growth reports from /distill (YYYY-MM-DD_distill.md) |
| `state/records.jsonl` | RAL daily records — event captures, amplifications, daily/weekly reviews (note skill) |
| `state/behavior_log.jsonl` | Telemetry behavior log — mismatch detection data (observability command) |
| `state/hypotheses.json` | Exploration state tracking across conversations (builderdna skill) |
| `state/watches.json` | Saved repo searches for recurring monitoring (repo-trend skill) |
| `output/proposals/` | Optimization proposals from /optimize skill (prop_YYYYMMDD_HHMMSS.json) |
| `output/tracked_repos.json` | Persistent repo tracking with diff history (repo-trend skill) |
| `references/cases/` | Case studies and examples for builder's perspective analysis |
| `.env` | Environment variables: GITHUB_TOKEN, EMBEDDING_BASE_URL (copy from .env.example) |
