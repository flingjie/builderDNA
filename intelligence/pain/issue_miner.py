"""Issue miner — fetches and extracts GitHub issues for pain analysis.

Migrated from backend/engine/pain.py (Phase 2).
Re-exports collector.github.issue.fetch_issues as the single implementation.
"""

from collector.github.issue import fetch_issues  # noqa: F401
