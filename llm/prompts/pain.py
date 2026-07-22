"""Pain mining prompt templates."""


def build_pain_cluster_naming_prompt(
    cluster_id: str, issue_count: int, top_issues: list[dict]
) -> str:
    """Build prompt to name a pain cluster and describe its root cause.

    Args:
        cluster_id: HDBSCAN cluster label.
        issue_count: Number of issues in this cluster.
        top_issues: Top 3-5 representative issues with title + body.

    Returns:
        Prompt string for LLM.
    """
    issue_lines = []
    for iss in top_issues:
        title = iss.get("title", "")[:100]
        body = (iss.get("body", "") or "")[:200]
        issue_lines.append(f"- #{iss.get('issue_number')}: {title}\n  {body}")

    return f"""Name this developer pain cluster and identify its root cause.

Cluster size: {issue_count} issues

Top issues:
{chr(10).join(issue_lines)}

Rules:
- Title: <=5 words, descriptive (e.g. "MCP Connection Instability")
- Root cause: 1 sentence explaining why this pain pattern exists
- Severity: 1-5 (5 = critical, blocking production)

Return JSON:
{{"title": "...", "root_cause": "...", "severity": 3.0}}
"""
