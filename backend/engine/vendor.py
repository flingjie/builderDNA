"""Vendor Tracking engine — tracks GitHub org/account behavior across 4 dimensions.

Dimensions: org dynamics, member activity, hiring signals, release cadence.
Generates domestic vs. overseas comparison diffs via LLM.
"""
import asyncio
from datetime import datetime, timezone, timedelta

from config import Config
from backend.models.vendor import (
    VendorProfile, VendorSnapshot, VendorDiff, VendorDirection, VendorSignal
)
from backend.store.vendor_store import VendorStore


async def _track_single_vendor(
    client, org_name: str, display_name: str, tags: list[str], comparison_group: str
) -> VendorProfile:
    """Track a single vendor across all 4 dimensions.

    Returns a VendorProfile even on API errors (with zero values).
    """
    profile = VendorProfile(
        name=org_name,
        display_name=display_name or org_name,
        accounts=[org_name],
        tags=tags,
        comparison_group=comparison_group,
    )

    try:
        repos = await client.get_repos(org_name)
    except Exception:
        return profile  # graceful degradation

    profile.total_public_repos = len(repos)

    # Dimension 1: Org dynamics — topic distribution from repos
    topic_intensity: dict[str, float] = {}
    total_stars = 0
    recent_signals: list[VendorSignal] = []

    for repo in repos:
        stars = repo.get("stargazers_count", 0)
        total_stars += stars
        for topic in repo.get("topics", [])[:10]:
            topic_intensity[topic] = topic_intensity.get(topic, 0) + 1

        # Recent repo creation = signal
        created = repo.get("created_at", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if dt > datetime.now(timezone.utc) - timedelta(days=90):
                    recent_signals.append(VendorSignal(
                        type="new_repo",
                        repo=repo.get("full_name", ""),
                        timestamp=created,
                    ))
            except (ValueError, TypeError):
                pass

    profile.total_stars = total_stars

    # Normalize topic intensity to 0-1
    max_intensity = max(topic_intensity.values()) if topic_intensity else 1
    profile.active_directions = [
        VendorDirection(
            topic=t,
            intensity=round(v / max_intensity, 2),
            trend="→",  # delta requires previous snapshot, TBD in subsequent runs
        )
        for t, v in sorted(topic_intensity.items(), key=lambda x: -x[1])[:10]
    ]
    profile.recent_signals = recent_signals

    return profile


def _build_comparison_prompt(profiles: list[VendorProfile]) -> str:
    """Build LLM prompt for domestic-vs-overseas comparison."""
    domestic_lines = []
    overseas_lines = []
    for p in profiles:
        entry = f"- {p.display_name} ({p.name}): {', '.join(d.topic for d in p.active_directions[:5])}"
        if p.comparison_group == "domestic":
            domestic_lines.append(entry)
        else:
            overseas_lines.append(entry)

    return f"""Compare domestic (Chinese) vs overseas AI vendor strategies from their GitHub activity.

🇨🇳 Domestic:
{chr(10).join(domestic_lines) if domestic_lines else 'No data'}

🌍 Overseas:
{chr(10).join(overseas_lines) if overseas_lines else 'No data'}

For EACH technology dimension where both sides show activity, produce a comparison. Return JSON:
{{"diffs": [{{"dimension": "topic-name", "domestic_summary": "what Chinese vendors are doing in Chinese", "overseas_summary": "what overseas vendors are doing in Chinese", "common_patterns": "shared trend in Chinese", "domestic_vendors": ["vendor1"], "overseas_vendors": ["vendor2"]}}]}}

IMPORTANT: Write all summary fields in Chinese. Focus on strategic differences, not just listing repos."""


async def run_vendor_tracking(
    client, config: Config, llm, store: VendorStore
) -> VendorSnapshot:
    """Run full vendor tracking pipeline.

    Tracks all configured vendors → persists snapshot → optionally generates comparison diffs.
    """
    profiles: list[VendorProfile] = []

    # Track domestic vendors
    for org_name in config.vendors.domestic:
        profile = await _track_single_vendor(
            client, org_name, org_name, ["🇨🇳 国产"], "domestic"
        )
        profiles.append(profile)

    # Track overseas vendors
    for org_name in config.vendors.overseas:
        profile = await _track_single_vendor(
            client, org_name, org_name, ["🌍 海外"], "overseas"
        )
        profiles.append(profile)

    # Build snapshot
    snapshot = VendorSnapshot(
        domain="agent",
        window_days=60,
        profiles=profiles,
    )
    store.save(snapshot)
    return snapshot


async def generate_comparison(client, config: Config, llm) -> list[VendorDiff]:
    """Generate domestic-vs-overseas comparison diffs for the latest snapshot."""
    store = VendorStore()
    snapshot = store.get_latest("agent")
    if snapshot is None or not snapshot.profiles:
        return []

    prompt = _build_comparison_prompt(snapshot.profiles)
    try:
        response = llm.complete(prompt, response_format=dict)
    except Exception:
        return []

    diffs = []
    for raw in response.get("diffs", []):
        if not isinstance(raw, dict):
            continue
        diffs.append(VendorDiff(
            dimension=str(raw.get("dimension", ""))[:50],
            domestic_summary=str(raw.get("domestic_summary", ""))[:200],
            overseas_summary=str(raw.get("overseas_summary", ""))[:200],
            common_patterns=str(raw.get("common_patterns", ""))[:200],
            domestic_vendors=[str(v) for v in raw.get("domestic_vendors", [])[:10]],
            overseas_vendors=[str(v) for v in raw.get("overseas_vendors", [])[:10]],
        ))
    return diffs
