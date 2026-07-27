"""CLI adapter — thin wrapper around BuilderDNA CLI commands.

Runs commands as subprocesses with the same interface as the
abstract BuilderDNAAdapter. Use this when you need to call
BuilderDNA from a non-Python environment or want process isolation.
"""

import json
import os
import subprocess
from pathlib import Path

from adapters.interface import BuilderDNAAdapter
from models.payload import SandboxResult, Diagnostics, TopicTrend


class CLIAdapter(BuilderDNAAdapter):
    """Adapter that runs BuilderDNA via CLI subprocess.

    Pros: Process isolation, works from any language, no import conflicts.
    Cons: Subprocess overhead, JSON serialization round-trip.
    """

    def __init__(self, python_path: str = ".", uv: bool = True):
        """Initialize CLI adapter.

        Args:
            python_path: PYTHONPATH value (defaults to current directory).
            uv: Whether to use `uv run` prefix.
        """
        self._python_path = python_path
        self._uv = uv

    def _run(self, *args: str) -> SandboxResult:
        """Execute a BuilderDNA CLI command and parse its SandboxResult output."""
        cmd_parts = []
        if self._uv:
            cmd_parts.extend(["uv", "run", "builderdna"])
        else:
            cmd_parts.extend(["python", "-m", "cli.main"])

        cmd_parts.extend(args)

        env = {**os.environ, "PYTHONPATH": self._python_path}
        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"BuilderDNA command failed (exit {result.returncode}):\n"
                f"stderr: {result.stderr[:500]}"
            )

        # Find the output file from args (--output or -o flag)
        output_path = None
        for i, arg in enumerate(args):
            if arg in ("--output", "-o") and i + 1 < len(args):
                output_path = args[i + 1]
                break

        if output_path and Path(output_path).exists():
            raw = json.loads(Path(output_path).read_text())
            return SandboxResult(**raw)

        raise RuntimeError(
            f"BuilderDNA completed but no output file found. stdout: {result.stdout[:200]}"
        )

    def analyze_domain(self, domain: str, **kwargs) -> SandboxResult:
        """Run collect → trend → pain → opportunity for a domain."""
        output_dir = kwargs.get("output_dir", "output")
        config_path = kwargs.get("config", "config.yaml")
        window = kwargs.get("window", 365)

        signals_path = kwargs.get("signals_path", f"{output_dir}/signals.json")
        trends_path = kwargs.get("trends_path", f"{output_dir}/trends.json")
        pains_path = kwargs.get("pains_path", f"{output_dir}/pain_clusters.json")
        opps_path = kwargs.get("opps_path", f"{output_dir}/opportunities.json")

        # Step 1: Collect (supports --config)
        self._run("collect", domain, "--output", signals_path, "--window", str(window),
                  "--config", config_path)

        # Step 2: Trend (no --config flag)
        self._run("trend", domain, "--data", signals_path, "--output", trends_path)

        # Step 3: Pain (supports --config)
        self._run("pain", domain, "--data", signals_path, "--output", pains_path,
                  "--config", config_path)

        # Step 4: Opportunity (returns the final result)
        return self._run(
            "opportunity",
            "--trends", trends_path,
            "--pains", pains_path,
            "--output", opps_path,
        )

    def get_trends(self, signals_path: str) -> list[TopicTrend]:
        """Compute trends from signals file. Returns list of TopicTrend."""
        # Extract domain from the signals SandboxResult
        try:
            raw_signals = json.loads(Path(signals_path).read_text())
            domain = raw_signals.get("domain", "unknown")
        except (json.JSONDecodeError, OSError):
            domain = "unknown"

        result = self._run(
            "trend", domain,
            "--data", signals_path,
            "--output", "/tmp/builderdna_trends_temp.json",
        )
        raw_trends = result.payload.get("trends", [])
        return [TopicTrend(**t) for t in raw_trends]

    def get_diagnostics(self, result: SandboxResult) -> Diagnostics:
        """Extract diagnostics from a SandboxResult (already parsed)."""
        return result.diagnostics
