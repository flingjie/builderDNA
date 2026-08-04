"""Claude Code adapter — wraps CLI calls for Claude Code skill consumption.

When BuilderDNA is used as part of a Claude Code skill (like the builderdna
skill), this adapter provides a Python-native interface that Claude can
import and call directly, avoiding subprocess overhead.

Use CLIAdapter instead if you need process isolation or are calling from
a non-Python context.
"""

import asyncio
import concurrent.futures
from pathlib import Path

from adapters.interface import BuilderDNAAdapter
from models.payload import SandboxResult, Diagnostics, TopicTrend


def _run_async(coro):
    """Run an async coroutine, handling the case where an event loop is already running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)
    else:
        # Already in an event loop — use a thread
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()


class ClaudeCodeAdapter(BuilderDNAAdapter):
    """Adapter for Claude Code contexts — direct Python imports.

    Pros: No subprocess overhead, shared memory, import-level caching.
    Cons: Must run within the BuilderDNA Python environment.

    This adapter imports command internals directly rather than shelling out.
    It's the preferred adapter when BuilderDNA is invoked from a Claude Code
    skill that has access to the project Python environment.
    """

    def analyze_domain(self, domain: str, **kwargs) -> SandboxResult:
        """Run the full analysis pipeline for a domain.

        Note: This is a synchronous wrapper. For production use with many
        domains, consider running each command via the CLI adapter for
        process isolation.
        """
        from cli.commands.collect import _run_collect
        from cli.commands.trend import trend
        from cli.commands.pain import pain
        from cli.commands.opportunity import opportunity

        output_dir = kwargs.get("output_dir", "output")
        config_path = kwargs.get("config", "config.yaml")
        window = kwargs.get("window", 365)

        signals_path = kwargs.get("signals_path", f"{output_dir}/signals.json")
        trends_path = kwargs.get("trends_path", f"{output_dir}/trends.json")
        pains_path = kwargs.get("pains_path", f"{output_dir}/pain_clusters.json")
        opps_path = kwargs.get("opps_path", f"{output_dir}/opportunities.json")

        # Step 1: Collect
        _run_async(_run_collect(
            domain=domain,
            output=signals_path,
            config_path=config_path,
            window_days=window,
        ))

        # Step 2: Trend
        trend(
            domain=domain,
            data=signals_path,
            output=trends_path,
            window=window,
        )

        # Step 3: Pain
        pain(
            domain=domain,
            data=signals_path,
            output=pains_path,
        )

        # Read opportunity result (opportunity() writes to file, doesn't return)
        import json
        opportunity(
            trends=trends_path,
            pains=pains_path,
            output=opps_path,
        )
        raw = json.loads(Path(opps_path).read_text())
        return SandboxResult(**raw)

    def get_trends(self, signals_path: str) -> list[TopicTrend]:
        """Compute topic trends from signals file."""
        import json
        from cli.commands.trend import trend

        # Extract domain from the signals SandboxResult
        try:
            raw_signals = json.loads(Path(signals_path).read_text())
            domain = raw_signals.get("domain", "unknown")
        except (json.JSONDecodeError, OSError):
            domain = "unknown"

        temp_path = "/tmp/builderdna_trends_cc.json"
        trend(
            domain=domain,
            data=signals_path,
            output=temp_path,
        )
        raw = json.loads(Path(temp_path).read_text())
        result = SandboxResult(**raw)
        raw_trends = result.payload.get("trends", [])
        return [TopicTrend(**t) for t in raw_trends]

    def get_diagnostics(self, result: SandboxResult) -> Diagnostics:
        """Extract diagnostics from a SandboxResult."""
        return result.diagnostics
