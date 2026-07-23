# Repo Scout Evaluation Checklist

Shared three-tier evaluation framework for GitHub repository assessment.
Used by `repo-trend`, and available for any future skill that needs to
score or compare repos (repo-awesome, repo-story, dev-dna, repo-audit, etc.).

## Tier 1: Quick Scan (API-only)

Run on: all discovery results. Cost: zero extra API calls (data comes from search query).

### Quality Gates

| Dimension | Source | Pass Threshold |
|-----------|--------|----------------|
| Stars | `stargazersCount` | >= 100 (user-overridable) |
| Recency | `pushedAt` | Within 90 days |
| Active | `isArchived` | Must be `false` |
| Original | `isFork` | Must be `false` (unless user wants forks) |
| Described | `description` | Non-null, non-empty |
| Licensed | `license` | License object present (not null) |

### Metrics Extracted

| Metric | Source Field | Purpose |
|--------|-------------|---------|
| Stars | `stargazersCount` | Raw popularity signal |
| Forks | `forksCount` | Community engagement |
| Open Issues | `openIssuesCount` | Maintenance burden signal |
| Created | `createdAt` | Age — used for velocity calculation |
| Pushed | `pushedAt` | Activity recency |
| Language | `language` | Tech stack fit |
| Description | `description` | Relevance check |
| License | `license.key` | Legal compatibility |
| Watchers | `watchersCount` | Interest signal |
| Homepage | `homepage` | External docs/presence |

### Composite Hotness Score

Calculated in the skill's discovery flow:

```
days_since_creation = max(1, (today - createdAt).days)
days_since_push    = max(0, (today - pushedAt).days)

velocity = stargazersCount / days_since_creation
recency  = 1.0 / (1.0 + days_since_push / 90)
hotness  = log2(stargazersCount + 1) * velocity * recency * log2(forksCount + 1)
```

### Lifecycle Stage

```
if   velocity > 80  → accelerating
elif velocity > 50  → emerging
elif velocity > 20  → mainstream
else                → declining
```

---

## Tier 2: Full Checklist

Run on: user-selected repos (typically 3-5). Cost: 3 API calls per repo.

### API Calls (per repo)

1. **Metadata + topics**:
   ```
   gh api repos/{owner}/{repo} --jq '{topics, stargazers_count, forks_count, subscribers_count, open_issues_count, created_at, updated_at, pushed_at, language, license: .license.spdx_id, description, size, archived, fork, homepage, default_branch, has_issues, has_wiki, has_pages, has_discussions}'
   ```

2. **README content**:
   ```
   gh api repos/{owner}/{repo}/readme -H 'Accept: application/vnd.github.raw'
   ```
   Read first 500 lines if large.

3. **Top contributors**:
   ```
   gh api repos/{owner}/{repo}/contributors --jq '.[:5] | .[] | {login, contributions}'
   ```

### Scoring Dimensions

| Dimension | Source | Scoring Rubric | Weight |
|-----------|--------|---------------|--------|
| **Topic Alignment** | `.topics` array | 1.0 if >= 2 domain-relevant topics, 0.5 if 1, 0 if none | 15% |
| **README Substance** | raw README length | 1.0 if > 2000 chars, 0.7 if > 1000, 0.5 if > 500, 0.1 otherwise | 20% |
| **README Structure** | README content | +0.3 bonus for `## Installation`, +0.2 for code examples, +0.2 for API docs | 15% |
| **Contributor Diversity** | contributors count | 1.0 if >= 5, 0.7 if >= 3, 0.3 if 1-2, 0 if 0 | 15% |
| **Issue Health** | open_issues / (subscribers + 1) | 1.0 if ratio < 0.3, 0.7 if < 0.5, 0.4 if < 2.0, 0.1 otherwise | 15% |
| **Release Cadence** | days since `pushed_at` | 1.0 if < 7 days, 0.7 if < 30, 0.4 if < 90, 0.1 if > 90 | 10% |
| **Stars Growth** | compare to `tracked_repos.json` | 1.0 if > 20% monthly, 0.5 if > 5%, 0 if stalled or no history | 10% |

### Tier 2 Aggregate Score

Weighted average of all dimensions, normalized to 0-10:

```
tier2_score = sum(score_i * weight_i) * 10
```

Present with breakdown by dimension.

---

## Tier 3: Deep Analysis (Claude Semantic Reasoning)

Run on: 1-2 repos for strategic evaluation. Claude reads the README (first 300 lines if large) and applies reasoning. No numeric scoring — qualitative narrative.

### Assessment Dimensions

| Dimension | Guiding Questions |
|-----------|------------------|
| **Clarity of Purpose** | Is the README immediately clear about what this project does? Can a newcomer understand it in 30 seconds? |
| **Documentation Quality** | Are there code examples? Quickstart guide? API reference? Architecture diagrams? |
| **Innovation Signal** | Is this a novel approach or one of many similar tools? Are there unique architectural decisions? |
| **Community Health** | Diverse contributors? Responsive issue triage? Active discussions? Welcoming tone? |
| **Risk Factors** | Single maintainer? Depends on deprecated upstream? VC-backed vs. hobby? Bus factor? |
| **Market Fit** | What real problem does this solve? How large is the addressable user base? Growing or shrinking category? |
| **Competitive Moats** | First mover? Network effects? Strong brand? Technical depth that's hard to replicate? |
| **Production Readiness** | CI/CD present? Tests? Changelog? Semantic versioning? Breaking change policy? |

### AI Agent Specific Checks

When evaluating repos in the AI Agent domain, additionally assess:

| Check | Signal |
|-------|--------|
| MCP Support | MCP server/client integration — key interoperability signal |
| Multi-Agent | Multi-agent coordination patterns — indicates ambition |
| State Persistence | Checkpointing, memory, conversation persistence — production readiness |
| Local LLM | Support for local models (Ollama, llama.cpp) — privacy/offline appeal |
| Tool Calling | Structured tool use, function calling — core Agent capability |
| Observability | Tracing, logging, monitoring — operations maturity |
| Model Agnostic | Works with multiple LLM providers — reduces vendor lock-in |

### Output Format

Narrative with these subheadings:
1. **Summary** — 2-3 sentence verdict
2. **What it does well** — strengths
3. **What to watch for** — concerns, risks
4. **Who should use it** — target audience
5. **Verdict** — "Consider", "Watch", or "Pass" with rationale
