"""Adapter interfaces for embedding BuilderDNA in agent frameworks.

Provides an abstract interface and concrete implementations for
running BuilderDNA analysis from other agent systems, including
Claude Code skills and direct CLI usage.
"""

from adapters.interface import BuilderDNAAdapter
from adapters.cli import CLIAdapter
from adapters.claude_code import ClaudeCodeAdapter

__all__ = [
    "BuilderDNAAdapter",
    "CLIAdapter",
    "ClaudeCodeAdapter",
]
