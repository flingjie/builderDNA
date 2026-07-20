"""Markdown report generator — Chinese labels with source attribution."""

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


def write_markdown(result: dict[str, Any], output_dir: str | Path) -> Path:
    """Write a Chinese Markdown report with full source attribution."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_id = result.get("snapshot_id", "unknown")
    filepath = output_dir / f"report-{ts}-{snapshot_id}.md"

    signals = result.get("signals", [])
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
    lines += _md_pipeline_summary(signals, insights, opportunities, result)
    lines += _md_signal_summary(signals)
    lines += _md_insights(insights, clusters)
    lines += _md_opportunities(opportunities, insights, clusters)

    filepath.write_text("\n".join(lines))
    return filepath


def _md_diff(diff: dict) -> list[str]:
    lines = ["## 变化摘要 (较上次运行)", ""]
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


def _md_pipeline_summary(signals: list, insights: list, opportunities: list, result: dict) -> list[str]:
    lines = ["## 执行摘要", ""]
    accounts = result.get("signals", [])
    actors = sorted(set(s.actor for s in accounts)) if accounts else []

    lines.append("| 阶段 | 输入 | 输出 | 说明 |")
    lines.append("|------|------|------|------|")
    lines.append(f"| 采集 | {', '.join(actors) if actors else '-'} | {len(signals)} 条信号 | 从 GitHub API 拉取 repos/stars/commits |")
    lines.append(f"| 理解 | {len(signals)} 条信号 | {len(insights)} 个洞察 | 规则聚类 + LLM 语义分类 |")
    lines.append(f"| 推荐 | {len(insights)} 个洞察 | {len(opportunities)} 个机会 | LLM 发现 + 缺口评分排序 |")
    lines.append("")
    return lines


def _md_signal_summary(signals: list) -> list[str]:
    lines = ["## 信号汇总", ""]
    if not signals:
        lines.append("_未采集到信号。_\n"); return lines

    by_type: dict[str, dict] = {}
    by_actor: dict[str, dict] = {}
    for s in signals:
        if s.type not in by_type:
            by_type[s.type] = {"count": 0, "weight": 0.0}
        by_type[s.type]["count"] += 1
        by_type[s.type]["weight"] += s.weight

        if s.actor not in by_actor:
            by_actor[s.actor] = {}
        if s.type not in by_actor[s.actor]:
            by_actor[s.actor][s.type] = 0
        by_actor[s.actor][s.type] += 1

    lines.append("| 类型 | 数量 | 总权重 |")
    lines.append("|------|------|--------|")
    tc, tw = 0, 0.0
    for stype in sorted(by_type):
        d = by_type[stype]
        tc += d["count"]
        tw += d["weight"]
        lines.append(f"| {stype} | {d['count']} | {d['weight']:.1f} |")
    lines.append(f"| **合计** | **{tc}** | **{tw:.1f}** |")
    lines.append("")

    # Per-actor breakdown
    if len(by_actor) > 1:
        lines.append("### 按账号分布\n")
        all_types = sorted(by_type.keys())
        header = "| 账号 | " + " | ".join(all_types) + " | 总信号数 | 总权重 |"
        lines.append(header)
        sep = "|------|" + "|".join(["------" for _ in all_types]) + "|----------|--------|"
        lines.append(sep)
        for actor in sorted(by_actor):
            cols = [actor]
            total_count = 0
            total_weight = 0.0
            for t in all_types:
                c = by_actor[actor].get(t, 0)
                cols.append(str(c))
                total_count += c
                total_weight += c * {"repo": 5.0, "commit": 3.0, "star": 1.0}.get(t, 0)
            cols.append(str(total_count))
            cols.append(f"{total_weight:.1f}")
            lines.append("| " + " | ".join(cols) + " |")
        lines.append("")

    return lines


def _md_insights(insights: list, clusters: list) -> list[str]:
    lines = ["## 洞察", ""]
    if not insights:
        lines.append("_未生成洞察。_\n"); return lines

    for ins in insights:
        trend_emoji = {"rising": "🔺", "stable": "🟡", "fading": "🔻"}.get(ins.trend, "")
        trend_cn = {"rising": "上升", "stable": "稳定", "fading": "下降"}.get(ins.trend, ins.trend)
        tags = ins.tags if hasattr(ins, 'tags') else ins.get('tags', [])
        lines.append(f"### {', '.join(tags[:5])} {trend_emoji}\n")
        lines.append(f"- **摘要:** {ins.summary}")
        lines.append(f"- **强度:** {ins.strength:.1f} | **趋势:** {trend_cn} | **信号数:** {ins.signal_count}")

        # Source attribution
        ab, tr = _get_actor_repo_from_insight(ins, clusters)
        if ab:
            actor_parts = [f"{a} ({c} 条信号)" for a, c in sorted(ab.items(), key=lambda x: -x[1])]
            lines.append(f"- **来源账号:** {', '.join(actor_parts)}")
        if tr:
            lines.append(f"- **关键仓库:** {', '.join(f'`{r}`' for r in tr)}")

        ev = ins.evidence if hasattr(ins, 'evidence') else ins.get('evidence', [])
        if ev:
            lines.append(f"- **支撑证据:** {', '.join(str(e) for e in ev[:5])}")
        lines.append("")
    return lines


def _md_opportunities(opportunities: list, insights: list, clusters: list) -> list[str]:
    lines = ["## 机会 (SSOT)", ""]
    if not opportunities:
        lines.append("_未发现机会。_\n"); return lines

    lines.append("| # | 标题 | 需求 | 竞争 | 缺口 | 建议 |")
    lines.append("|---|------|------|------|------|------|")
    for i, op in enumerate(opportunities, 1):
        action = (op.recommended_action if hasattr(op, 'recommended_action') else op.get('recommended_action', ''))[:60]
        lines.append(f"| {i} | **{op.title}** | {op.demand_score:.1f} | {op.competition_score:.1f} | {op.gap_score:.2f} | {action} |")
    lines.append("")

    lines.append("## 机会详情\n")
    for i, op in enumerate(opportunities[:5], 1):
        lines.append(f"### {i}. {op.title}\n")
        lines.append(f"- **痛点:** {op.pain_point}")
        lines.append(f"- **缺口评分:** {op.gap_score:.2f}")
        action = op.recommended_action if hasattr(op, 'recommended_action') else op.get('recommended_action', '')
        lines.append(f"- **建议行动:** {action}")

        # Source attribution: walk source_insights → insight → cluster
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
            lines.append(f"- **关联账号:** {', '.join(actor_parts)}")
        if all_repos:
            unique_repos = list(dict.fromkeys(all_repos))[:5]
            lines.append(f"- **关键仓库:** {', '.join(f'`{r}`' for r in unique_repos)}")
        lines.append("")
    return lines
