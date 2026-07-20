"""CLI output renderer using Rich — simplified Chinese output."""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def _find_cluster(clusters: list, cluster_id: str):
    for c in clusters:
        cid = c.id if hasattr(c, 'id') else c.get('id', '')
        if cid == cluster_id:
            return c
    return None


def _get_attr(obj, name: str, default=None):
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _sc(insight) -> int:
    return _get_attr(insight, 'signal_count', 0)


def _insight_source(insight, clusters: list) -> tuple[dict, list]:
    cid = _get_attr(insight, 'source_cluster_id', '')
    c = _find_cluster(clusters, cid)
    if c is None:
        return {}, []
    return _get_attr(c, 'actor_breakdown', {}), _get_attr(c, 'top_repos', [])


def render(result: dict[str, Any]) -> None:
    """Render pipeline results to the terminal."""
    clusters = result.get("clusters", [])
    insights = result.get("insights", [])
    opportunities = result.get("opportunities", [])

    console.print()
    console.print(Panel.fit(
        Text("BuilderDNA 分析", style="bold white on blue"),
        subtitle=f"快照: {result.get('snapshot_id', 'unknown')}",
    ))

    _render_insights(insights, clusters)
    _render_opportunities(opportunities, insights, clusters)
    console.print()


def _render_insights(insights: list, clusters: list) -> None:
    console.print()
    console.print(Text("技术洞察", style="bold cyan"))
    if not insights:
        console.print("  未生成洞察。"); return

    shown = 0
    for ins in insights:
        if _sc(ins) <= 1:
            continue
        shown += 1
        tags = _get_attr(ins, 'tags', [])
        tags_str = ", ".join(tags[:5])
        summary = _get_attr(ins, 'summary', '')
        _, tr = _insight_source(ins, clusters)
        repo_str = f"\n关键仓库: {', '.join(tr[:5])}" if tr else ""
        panel = Panel(f"{summary}{repo_str}", title=f"[bold]{tags_str}[/bold]")
        console.print(panel)

    if shown == 0:
        console.print("  无多信号洞察。")


def _render_opportunities(opportunities: list, insights: list, clusters: list) -> None:
    console.print()
    console.print(Text("机会", style="bold green"))
    if not opportunities:
        console.print("  未发现机会。"); return

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#"); table.add_column("标题"); table.add_column("缺口"); table.add_column("建议")
    for i, op in enumerate(opportunities[:10], 1):
        gap = _get_attr(op, 'gap_score', 0)
        gap_color = "green" if gap >= 2.0 else "yellow" if gap >= 1.0 else "red"
        action = _get_attr(op, 'recommended_action', '')[:60]
        table.add_row(str(i), _get_attr(op, 'title', ''),
                      f"[{gap_color}]{gap:.2f}[/{gap_color}]", action)
    console.print(table)

    console.print()
    console.print(Text("机会详情", style="bold green"))
    for i, op in enumerate(opportunities[:5], 1):
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
            f"  建议: {_get_attr(op, 'recommended_action', '')}",
        ]
        if all_actors:
            parts.append(f"  关联账号: {', '.join(f'{a}({c})' for a, c in sorted(all_actors.items(), key=lambda x: -x[1]))}")
        if all_repos:
            parts.append(f"  关键仓库: {', '.join(dict.fromkeys(all_repos))}")
        console.print("\n".join(parts))
        console.print()
