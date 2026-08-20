# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

BuilderDNA is a Technology Intelligence Sandbox Toolkit — 7 composable CLI commands that analyze GitHub developer activity. Each command is an independent sandbox: structured JSON in → deterministic compute → structured JSON out. Claude Code handles all semantic reasoning and orchestration, reading JSON outputs from `output/`. No LLM, no web server, no LangGraph pipeline.

## Commands

```bash
# All commands need PYTHONPATH=. prefix and config.yaml in project root
# Copy .env.example to .env and fill in: GITHUB_TOKEN

# Collect GitHub signals (repos + issues) for a domain
PYTHONPATH=. uv run builderdna collect agent --window 365 --output output/signals.json

# Compute topic trends from collected signals
PYTHONPATH=. uv run builderdna trend agent --data output/signals.json --output output/trends.json

# Mine pain points from issue text (requires local Ollama for embeddings)
PYTHONPATH=. uv run builderdna pain agent --data output/signals.json --output output/pain_clusters.json

# Generate opportunity cards from trends + pain clusters (rule engine, no LLM)
PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json

# Render any SandboxResult to Markdown or JSON
PYTHONPATH=. uv run builderdna report --data output/opportunities.json --format md

# Show resolved configuration (with sensitive values masked)
PYTHONPATH=. uv run builderdna config --show

# Run self-iteration diagnostics (mismatch detection, snapshot comparison, hypothesis pruning)
PYTHONPATH=. uv run builderdna observability --all --domain agent

# Run all tests (197 tests)
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
cli/main.py ── Typer app, 7 commands
     │
     ├─ collect  ──▶ collector/github/ (httpx client, cache, rate limiter)
     │              ▶ collector/normalizer.py (raw API → Signal model)
     │              ▶ output: models/payload.py → RepoSignal, IssueSignal
     │
     ├─ trend    ──▶ intelligence/trend/ (velocity analysis)
     │              ▶ output: models/payload.py → TopicTrend, RepoSummary
     │
     ├─ pain     ──▶ intelligence/pain/ (HDBSCAN + BGE-M3 embeddings via Ollama)
     │              ▶ output: models/payload.py → PainCluster, IssueSummary
     │
     ├─ opportunity ▶ intelligence/opportunity/ (rule engine, gap_score = demand/competition)
     │              ▶ output: models/payload.py → OpportunityCard
     │
     ├─ report   ──▶ cli/commands/report_cmd.py (rendering only)
     │
     ├─ config   ──▶ cli/commands/config_cmd.py (show resolved config)
     │
     └─ observability ▶ cli/commands/observability_cmd.py (mismatch detection, snapshot comparison, hypothesis pruning)

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

- **LLM-free pipeline (with one exception)**: After refactoring, all cloud LLM calls were removed. Trend and opportunity use deterministic algorithms (velocity, rule engine). Pain uses local Ollama embeddings (BGE-M3) — the only ML dependency, running entirely offline.
- **No web layer**: FastAPI was removed. This is a CLI toolkit, not a service.
- **Two-loop architecture**: Inner loop = deterministic sandbox commands run locally. Outer loop = Claude Code reads JSON outputs and does semantic reasoning.
- **Config via YAML + env**: `config.yaml` supports `${VAR}` and `${VAR:-default}` substitution. `.env` is auto-loaded at `config.py` import time.
- **Collector cache**: `collector/github/cache.py` provides filesystem-based HTTP response caching. Rate limiter in `collector/github/rate_limit.py` proactively manages GitHub API quotas.
- **SQLite for signals**: `signals/store.py` persists normalized signals to SQLite for velocity queries across time windows.
- **Known limitation**: `contributors` field is always 0. GitHub Search API doesn't return contributor counts; fetching them would require N additional API calls (one per repo). The field exists for future enhancement.

## Skills (`.claude/skills/`)

Thirteen skills are deployed (16 directories — 3 `*-workspace/` dirs are skill-creator eval artifacts, not skills):

| Skill | Purpose | Trigger |
|-------|---------|---------|
| `builderdna` | Run the 7-command analysis pipeline, manage hypotheses | "analyze X's GitHub", "tech DNA", "find opportunities in Z" |
| `repo-trend` | Discover trending repos via GitHub API search, 3-tier eval | "find trending X repos", "evaluate this repo", "check my watches" |
| `repo-awesome` | Mine awesome-* lists for curated repo discovery | "mine awesome lists for X", "what do awesome lists recommend" |
| `reddit-opportunity` | Discover product opportunities + pain points from a Reddit community (no product yet): RSS → Subreddit Profile → recurring problems → product concept | "find problems people will pay to solve", "what should I build from r/...", "从 Reddit 找商机" |
| `reddit-outreach` | Find customers + draft replies for an existing product on Reddit (human posts, no spam) | "find customers on reddit", "draft a reply", "红迪获客" |
| `value-discovery` | Extract user's cognitive decision model via Meta Model interview | "value discovery", "what do I value", "help me understand my preferences" |
| `observability` | Run self-iteration diagnostics (mismatch, snapshot, hypothesis pruning) | "check my predictions", "validate assumptions", "任何东西变了吗" |
| `optimize` | Diagnose→Propose→Apply→Verify loop — read diagnostics, generate improvement proposals, apply and re-run | "/optimize", "improve the analysis", "fix low confidence", "优化分析" |
| `reflect` | Multi-pass adversarial reflection on conversations → self-model updates (v4 protocol) | "/reflect", "reflect on this conversation", "复盘" |
| `distill` | Synthesize accumulated reflections + digest gap reports into growth reports, propose self-model updates (including cognitive_patterns) | "/distill", "synthesize my reflections", "growth report", "蒸馏" |
| `note` | RAL recording layer — capture daily moments, amplify meaning, weekly connection review | "/note", "记一下", "take a note", "weekly review", "日复盘" |
| `digest` | 5-layer Feynman adversarial interview — verify true understanding of a book/principle/repo by exposing blind spots | "/digest", "校验我对...的掌握", "verify my grasp of", "费曼校验" |
| `trace-classify` | Classify raw tool-call traces into step-level trace files + periodic review for optimization insights | "classify the last trace", "trace this session", "review this week's traces" |

Evals exist for builderdna (`.claude/skills/builderdna/evals/`) via the skill-creator workflow. Shared evaluation rubrics: `references/repo-scout/`. Most skills are pure Claude-orchestrated — they use `gh` CLI, not the Python codebase. The `builderdna` skill orchestrates the 7 Python CLI sandbox commands.

**Skill path note:** Several skills (`reflect`, `distill`, `note`, `repo-trend`, `repo-awesome`, `builderdna`) reference files under `references/` at the project root (e.g., `references/reflection-protocol.md`, `references/repo-scout/eval.md`). These paths resolve because skills are always invoked from the project root — skills are not standalone/portable.

## Key Files

| File | Purpose |
|------|---------|
| `config.py` | Config loading with env var substitution + pydantic validation |
| `config.yaml` | Accounts, domains (topic tags), vendors, embedding, output config |
| `models/payload.py` | Output schemas for all data-producing commands — the contract Claude Code reads |
| `models/user_dna_schema.py` | Schema definition + domain/activity/reward mapping rule tables |
| `schema.md` | Human-readable schema reference for all SandboxResult payloads (including diagnostics) |
| `signals/models.py` | Unified Signal model — all data sources normalize to this |
| `signals/store.py` | SQLite-backed persistence with velocity and topic trend queries |
| `observability/` | Telemetry, behavior tracking, prediction snapshots, hypothesis management, diagnostics |
| `adapters/` | Embed BuilderDNA in agent frameworks: interface.py, cli.py, claude_code.py |
| `state/bootstrap.json` | Bootstrap state — records successful run parameters for optimize skill hints |
| `state/user_dna.json` | User cognitive model (values, beliefs, criteria, preferences, cognitive_patterns) |
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

## README Warning

`README.md` is outdated — it describes the old architecture (pipeline, LLM insight/opportunity layers, `bldr-dna run`, etc.) that was deleted in the dual-loop refactoring. The current truth is in `schema.md`, `models/payload.py`, and `cli/main.py`. Update README.md before using it as a reference.
