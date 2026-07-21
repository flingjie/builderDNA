"""Radar engine stub -- Task 4 in progress.

The real radar engine will be implemented in Task 4. This stub exists so that
the FastAPI application and router layers are importable and testable. It
raises NotImplementedError if called directly.
"""
from backend.models.trend import TrendSnapshot


async def run_radar(
    client, domain_config, store
) -> TrendSnapshot:
    """Run the radar engine to collect and analyze trend data.

    Args:
        client: GitHubClient instance.
        domain_config: DomainConfig describing the domain to analyze.
        store: TrendStore for persisting results.

    Returns:
        TrendSnapshot with analyzed topics.

    Raises:
        NotImplementedError: Always -- see Task 4 for implementation.
    """
    raise NotImplementedError("Radar engine not yet implemented (Task 4)")
