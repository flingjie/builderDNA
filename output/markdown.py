"""Markdown report generator."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_markdown(result: dict[str, Any], output_dir: str | Path) -> Path:
    """Write a Markdown report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_id = result.get("snapshot_id", "unknown")
    filepath = output_dir / f"report-{ts}-{snapshot_id}.md"

    signals = result.get("signals", [])
    insights = result.get("insights", [])
    opportunities = result.get("opportunities", [])
    diff = result.get("diff")

    lines = [
        f"# BuilderDNA Analysis Report", "",
        f"**Snapshot:** `{snapshot_id}`",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}", "",
    ]

    if diff:
        lines += _md_diff(diff)
    lines += _md_signal_summary(signals)
    lines += _md_insights(insights)
    lines += _md_opportunities(opportunities)

    filepath.write_text("\n".join(lines))
    return filepath


def _md_diff(diff: dict) -> list[str]:
    lines = ["## Changes Since Last Run", ""]
    new_count = diff.get("new_signals", 0)
    lines.append(f"- **New signals:** {new_count:+d} (total: {diff.get('total_signals', 0)})")
    lines.append("")
    topic_changes = diff.get("topic_weight_changes", {})
    if topic_changes:
        lines.append("### Topic Weight Changes\n")
        lines.append("| Topic | Previous | Current | Change |")
        lines.append("|-------|----------|---------|--------|")
        for topic, data in sorted(topic_changes.items(), key=lambda x: abs(x[1]["change_pct"]), reverse=True)[:10]:
            lines.append(f"| {topic} | {data['previous']:.1f} | {data['current']:.1f} | {data['change_pct']:+.1f}% |")
        lines.append("")
    return lines


def _md_signal_summary(signals: list) -> list[str]:
    lines = ["## Signal Summary", ""]
    if not signals:
        lines.append("_No signals collected._\n"); return lines
    by_type: dict[str, dict] = {}
    for s in signals:
        if s.type not in by_type:
            by_type[s.type] = {"count": 0, "weight": 0.0}
        by_type[s.type]["count"] += 1; by_type[s.type]["weight"] += s.weight
    lines.append("| Type | Count | Total Weight |")
    lines.append("|------|-------|-------------|")
    tc, tw = 0, 0.0
    for stype in sorted(by_type):
        d = by_type[stype]; tc += d["count"]; tw += d["weight"]
        lines.append(f"| {stype} | {d['count']} | {d['weight']:.1f} |")
    lines.append(f"| **TOTAL** | **{tc}** | **{tw:.1f}** |\n")
    return lines


def _md_insights(insights: list) -> list[str]:
    lines = ["## Insights", ""]
    if not insights:
        lines.append("_No insights generated._\n"); return lines
    for ins in insights:
        trend_emoji = {"rising": "🔺", "stable": "🟡", "fading": "🔻"}.get(ins.trend, "")
        lines.append(f"### {', '.join(ins.tags[:5])} {trend_emoji}\n")
        lines.append(f"- **Summary:** {ins.summary}")
        lines.append(f"- **Strength:** {ins.strength:.1f}")
        lines.append(f"- **Trend:** {ins.trend}")
        lines.append(f"- **Signal Count:** {ins.signal_count}")
        if ins.evidence:
            lines.append(f"- **Evidence:** {', '.join(ins.evidence[:5])}")
        lines.append("")
    return lines


def _md_opportunities(opportunities: list) -> list[str]:
    lines = ["## Opportunities (SSOT)", ""]
    if not opportunities:
        lines.append("_No opportunities detected._\n"); return lines
    lines.append("| # | Title | Demand | Competition | Gap | Action |")
    lines.append("|---|-------|--------|-------------|-----|--------|")
    for i, op in enumerate(opportunities, 1):
        lines.append(f"| {i} | **{op.title}** | {op.demand_score:.1f} | {op.competition_score:.1f} | {op.gap_score:.2f} | {op.recommended_action} |")
    lines.append("")
    lines.append("## Top Opportunity Details\n")
    for i, op in enumerate(opportunities[:5], 1):
        lines.append(f"### {i}. {op.title}\n")
        lines.append(f"- **Pain Point:** {op.pain_point}")
        lines.append(f"- **Gap Score:** {op.gap_score:.2f}")
        lines.append(f"- **Recommended Action:** {op.recommended_action}")
        lines.append(f"- **Source Insights:** {', '.join(op.source_insights)}")
        lines.append("")
    return lines
