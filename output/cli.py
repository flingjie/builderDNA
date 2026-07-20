"""CLI output renderer using Rich — Chinese labels with source attribution."""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

TREND_COLORS = {"rising": "green", "stable": "yellow", "fading": "red"}
TREND_CN = {"rising": "上升", "stable": "稳定", "fading": "下降"}
WEIGHTS = {"repo": 5.0, "commit": 3.0, "star": 1.0}


def _find_cluster(clusters: list, cluster_id: str):
    """Find a cluster by ID from the in-memory list (supports both model objects and dicts)."""
    for c in clusters:
        cid = c.id if hasattr(c, 'id') else c.get('id', '')
        if cid == cluster_id:
            return c
    return None


def _get_attr(obj, name: str, default=None):
    """Get attribute from either pydantic model or dict."""
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _insight_source(insight, clusters: list) -> tuple[dict, list]:
    """Walk insight → cluster → actor_breakdown + top_repos."""
    cid = _get_attr(insight, 'source_cluster_id', '')
    c = _find_cluster(clusters, cid)
    if c is None:
        return {}, []
    ab = _get_attr(c, 'actor_breakdown', {})
    tr = _get_attr(c, 'top_repos', [])
    return ab, tr


def render(result: dict[str, Any]) -> None:
    """Render pipeline results to the terminal."""
    signals = result.get("signals", [])
    clusters = result.get("clusters", [])
    insights = result.get("insights", [])
    opportunities = result.get("opportunities", [])
    diff = result.get("diff")

    console.print()
    console.print(Panel.fit(
        Text("BuilderDNA 分析", style="bold white on blue"),
        subtitle=f"快照: {result.get('snapshot_id', 'unknown')}",
    ))

    if diff:
        _render_diff(diff)

    _render_pipeline_summary(signals, insights, opportunities, result)
    _render_signal_summary(signals)
    _render_insights(insights, clusters)
    _render_opportunities(opportunities, insights, clusters)
    console.print()


def _render_diff(diff: dict) -> None:
    console.print()
    console.print(Text("变化摘要 (较上次运行)", style="bold yellow"))
    new_count = diff.get("new_signals", 0)
    total = diff.get("total_signals", 0)
    color = "green" if new_count > 0 else "yellow" if new_count == 0 else "red"
    console.print(f"  新增信号: [{color}]{new_count:+d}[/{color}] (总计: {total})")

    by_type = diff.get("signals_by_type", {})
    current = by_type.get("current", {})
    previous = by_type.get("previous", {})
    if current:
        type_table = Table(show_header=True, box=None, padding=(0, 2))
        type_table.add_column("类型"); type_table.add_column("上次")
        type_table.add_column("本次"); type_table.add_column("变化")
        for stype in sorted(set(current) | set(previous)):
            prev = previous.get(stype, 0); curr = current.get(stype, 0)
            change = curr - prev
            change_str = f"[green]+{change}[/green]" if change > 0 else f"[red]{change}[/red]"
            type_table.add_row(stype, str(prev), str(curr), change_str)
        console.print(type_table)

    topic_changes = diff.get("topic_weight_changes", {})
    if topic_changes:
        console.print()
        console.print(Text("话题权重变化:", style="bold"))
        for topic, data in sorted(topic_changes.items(), key=lambda x: abs(x[1]["change_pct"]), reverse=True)[:5]:
            pct = data["change_pct"]; arrow = "↑" if pct > 0 else "↓" if pct < 0 else "→"
            color = "green" if pct > 20 else "red" if pct < -20 else "yellow"
            console.print(f"  [{color}]{arrow} {topic}: {data['previous']:.1f} → {data['current']:.1f} ({pct:+.1f}%)[/{color}]")


def _render_pipeline_summary(signals: list, insights: list, opportunities: list, result: dict) -> None:
    console.print()
    console.print(Text("执行摘要", style="bold cyan"))
    actors = sorted(set(s.actor for s in signals)) if signals else []
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("阶段"); table.add_column("输入"); table.add_column("输出"); table.add_column("说明")
    table.add_row("采集", ", ".join(actors) if actors else "-", f"{len(signals)} 条信号",
                  "GitHub API: repos, stars, commits")
    table.add_row("理解", f"{len(signals)} 条信号", f"{len(insights)} 个洞察",
                  "规则聚类 → LLM 语义分类")
    table.add_row("推荐", f"{len(insights)} 个洞察", f"{len(opportunities)} 个机会",
                  "LLM 发现 → 缺口评分排序")
    console.print(table)


