"""Cross-run diagnostics — parameter sensitivity, bootstrap, and optimization hints.

This module operates at the observability layer: it reads SandboxResult outputs,
compares them against snapshots and hypothesis history, and generates actionable
parameter sensitivity hints for the optimize skill.

Functions here do NOT run CLI commands — they analyze existing output data.
"""

import json
from pathlib import Path

from models.payload import SandboxResult, ParamSensitivity

BOOTSTRAP_PATH = "state/bootstrap.json"


def _ensure_dir(filepath: str) -> None:
    """Ensure parent directory exists for a file path."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)


# ── Parameter Sensitivity ────────────────────────────────────────


def generate_parameter_sensitivity(
    result: SandboxResult,
    domain: str = "",
) -> list[ParamSensitivity]:
    """Generate parameter sensitivity hints from a single SandboxResult.

    Analyzes the result's diagnostics to suggest concrete parameter changes.
    Cross-references with historical snapshots when available.
    """
    hints: list[ParamSensitivity] = []

    diag = result.diagnostics

    # coverage gaps → suggest topic expansion or window widening
    if diag.data_quality.coverage_gaps:
        gap_topics = []
        for gap in diag.data_quality.coverage_gaps:
            # Extract topic name from message like "topic 'X' matched only..."
            if "topic '" in gap:
                import re
                match = re.search(r"topic '([^']+)'", gap)
                if match:
                    gap_topics.append(match.group(1))

        if gap_topics:
            hints.append(ParamSensitivity(
                parameter="config.domains.<domain>.topics",
                current_value="current topic list",
                suggested_value=f"add broader synonyms for: {', '.join(gap_topics[:3])}",
                expected_effect=f"Add specific subtopics or broader keywords to improve match rate for low-coverage topics",
                confidence=0.7,
            ))

    # sample size warning → suggest window extension
    if diag.data_quality.sample_size_warning:
        hints.append(ParamSensitivity(
            parameter="--window",
            current_value="current window setting",
            suggested_value="extend window by 50-100%",
            expected_effect="Larger window captures more repos, improving sample size and confidence",
            confidence=0.6,
        ))

    # API issues → suggest rate limit tuning
    if diag.data_quality.api_issues:
        for issue in diag.data_quality.api_issues:
            if "rate-limited" in issue.lower():
                hints.append(ParamSensitivity(
                    parameter="config.github.rate_limit_margin",
                    current_value="current margin",
                    suggested_value="increase by 10-20",
                    expected_effect="Higher margin reduces rate-limit waits and retry exhaustions",
                    confidence=0.8,
                ))
                break

    # low confidence items → suggest topic refinement
    if diag.confidence.low_confidence_items:
        low_conf_count = len(diag.confidence.low_confidence_items)
        hints.append(ParamSensitivity(
            parameter="config.domains.<domain>.topics",
            current_value="current topic list",
            suggested_value="remove overly broad topics, add more specific ones",
            expected_effect=f"More focused topics should improve confidence for {low_conf_count} low-confidence items",
            confidence=0.5,
        ))

    return hints


# ── Bootstrap ─────────────────────────────────────────────────────


def _load_bootstrap() -> dict:
    """Load bootstrap state. Returns empty structure if file missing."""
    p = Path(BOOTSTRAP_PATH)
    if not p.exists():
        return {
            "version": 1,
            "collect": {
                "high_quality_queries": [],
                "effective_windows": [],
                "domain_best_practices": {},
            },
            "trend": {
                "effective_topics": {},
                "good_windows": {},
            },
        }
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "collect": {}, "trend": {}}


def _save_bootstrap(data: dict) -> None:
    """Persist bootstrap state."""
    _ensure_dir(BOOTSTRAP_PATH)
    Path(BOOTSTRAP_PATH).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def record_bootstrap(result: SandboxResult, quality: str) -> None:
    """Record a high-quality run's parameters for future bootstrap hints.

    Args:
        result: The SandboxResult that was marked as high quality.
        quality: 'high', 'medium', or 'low' — only 'high' is recorded.
    """
    if quality != "high":
        return

    bootstrap = _load_bootstrap()
    command = result.command
    domain = result.domain

    if command == "collect":
        if domain not in bootstrap.setdefault("collect", {}).setdefault("domain_best_practices", {}):
            bootstrap["collect"]["domain_best_practices"][domain] = {
                "count": 0,
                "window_days": [],
                "topic_count": [],
            }
        bp = bootstrap["collect"]["domain_best_practices"][domain]
        bp["count"] += 1

        # Extract window from stats if available
        if result.stats.get("topics_searched"):
            bp["topic_count"].append(result.stats["topics_searched"])

    elif command == "trend":
        payload = result.payload
        trends = payload.get("trends", [])
        if domain not in bootstrap.setdefault("trend", {}).setdefault("effective_topics", {}):
            bootstrap["trend"]["effective_topics"][domain] = {}
        # Record which topics had high confidence
        for t in trends:
            if t.get("confidence", 0) > 0.5:
                topic_name = t.get("topic", "")
                bootstrap["trend"]["effective_topics"][domain][topic_name] = (
                    bootstrap["trend"]["effective_topics"][domain].get(topic_name, 0) + 1
                )

    _save_bootstrap(bootstrap)


def get_bootstrap_hints(domain: str, command: str) -> list[dict]:
    """Get bootstrap hints for a given domain and command.

    Returns list of hint dicts with 'type', 'suggestion', and 'confidence'.
    Used by the optimize skill to prioritize proposals backed by history.
    """
    bootstrap = _load_bootstrap()
    hints: list[dict] = []

    if command == "collect":
        bp = bootstrap.get("collect", {}).get("domain_best_practices", {}).get(domain)
        if bp and bp.get("count", 0) >= 2:
            hints.append({
                "type": "domain_best_practice",
                "suggestion": f"This domain ({domain}) has {bp['count']} prior high-quality runs — "
                              f"current topic and window settings are likely well-tuned",
                "confidence": 0.8,
            })

    elif command == "trend":
        topics = bootstrap.get("trend", {}).get("effective_topics", {}).get(domain, {})
        if topics:
            top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:3]
            hints.append({
                "type": "effective_topics",
                "suggestion": f"Topics with historically high confidence: "
                              f"{', '.join(f'{t[0]} ({t[1]}x)' for t in top_topics)}",
                "confidence": 0.7,
            })

    return hints


# ── Cross-run comparison ──────────────────────────────────────────


def compare_diagnostics(
    current: SandboxResult,
    previous: SandboxResult,
) -> dict:
    """Compare diagnostics between two runs to detect improvement or regression.

    Returns a summary dict with 'improvements', 'regressions', and 'stable' lists.
    """
    result = {
        "improvements": [],
        "regressions": [],
        "stable": [],
    }

    cur = current.diagnostics
    prev = previous.diagnostics

    # Coverage gaps: fewer is better
    cur_gaps = len(cur.data_quality.coverage_gaps)
    prev_gaps = len(prev.data_quality.coverage_gaps)
    if cur_gaps < prev_gaps:
        result["improvements"].append(
            f"coverage gaps: {prev_gaps} → {cur_gaps}"
        )
    elif cur_gaps > prev_gaps:
        result["regressions"].append(
            f"coverage gaps: {prev_gaps} → {cur_gaps}"
        )
    else:
        result["stable"].append(f"coverage gaps: {cur_gaps} (unchanged)")

    # Low confidence items
    cur_lc = len(cur.confidence.low_confidence_items)
    prev_lc = len(prev.confidence.low_confidence_items)
    if cur_lc < prev_lc:
        result["improvements"].append(
            f"low confidence items: {prev_lc} → {cur_lc}"
        )
    elif cur_lc > prev_lc:
        result["regressions"].append(
            f"low confidence items: {prev_lc} → {cur_lc}"
        )
    else:
        result["stable"].append(f"low confidence items: {cur_lc} (unchanged)")

    # Sample size warnings
    cur_warn = bool(cur.data_quality.sample_size_warning)
    prev_warn = bool(prev.data_quality.sample_size_warning)
    if prev_warn and not cur_warn:
        result["improvements"].append("sample size warning resolved")
    elif not prev_warn and cur_warn:
        result["regressions"].append("new sample size warning appeared")

    # Noise sources
    cur_noise = len(cur.data_quality.noise_sources)
    prev_noise = len(prev.data_quality.noise_sources)
    if cur_noise < prev_noise:
        result["improvements"].append(
            f"noise sources: {prev_noise} → {cur_noise}"
        )
    elif cur_noise > prev_noise:
        result["regressions"].append(
            f"noise sources: {prev_noise} → {cur_noise}"
        )

    # API issues
    cur_api = len(cur.data_quality.api_issues)
    prev_api = len(prev.data_quality.api_issues)
    if cur_api < prev_api:
        result["improvements"].append(
            f"API issues: {prev_api} → {cur_api}"
        )
    elif cur_api > prev_api:
        result["regressions"].append(
            f"API issues: {prev_api} → {cur_api}"
        )

    return result
