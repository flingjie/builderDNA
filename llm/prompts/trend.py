"""Trend detection prompt templates."""


def build_trend_prompt(topics: list[str], repos_per_topic: dict[str, list[str]]) -> str:
    """Build prompt for trend analysis.

    Args:
        topics: List of topic names to analyze.
        repos_per_topic: Mapping of topic -> list of repo full_names.

    Returns:
        Prompt string for LLM.
    """
    topic_lines = []
    for topic in topics:
        repos = repos_per_topic.get(topic, [])
        topic_lines.append(f"- {topic}: {len(repos)} repos ({', '.join(repos[:5])})")

    return f"""Analyze these technology trends from GitHub data. For each topic, assess:

1. Stage: emerging / accelerating / mainstream / declining
2. Confidence: 0-1 (how certain is this assessment)
3. Key drivers: what is causing growth (1 sentence)

Topics:
{chr(10).join(topic_lines)}

Return JSON:
{{"trends": [{{"topic": "...", "stage": "...", "confidence": 0.8, "drivers": "..."}}]}}
"""
