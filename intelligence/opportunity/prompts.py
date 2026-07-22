"""Opportunity generation prompt templates — migrated from llm/prompts/opportunity.py."""


def build_opportunity_prompt(
    trends: list[dict], pains: list[dict], graph_data: dict
) -> str:
    """Build prompt for opportunity generation.

    Args:
        trends: List of {topic, stage, velocity, top_repos}.
        pains: List of {title, severity, affected_repos}.
        graph_data: Signal Graph export (bridging repos, co-occurring topics).

    Returns:
        Prompt string for LLM.
    """
    trend_lines = [f"- {t['topic']}: stage={t['stage']}, velocity={t.get('velocity', 0)}" for t in trends]
    pain_lines = [f"- {p['title']}: severity={p.get('severity', 0)}" for p in pains]
    bridges = graph_data.get("bridging_repos", [])

    return f"""You are a top-tier AI venture strategist. Identify 3-5 concrete product/business opportunities from these signals.

TREND SIGNALS:
{chr(10).join(trend_lines)}

PAIN SIGNALS:
{chr(10).join(pain_lines)}

BRIDGING REPOS (connecting different technology domains):
{bridges[:10]}

For each opportunity:
1. Title: concise opportunity name
2. Why now: why this problem is urgent (1 sentence)
3. Problem: the core user pain (1 sentence)
4. MVP: minimum viable product (2-3 bullet points)
5. Score: 1-10 (be strict -- most opportunities are 5-7)
6. Risk: low/medium/high

Return JSON:
{{"opportunities": [{{"title": "...", "why_now": "...", "problem": "...", "mvp": "...", "score": 6.0, "risk": "medium"}}]}}

IMPORTANT: Write all titles and descriptions in Chinese (中文)."""


def build_critic_prompt(opportunity: dict) -> str:
    """Build prompt for the Critic Agent to challenge an opportunity.

    Args:
        opportunity: Dict with title, why_now, problem, mvp, score, risk.

    Returns:
        Prompt string for LLM (holding a deliberately skeptical stance).
    """
    return f"""You are a skeptical venture capital investor. Review this startup opportunity and identify its biggest risks.

OPPORTUNITY:
- Title: {opportunity.get('title', '')}
- Why now: {opportunity.get('why_now', '')}
- Problem: {opportunity.get('problem', '')}
- MVP: {opportunity.get('mvp', '')}
- Generator score: {opportunity.get('score', 0)}/10

Rate each dimension 1-10 (be harsh -- not everything is an 8):
1. Feasibility: Can this actually be built?
2. Market size: Is this a real market?
3. Timing: Is now the right time?

List 1-3 blind spots the generator missed. Give a one-sentence counter-view.

Return JSON:
{{"feasibility": 5, "market_size": 4, "timing": 6, "blind_spots": ["risk1"], "counter_view": "This might fail because..."}}

IMPORTANT: Write all text fields in Chinese (中文)."""
