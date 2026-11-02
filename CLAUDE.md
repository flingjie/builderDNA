# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

BuilderDNA is a concept-radar lifecycle toolkit plus signal-source skill orchestration. Deterministic CLI commands manage concept cards, radar gates, and bounded Reddit investigations (structured JSON in → deterministic compute → structured JSON out). Claude Code owns semantic reasoning and orchestration across the retained source skills, reading CLI JSON and skill state under `output/` / `state/`. No cloud LLM, no web server, no LangGraph pipeline. The product boundary and non-goals live in `docs/product-contract.md`.

## Commands

```bash
# All commands need PYTHONPATH=. prefix and config.yaml in project root
# Copy .env.example to .env and fill in: TAVILY_API_KEY (optional; repo-evolution-learning)

# Show resolved configuration (with sensitive values masked)
PYTHONPATH=. uv run builderdna config --show

# Concept lifecycle + radar (deterministic gates; Claude owns semantic orchestration)
PYTHONPATH=. uv run builderdna concept capture --title "..." --problem "..."
PYTHONPATH=. uv run builderdna radar scan agent-reliability
PYTHONPATH=. uv run builderdna radar verify <CONCEPT_ID>

# Reddit investigation control plane
PYTHONPATH=. uv run builderdna investigate init --topic "production agent failures"
PYTHONPATH=. uv run builderdna investigate --help

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
cli/main.py ── Typer app (concept / radar / investigate / config)
     │
     ├─ concept ──▶ concepts/ (store, service, scoring, matching, handoffs,
     │              rendering, radar_config + adapters/{manual_x,reddit})
     │              ▶ models/concept.py → ConceptCard, ConceptEvidence, …
     │
     ├─ radar   ──▶ concepts/ + experiments/ (scan/verify/review/source-audit;
     │              experiment → FDE-Gym export)
     │              ▶ models/radar_payload.py → RadarRunPayload
     │
     ├─ investigate ▶ investigations/ (bounded Reddit pain-discovery control plane)
     │              ▶ concepts/adapters/reddit.py (Signal → concept evidence)
     │
     └─ config  ──▶ cli/commands/config_cmd.py (show resolved config)

Shared foundations:
  signals/models.py     — Signal type (adapters normalize sources to this)
  state/jsonl.py        — JSONL storage primitives (concept + investigation stores)
  observability/        — telemetry.py (RunTelemetry, vprint) + output.py (OutputLevel)
```

## Key Design Decisions

- **No web layer**: This is a CLI toolkit, not a service.
- **Two-loop architecture**: Inner loop = deterministic sandbox commands run locally. Outer loop = Claude Code reads JSON outputs and does semantic reasoning (including source-skill orchestration).
- **Config via YAML + env**: `config.yaml` supports `${VAR}` and `${VAR:-default}` substitution. `.env` is auto-loaded at `config.py` import time.

## Skills (`.claude/skills/`)

Skills are deployed under `.claude/skills/` (`*-workspace/` dirs, when present, are skill-creator eval artifacts, not skills):

| Skill | Purpose | Trigger |
|-------|---------|---------|
| `concept-radar` | Cross-source concept lifecycle radar + full-cycle orchestration via `concept`/`radar` CLI (Inbox → Watch → Verify → Build/Drop) | "validate an idea", "weak signals to validated builds", "run the concept radar loop", "继续跑概念雷达", "雷达" |
| `repo-trend` | Discover trending repos via GitHub API search, 3-tier eval | "find trending X repos", "evaluate this repo", "check my watches" |
| `repo-awesome` | Mine awesome-* lists for curated repo discovery | "mine awesome lists for X", "what do awesome lists recommend" |
| `repo-evolution-learning` | Reconstruct a repo/PR episode + promotion/feedback via `gh` + Tavily + HTML template (pure skill orchestration) | "分析这个 PR 的设计取舍", "复盘这个仓库的迭代", "这个项目怎么宣传的", "repo evolution learning" |
| `reddit-opportunity` | Discover product opportunities + pain points from a Reddit community (thin loop over `investigate`) | "find problems people will pay to solve", "what should I build from r/...", "从 Reddit 找商机" |
| `twitter-learning` | Daily Twitter/X learning on a topic (default: agent): discover, filter, score by Learning Score → Top 10 learnings (7-angle analysis) + knowledge asset | "做今天的 X 情报", "帮我研究 Y 的推特", "今天 X 上有什么值得学的", "有哪些值得学习的高质量推文" |

Personal cognitive skills (`note` / `reflect` / `distill` / `digest`) live under `~/.claude/skills/` with state in `~/.claude/personal-state/` — they are not part of this product.

**Cross-source routing:** `concept-radar` owns cross-source synthesis and the `Inbox → Watch → Verify → Build/Drop` lifecycle. Single-source requests stay with their specialists — X learning/knowledge-base → `twitter-learning` (X may also surface public problem clues), Reddit pain/opportunity discovery → `reddit-opportunity`, GitHub-only discovery → `repo-trend`, awesome-list curation → `repo-awesome`. X reply/engagement and customer outreach are **out of scope** for this project. Selected `twitter-learning` findings may feed into `concept-radar`; never the reverse. Full routing rules: `docs/product-contract.md`.

Shared evaluation rubrics: `references/repo-scout/`. Most skills are pure Claude-orchestrated — they use `gh` CLI and external tools, not the Python codebase. `concept-radar` and `reddit-opportunity` drive the retained `concept` / `radar` / `investigate` CLI.

**Skill path note:** Several skills (`repo-trend`, `repo-awesome`) reference files under `references/` at the project root (e.g., `references/repo-scout/eval.md`). These paths resolve because skills are always invoked from the project root.

## Key Files

| File | Purpose |
|------|---------|
| `config.py` | Config loading with env var substitution + pydantic validation |
| `config.yaml` | Output config (dir + formats) |
| `schema.md` | Human-readable schema reference for concept/radar/investigate envelopes |
| `models/concept.py` | ConceptCard, ConceptEvidence, RadarReview, and lifecycle contracts |
| `models/radar_payload.py` | RadarRunPayload (per-source coverage + cards affected) |
| `signals/models.py` | Unified Signal type — adapters normalize sources to this |
| `state/jsonl.py` | Shared JSONL storage primitives |
| `observability/` | telemetry.py + output.py (RunTelemetry, OutputLevel, vprint) |
| `concepts/` | Concept store/service/scoring/matching/handoffs + adapters + `radar_config.py` |
| `investigations/` | Bounded Reddit investigation control plane |
| `experiments/` | ExperimentProposal + FDE-Gym export used by `radar experiment` |
| `state/watches.json` | Saved repo searches for recurring monitoring (repo-trend skill) |
| `output/tracked_repos.json` | Persistent repo tracking with diff history (repo-trend skill) |
| `.env` | Environment variables: `TAVILY_API_KEY` (copy from `.env.example`) |
