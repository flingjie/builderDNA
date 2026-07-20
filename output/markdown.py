"""Markdown report generator — Chinese labels with source attribution, simplified."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _find_cluster(clusters: list, cluster_id: str) -> dict | None:
    """Find a cluster by ID from the in-memory cluster list."""
    for c in clusters:
        cid = c.id if hasattr(c, 'id') else c.get('id', '')
        if cid == cluster_id:
            return c
    return None


def _get_actor_repo_from_insight(insight, clusters: list) -> tuple[dict[str, int], list[str]]:
    """Resolve source attribution for an insight via cluster ID chain."""
    cid = insight.source_cluster_id if hasattr(insight, 'source_cluster_id') else insight.get('source_cluster_id', '')
    c = _find_cluster(clusters, cid)
    if c is None:
        return {}, []
    ab = c.actor_breakdown if hasattr(c, 'actor_breakdown') else c.get('actor_breakdown', {})
    tr = c.top_repos if hasattr(c, 'top_repos') else c.get('top_repos', [])
    return ab, tr


def _sc(insight) -> int:
    """Get signal_count, works with both pydantic models and dicts."""
    return insight.signal_count if hasattr(insight, 'signal_count') else insight.get('signal_count', 0)


def write_markdown(result: dict[str, Any], output_dir: str | Path) -> Path:
    """Write a simplified Chinese Markdown report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_id = result.get("snapshot_id", "unknown")
    filepath = output_dir / f"report-{ts}-{snapshot_id}.md"

    clusters = result.get("clusters", [])
    insights = result.get("insights", [])
    opportunities = result.get("opportunities", [])
    diff = result.get("diff")

    lines = [
        f"# BuilderDNA 分析报告", "",
        f"**快照:** `{snapshot_id}`",
        f"**生成时间:** {datetime.now(timezone.utc).isoformat()}", "",
    ]

    if diff:
        lines += _md_diff(diff)
    lines += _md_insights(insights, clusters)
    lines += _md_opportunities(opportunities, insights, clusters)

    filepath.write_text("\n".join(lines))
    return filepath


def _md_diff(diff: dict) -> list[str]:
    lines = ["## 变化摘要", ""]
    new_count = diff.get("new_signals", 0)
    lines.append(f"- **新增信号:** {new_count:+d} (总计: {diff.get('total_signals', 0)})")
    lines.append("")
    topic_changes = diff.get("topic_weight_changes", {})
    if topic_changes:
        lines.append("### 话题权重变化\n")
        lines.append("| 话题 | 上次 | 本次 | 变化 |")
        lines.append("|------|------|------|------|")
        for topic, data in sorted(topic_changes.items(), key=lambda x: abs(x[1]["change_pct"]), reverse=True)[:10]:
            lines.append(f"| {topic} | {data['previous']:.1f} | {data['current']:.1f} | {data['change_pct']:+.1f}% |")
        lines.append("")
    return lines


def _md_insights(insights: list, clusters: list) -> list[str]:
    lines = ["## 技术洞察", ""]
    if not insights:
        lines.append("_未生成洞察。_\n"); return lines

    # Only show multi-signal insights (skip single-star noise)
    shown = 0
    for ins in insights:
        if _sc(ins) <= 1:
            continue
        shown += 1
        tags = ins.tags if hasattr(ins, 'tags') else ins.get('tags', [])
        tag_str = ", ".join(tags[:5])
        lines.append(f"### {tag_str}\n")
        lines.append(f"{ins.summary}")

        _, tr = _get_actor_repo_from_insight(ins, clusters)
        if tr:
            lines.append(f"\n关键仓库: {', '.join(f'`{r}`' for r in tr)}")
        lines.append("")

    if shown == 0:
        lines.append("_无多信号洞察。_\n")
    return lines


def _md_opportunities(opportunities: list, insights: list, clusters: list) -> list[str]:
    lines = ["## 机会", ""]
    if not opportunities:
        lines.append("_未发现机会。_\n"); return lines

    lines.append("| # | 标题 | 缺口 | 建议 |")
    lines.append("|---|------|------|------|")
    for i, op in enumerate(opportunities, 1):
        action = (op.recommended_action if hasattr(op, 'recommended_action') else op.get('recommended_action', ''))[:80]
        lines.append(f"| {i} | **{op.title}** | {op.gap_score:.2f} | {action} |")
    lines.append("")

    lines.append("## 机会详情\n")
    for i, op in enumerate(opportunities[:5], 1):
        lines.append(f"### {i}. {op.title}\n")
        lines.append(f"**痛点:** {op.pain_point}")
        action = op.recommended_action if hasattr(op, 'recommended_action') else op.get('recommended_action', '')
        lines.append(f"**建议:** {action}")

        src_ids = op.source_insights if hasattr(op, 'source_insights') else op.get('source_insights', [])
        all_actors: dict[str, int] = {}
        all_repos: list[str] = []
        for sid in src_ids:
            for ins in insights:
                iid = ins.id if hasattr(ins, 'id') else ins.get('id', '')
                if iid == sid:
                    ab, tr = _get_actor_repo_from_insight(ins, clusters)
                    for a, c in ab.items():
                        all_actors[a] = all_actors.get(a, 0) + c
                    all_repos.extend(tr)
                    break

        if all_actors:
            actor_parts = [f"{a} ({c} 条信号)" for a, c in sorted(all_actors.items(), key=lambda x: -x[1])]
            lines.append(f"**关联账号:** {', '.join(actor_parts)}")
        if all_repos:
            unique_repos = list(dict.fromkeys(all_repos))[:5]
            lines.append(f"**关键仓库:** {', '.join(f'`{r}`' for r in unique_repos)}")
        lines.append("")
    return lines
