"""Trend Radar engine — detects accelerating GitHub topics and repos.

Phase 1 uses GitHub Search API to find repos by topic, then computes
trend scores using either 1st-order velocity (first run) or 2nd-order
acceleration (subsequent runs with snapshot history).
"""

import asyncio
import math
from datetime import datetime, timezone

from backend.models.trend import DomainConfig, RepoTrend, TopicTrend, TrendSnapshot


def _days_since(date_str: str | None) -> int:
    """Calculate days between date_str and now."""
    if not date_str:
        return 365
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return max(1, (datetime.now(timezone.utc) - dt).days)
    except (ValueError, TypeError):
        return 365


def compute_repo_trend(
    repo_data: dict,
    prev_snapshot: TrendSnapshot | None,
    contributors: int = 0,
) -> RepoTrend:
    """Compute trend score for a single repo.

    First run (prev_snapshot=None): uses 1st-order velocity.
    Subsequent runs: uses 2nd-order acceleration.

    Formula (first run):
      velocity = stars / days_since_first_release
      trend_score = velocity * log10(forks+1) * log10(contributors+1)

    Formula (second run):
      velocity_now = (stars - prev_stars) / dt
      acceleration = (velocity_now - prev_velocity) / dt
      trend_score = acceleration * log10(forks+1) * log10(growth+1)
    """
    full_name = repo_data.get("full_name", "")
    stars = repo_data.get("stargazers_count", 0)
    forks = repo_data.get("forks_count", 0)
    created_at = repo_data.get("created_at")
    days_since_release = _days_since(created_at)

    velocity = stars / max(1, days_since_release)
    trend_score = velocity * math.log10(forks + 1) * math.log10(contributors + 1)
    stars_delta = 0
    contributor_growth = 0.0

    if prev_snapshot:
        prev_repo = None
        for topic in prev_snapshot.topics:
            for r in topic.top_repos:
                if r.full_name == full_name:
                    prev_repo = r
                    break
            if prev_repo:
                break

        if prev_repo and prev_repo.velocity > 0:
            prev_created = prev_snapshot.created_at
            if prev_created.tzinfo is None:
                prev_created = prev_created.replace(tzinfo=timezone.utc)
            dt = max(1, (datetime.now(timezone.utc) - prev_created).days)

            velocity_now = (stars - prev_repo.stars) / dt
            acceleration = (velocity_now - prev_repo.velocity) / dt

            if prev_repo.contributors > 0:
                contributor_growth = (contributors - prev_repo.contributors) / prev_repo.contributors

            trend_score = (
                acceleration
                * math.log10(forks + 1)
                * math.log10(max(0, contributor_growth) + 1)
            )
            stars_delta = stars - prev_repo.stars
            velocity = velocity_now

    return RepoTrend(
        full_name=full_name,
        stars=stars,
        stars_delta=stars_delta,
        forks=forks,
        contributors=contributors,
        contributor_growth=round(contributor_growth, 2),
        velocity=round(velocity, 2),
        trend_score=round(trend_score, 2),
        days_since_first_release=days_since_release,
    )


def get_stage(score: float) -> str:
    """Map trend score to a lifecycle stage."""
    if score >= 80:
        return "accelerating"
    if score >= 50:
        return "emerging"
    if score >= 20:
        return "mainstream"
    return "declining"


def aggregate_topic(repos: list[RepoTrend], topic: str) -> TopicTrend:
    """Aggregate individual repo trends into a topic-level trend."""
    repos_sorted = sorted(repos, key=lambda r: r.trend_score, reverse=True)
    top_5 = repos_sorted[:5]

    if not top_5:
        return TopicTrend(
            topic=topic, stage="declining", confidence=0.0,
            growth_velocity=0.0, evidence_count=0, top_repos=[],
        )

    avg_score = sum(r.trend_score for r in top_5) / len(top_5)
    avg_velocity = sum(r.velocity for r in top_5) / len(top_5)

    accelerating_count = sum(1 for r in top_5 if r.trend_score >= 50)
    confidence = accelerating_count / max(1, len(top_5))

    return TopicTrend(
        topic=topic,
        stage=get_stage(avg_score),
        confidence=round(confidence, 2),
        growth_velocity=round(avg_velocity, 2),
        evidence_count=len(repos),
        top_repos=top_5,
    )


async def collect_topic_data(client, topic: str, max_results: int = 30) -> list[dict]:
    """Fetch repos for a topic from GitHub Search API.

    Returns list of raw repo dicts with stars, forks, created_at, etc.
    """
    params = {
        "q": f"topic:{topic}",
        "sort": "stars",
        "order": "desc",
        "per_page": str(max_results),
    }
    try:
        results = await client._paginate("/search/repositories", extra_params=params)
        return results
    except Exception:
        return []


async def run_radar(client, domain_config: DomainConfig, store) -> TrendSnapshot:
    """Run the full radar analysis for a domain.

    Fetches repos per topic concurrently, computes trends per repo,
    aggregates to topic level, and persists the snapshot.
    """
    prev_snapshot = store.get_latest(domain_config.name)

    async def process_topic(topic: str) -> TopicTrend:
        repos_raw = await collect_topic_data(client, topic)
        repo_trends = [compute_repo_trend(r, prev_snapshot) for r in repos_raw]
        return aggregate_topic(repo_trends, topic)

    all_topics = await asyncio.gather(
        *[process_topic(t) for t in domain_config.topics]
    )

    # Keep only topics with evidence
    all_topics = [t for t in all_topics if t.evidence_count > 0]
    all_topics.sort(key=lambda t: t.growth_velocity, reverse=True)

    snapshot = TrendSnapshot(
        domain=domain_config.name,
        window_days=domain_config.window_days,
        topics=all_topics,
    )
    store.save(snapshot)

    # ── Phase 2: Pain Mining on top trend repos ──
    top_repos: list[str] = []
    seen_repos: set[str] = set()
    for topic in all_topics[:3]:  # top 3 topics
        for repo in topic.top_repos[:2]:  # top 2 repos per topic
            if repo.full_name not in seen_repos:
                seen_repos.add(repo.full_name)
                top_repos.append(repo.full_name)
    top_repos = top_repos[:5]  # cap at 5

    if top_repos:
        try:
            from backend.engine.pain import run_pain_mining
            from backend.store.pain_store import PainStore
            from llm.client import OpenAIClient
            from config import load_config

            cfg = load_config("config.yaml")
            llm_client = OpenAIClient(
                api_key=cfg.llm.api_key,
                model=cfg.llm.model,
                base_url=cfg.llm.base_url,
            )
            pain_store = PainStore()
            await run_pain_mining(client, top_repos, llm_client, pain_store)
        except Exception as e:
            print(f"[Pain Mining] Skipped: {e}")

    # ── Phase 3: Opportunity Intelligence ──
    try:
        from backend.engine.opportunity import run_opportunity_engine
        from backend.store.opportunity_store import OpportunityStore
        from backend.store.pain_store import PainStore
        from llm.client import OpenAIClient
        from config import load_config

        trend_snapshot = store.get_latest(domain_config.name)
        pain_snapshot = PainStore().get_latest(domain_config.name)

        if trend_snapshot and pain_snapshot:
            cfg = load_config("config.yaml")
            llm_client = OpenAIClient(
                api_key=cfg.llm.api_key,
                model=cfg.llm.model,
                base_url=cfg.llm.base_url,
            )
            opp_store = OpportunityStore()
            await run_opportunity_engine(trend_snapshot, pain_snapshot, llm_client, opp_store)
    except Exception as e:
        print(f"[Opportunity] Skipped: {e}")

    return snapshot
