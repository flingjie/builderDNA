"""CLI output renderer using Rich."""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def render(result: dict[str, Any]) -> None:
    """Render pipeline results to the terminal."""
    signals = result.get("signals", [])
    insights = result.get("insights", [])
    opportunities = result.get("opportunities", [])
    diff = result.get("diff")

    console.print()
    console.print(Panel.fit(
        Text("BuilderDNA Analysis", style="bold white on blue"),
        subtitle=f"Snapshot: {result.get('snapshot_id', 'unknown')}",
    ))

    if diff:
        _render_diff(diff)

    _render_signal_summary(signals)
    _render_insights(insights)
    _render_opportunities(opportunities)
    console.print()


def _render_diff(diff: dict) -> None:
    console.print()
    console.print(Text("Changes Since Last Run", style="bold yellow"))
    new_count = diff.get("new_signals", 0)
    total = diff.get("total_signals", 0)
    color = "green" if new_count > 0 else "yellow" if new_count == 0 else "red"
    console.print(f"  New signals: [{color}]{new_count:+d}[/{color}] (total: {total})")

    by_type = diff.get("signals_by_type", {})
    current = by_type.get("current", {})
    previous = by_type.get("previous", {})
    if current:
        type_table = Table(show_header=True, box=None, padding=(0, 2))
        type_table.add_column("Type"); type_table.add_column("Previous")
        type_table.add_column("Current"); type_table.add_column("Change")
        for stype in sorted(set(current) | set(previous)):
            prev = previous.get(stype, 0); curr = current.get(stype, 0)
            change = curr - prev
            change_str = f"[green]+{change}[/green]" if change > 0 else f"[red]{change}[/red]"
            type_table.add_row(stype, str(prev), str(curr), change_str)
        console.print(type_table)

    topic_changes = diff.get("topic_weight_changes", {})
    if topic_changes:
        console.print()
        console.print(Text("Topic Weight Changes:", style="bold"))
        for topic, data in sorted(topic_changes.items(), key=lambda x: abs(x[1]["change_pct"]), reverse=True)[:5]:
            pct = data["change_pct"]; arrow = "↑" if pct > 0 else "↓" if pct < 0 else "→"
            color = "green" if pct > 20 else "red" if pct < -20 else "yellow"
            console.print(f"  [{color}]{arrow} {topic}: {data['previous']:.1f} → {data['current']:.1f} ({pct:+.1f}%)[/{color}]")


def _render_signal_summary(signals: list) -> None:
    console.print()
    console.print(Text("Signal Summary", style="bold cyan"))
    if not signals:
        console.print("  No signals collected."); return
    by_type: dict[str, int] = {}
    for s in signals:
        by_type[s.type] = by_type.get(s.type, 0) + 1
    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Type"); table.add_column("Count"); table.add_column("Total Weight")
    for stype in sorted(by_type):
        total_w = sum(s.weight for s in signals if s.type == stype)
        table.add_row(stype, str(by_type[stype]), f"{total_w:.1f}")
    table.add_row("TOTAL", str(len(signals)), f"{sum(s.weight for s in signals):.1f}", style="bold")
    console.print(table)


def _render_insights(insights: list) -> None:
    console.print()
    console.print(Text("Insights", style="bold cyan"))
    if not insights:
        console.print("  No insights generated."); return
    for ins in insights[:10]:
        trend_color = {"rising": "green", "stable": "yellow", "fading": "red"}.get(ins.trend, "white")
        tags_str = ", ".join(ins.tags[:5])
        panel = Panel(
            f"{ins.summary}\n\nStrength: {ins.strength:.1f} | Trend: [{trend_color}]{ins.trend}[/{trend_color}] | Signals: {ins.signal_count}",
            title=f"[bold]{tags_str}[/bold]", border_style=trend_color,
        )
        console.print(panel)


def _render_opportunities(opportunities: list) -> None:
    console.print()
    console.print(Text("Opportunities (SSOT)", style="bold green"))
    if not opportunities:
        console.print("  No opportunities detected."); return
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#"); table.add_column("Title"); table.add_column("Demand")
    table.add_column("Comp."); table.add_column("Gap"); table.add_column("Action")
    for i, op in enumerate(opportunities[:10], 1):
        gap_color = "green" if op.gap_score >= 2.0 else "yellow" if op.gap_score >= 1.0 else "red"
        table.add_row(str(i), op.title, f"{op.demand_score:.1f}", f"{op.competition_score:.1f}",
                      f"[{gap_color}]{op.gap_score:.2f}[/{gap_color}]", op.recommended_action[:60])
    console.print(table)
