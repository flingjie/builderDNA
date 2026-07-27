"""Abstract adapter interface for BuilderDNA.

Defines the clean boundary: any agent framework that implements
this interface can embed BuilderDNA analysis capabilities.
"""

from abc import ABC, abstractmethod

from models.payload import SandboxResult, Diagnostics, TopicTrend


class BuilderDNAAdapter(ABC):
    """Abstract adapter for embedding BuilderDNA in agent frameworks.

    Concrete implementations handle the transport layer (CLI calls,
    subprocess, in-process Python, etc.) while exposing a consistent
    interface for running analysis and retrieving diagnostics.
    """

    @abstractmethod
    def analyze_domain(self, domain: str, **kwargs) -> SandboxResult:
        """Run the full analysis pipeline for a domain.

        Args:
            domain: Domain name (must exist in config.yaml domains).
            **kwargs: Additional parameters (window, output path, etc.).

        Returns:
            SandboxResult with payload, stats, and diagnostics.
        """
        ...

    @abstractmethod
    def get_trends(self, signals_path: str) -> list[TopicTrend]:
        """Compute topic trends from collected signals.

        Args:
            signals_path: Path to a SandboxResult JSON from collect.

        Returns:
            List of TopicTrend objects with velocity, stage, and confidence.
        """
        ...

    @abstractmethod
    def get_diagnostics(self, result: SandboxResult) -> Diagnostics:
        """Extract diagnostics from a SandboxResult.

        Args:
            result: Any SandboxResult from a BuilderDNA command.

        Returns:
            Diagnostics with data_quality, confidence, and parameter_sensitivity.
        """
        ...
