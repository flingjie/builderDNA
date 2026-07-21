"""Theme Discovery engine — automatically detects emerging topics from broad GitHub search.

Runs independently of the fixed-topic Radar pipeline. Uses broad search (no
predefined topic keywords) to find new repos, clusters them via LLM, and
rates each cluster's heat.
"""
import asyncio
import math
from datetime import datetime, timezone, timedelta

from config import Config
from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot
from backend.store.discovery_store import DiscoveryStore


def _build_broad_query(config: Config) -> str:
    """Build a broad GitHub search query with language filters.

    Uses 'include' mode: searches only within specified languages.
    Falls back to no language filter if include list is empty.
    """
    parts = [f"stars:>={config.discovery.min_stars}"]

    since_date = (datetime.now(timezone.utc) - timedelta(days=config.discovery.lookback_days)).strftime("%Y-%m-%d")
    parts.append(f"created:>={since_date}")

    include_langs = config.discovery.language_filter.get("include", [])
    if include_langs:
        lang_clauses = " OR ".join(f"language:{lang}" for lang in include_langs)
        parts.append(f"({lang_clauses})")

    return " ".join(parts)


def _build_clustering_prompt(repos: list[dict]) -> str:
    """Build an LLM prompt to cluster repos into named themes."""
    repo_lines = []
    for r in repos:
        desc = (r.get("description") or "")[:120]
        topics = r.get("topics", [])[:5]
        repo_lines.append(
            f"- {r['full_name']}: {desc} [topics: {', '.join(topics) if topics else 'none'}]"
        )

    return f"""You are a technology trend analyst. Analyze these GitHub repositories and group them into 3-8 thematic clusters. Each cluster should represent an emerging technology direction or vertical.

Repos:
{chr(10).join(repo_lines)}

Rules:
- Name each cluster with a concise kebab-case topic (e.g. "ai-native-ide", "multi-agent-orchestration")
- Write a one-sentence description for each
- Merge semantically close directions; split genuinely different ones
- Skip noise: if a repo doesn't fit any clear cluster, leave it out
- For each cluster, count how many repos belong and estimate its velocity (1-10)

Return valid JSON:
{{"themes": [{{"topic": "...", "description": "...", "repo_count": N, "avg_stars": F, "velocity": F, "stage": "emerging", "sample_repos": ["a/b", "c/d"]}}]}}

Stage values: "emerging" (brand new, small but growing), "accelerating" (fast growth), "stable" (large and steady), "cooling" (slowing down)."""


def _compute_heat(repo_count: int, avg_velocity: float) -> str:
    """Classify a discovered theme's heat stage.

    Thresholds tuned for discovery mode (smaller clusters than radar topics):
      velocity >= 5.0 and count >= 5  → accelerating
      velocity >= 2.0 and count >= 3  → emerging
      velocity >= 0.5                  → stable
      otherwise                        → cooling
    """
    if avg_velocity >= 5.0 and repo_count >= 5:
        return "accelerating"
    if avg_velocity >= 2.0 and repo_count >= 3:
        return "emerging"
    if avg_velocity >= 0.5:
        return "stable"
    return "cooling"


async def _broad_search(client, config: Config) -> list[dict]:
    """Fetch repos via broad search query (1 page, controlled by max_results)."""
    query = _build_broad_query(config)
    try:
        params: dict[str, str] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": str(min(config.discovery.max_results, 100)),
        }
        resp = await client._request("GET", "/search/repositories", params=params)
        if resp is None:
            return []
        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return []
    except Exception:
        return []


def _compute_avg_velocity(repo: dict) -> float:
    """Compute a simple velocity metric for a repo."""
    stars = repo.get("stargazers_count", 0)
    created = repo.get("created_at")
    if not created:
        return 0.0
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        days = max(1, (datetime.now(timezone.utc) - dt).days)
        return stars / days
    except (ValueError, TypeError):
        return 0.0


async def run_discovery(client, config: Config, llm, store: DiscoveryStore) -> DiscoverySnapshot:
    """Run the full theme discovery pipeline.

    Broad search → enhance repos with velocity → LLM clustering → heat scoring → persist.

    Returns:
        DiscoverySnapshot with auto-discovered themes.
    """
    if not config.discovery.enabled:
        return DiscoverySnapshot(domain="global", window_days=config.discovery.lookback_days)

    # Step 1: Broad search
    raw_repos = await _broad_search(client, config)

    if not raw_repos:
        snapshot = DiscoverySnapshot(domain="global", window_days=config.discovery.lookback_days)
        store.save(snapshot)
        return snapshot

    # Step 2: Enrich repos with velocity data (for LLM consumption)
    for r in raw_repos:
        r["_velocity"] = round(_compute_avg_velocity(r), 2)

    # Step 3: LLM clustering
    known_topics: set[str] = set()
    for domain_cfg in config.domains.values():
        if isinstance(domain_cfg, dict):
            known_topics.update(domain_cfg.get("topics", []))

    try:
        prompt = _build_clustering_prompt(raw_repos)
        response = llm.complete(prompt, response_format=dict)
        themes_data = response.get("themes", [])
    except Exception:
        themes_data = []

    # Step 4: Heat scoring + mark known vs new
    themes = []
    for raw in themes_data:
        if not isinstance(raw, dict):
            continue
        topic = str(raw.get("topic", ""))[:50]
        repo_count = int(raw.get("repo_count", 0))
        vel = float(raw.get("velocity", 1.0))
        stage = raw.get("stage") or _compute_heat(repo_count, vel)

        themes.append(DiscoveredTheme(
            topic=topic,
            description=str(raw.get("description", ""))[:200],
            repo_count=repo_count,
            avg_stars=float(raw.get("avg_stars", 0.0)),
            velocity=vel,
            stage=stage,
            sample_repos=[str(r) for r in raw.get("sample_repos", [])[:5]],
            is_new=topic not in known_topics,
            suggested_as_topic=topic not in known_topics,
        ))

    # Sort by velocity desc
    themes.sort(key=lambda t: t.velocity, reverse=True)

    snapshot = DiscoverySnapshot(
        domain="global",
        window_days=config.discovery.lookback_days,
        themes=themes,
    )
    store.save(snapshot)
    return snapshot