def _render_signal_summary(signals: list) -> None:
    console.print()
    console.print(Text("信号汇总", style="bold cyan"))
    if not signals:
        console.print("  未采集到信号。"); return

    by_type: dict[str, int] = {}
    by_actor: dict[str, dict] = {}
    for s in signals:
        by_type[s.type] = by_type.get(s.type, 0) + 1
        if s.actor not in by_actor:
            by_actor[s.actor] = {}
        by_actor[s.actor][s.type] = by_actor[s.actor].get(s.type, 0) + 1

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("类型"); table.add_column("数量"); table.add_column("总权重")
    for stype in sorted(by_type):
        total_w = sum(s.weight for s in signals if s.type == stype)
        table.add_row(stype, str(by_type[stype]), f"{total_w:.1f}")
    table.add_row("合计", str(len(signals)), f"{sum(s.weight for s in signals):.1f}", style="bold")
    console.print(table)

    # Per-actor breakdown
    if len(by_actor) > 1:
        console.print()
        console.print(Text("按账号分布", style="bold"))
        all_types = sorted(by_type.keys())
        atable = Table(show_header=True, box=None, padding=(0, 1))
        atable.add_column("账号")
        for t in all_types:
            atable.add_column(t)
        atable.add_column("总信号数")
        atable.add_column("总权重")
        for actor in sorted(by_actor):
            row = [actor]
            total_count = 0
            total_weight = 0.0
            for t in all_types:
                c = by_actor[actor].get(t, 0)
                row.append(str(c))
                total_count += c
                total_weight += c * WEIGHTS.get(t, 0)
            row.append(str(total_count))
            row.append(f"{total_weight:.1f}")
            atable.add_row(*row)
        console.print(atable)


def _render_insights(insights: list, clusters: list) -> None:
    console.print()
    console.print(Text("洞察", style="bold cyan"))
    if not insights:
        console.print("  未生成洞察。"); return

    for ins in insights[:10]:
        trend = _get_attr(ins, 'trend', 'stable')
        trend_color = TREND_COLORS.get(trend, "white")
        trend_cn = TREND_CN.get(trend, trend)
        tags = _get_attr(ins, 'tags', [])
        tags_str = ", ".join(tags[:5])

        # Source lines
        source_lines = []
        ab, tr = _insight_source(ins, clusters)
        if ab:
            actor_parts = [f"{a}({c})" for a, c in sorted(ab.items(), key=lambda x: -x[1])]
            source_lines.append(f"来源账号: {', '.join(actor_parts)}")
        if tr:
            source_lines.append(f"关键仓库: {', '.join(tr[:5])}")

        source_text = "\n" + "\n".join(source_lines) if source_lines else ""

        panel = Panel(
            f"{_get_attr(ins, 'summary', '')}\n\n"
            f"强度: {_get_attr(ins, 'strength', 0):.1f} | 趋势: [{trend_color}]{trend_cn}[/{trend_color}] | "
            f"信号数: {_get_attr(ins, 'signal_count', 0)}{source_text}",
            title=f"[bold]{tags_str}[/bold]", border_style=trend_color,
        )
        console.print(panel)


def _render_opportunities(opportunities: list, insights: list, clusters: list) -> None:
    console.print()
    console.print(Text("机会 (SSOT)", style="bold green"))
    if not opportunities:
        console.print("  未发现机会。"); return

    # Summary table
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#"); table.add_column("标题"); table.add_column("需求")
    table.add_column("竞争"); table.add_column("缺口"); table.add_column("建议")
    for i, op in enumerate(opportunities[:10], 1):
        gap = _get_attr(op, 'gap_score', 0)
        gap_color = "green" if gap >= 2.0 else "yellow" if gap >= 1.0 else "red"
        action = _get_attr(op, 'recommended_action', '')[:50]
        table.add_row(
            str(i), _get_attr(op, 'title', ''),
            f"{_get_attr(op, 'demand_score', 0):.1f}",
            f"{_get_attr(op, 'competition_score', 0):.1f}",
            f"[{gap_color}]{gap:.2f}[/{gap_color}]", action,
        )
    console.print(table)

    # Detail with source attribution
    console.print()
    console.print(Text("机会详情", style="bold green"))
    for i, op in enumerate(opportunities[:5], 1):
        # Resolve source via insights
        src_ids = _get_attr(op, 'source_insights', [])
        all_actors: dict[str, int] = {}
        all_repos: list[str] = []
        for sid in src_ids:
            for ins in insights:
                if _get_attr(ins, 'id', '') == sid:
                    ab, tr = _insight_source(ins, clusters)
                    for a, c in ab.items():
                        all_actors[a] = all_actors.get(a, 0) + c
                    all_repos.extend(tr)
                    break

        parts = [
            f"[bold]#{i} {_get_attr(op, 'title', '')}[/bold]",
            f"  痛点: {_get_attr(op, 'pain_point', '')}",
            f"  缺口评分: {_get_attr(op, 'gap_score', 0):.2f}",
            f"  建议: {_get_attr(op, 'recommended_action', '')}",
        ]
        if all_actors:
            actor_str = ", ".join(f"{a}({c})" for a, c in sorted(all_actors.items(), key=lambda x: -x[1]))
            parts.append(f"  关联账号: {actor_str}")
        if all_repos:
            parts.append(f"  关键仓库: {', '.join(dict.fromkeys(all_repos))}")
        console.print("\n".join(parts))
        console.print()
