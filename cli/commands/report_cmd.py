"""report — render structured results to Markdown or JSON."""
import json
from pathlib import Path
from datetime import datetime

import typer
from rich.console import Console

console = Console()


def _render_md(data: dict, output_path: Path) -> str:
    """Render a structured result dict to Markdown."""
    payload = data.get("payload", data)
    lines = [
        f"# BuilderDNA Report\n",
        f"**Command:** {data.get('command', 'unknown')}",
        f"**Domain:** {data.get('domain', '')}",
        f"**Generated:** {datetime.now().isoformat()}\n",
    ]

    # Trends section
    trends = payload.get("trends", [])
    if trends:
        lines.append("## Trends\n")
        lines.append("| Topic | Stage | Velocity | Evidence |")
        lines.append("|-------|-------|----------|----------|")
        for t in trends:
            lines.append(f"| {t.get('topic', '')} | {t.get('stage', '')} | {t.get('growth_velocity', 0):.1f} | {t.get('evidence_count', 0)} |")
        lines.append("")

    # Pain clusters
    clusters = payload.get("clusters", [])
    if clusters:
        lines.append("## Pain Points\n")
        for c in clusters:
            lines.append(f"### {c.get('title', '')}")
            lines.append(f"- Severity: {c.get('severity', 0):.1f}")
            lines.append(f"- Frequency: {c.get('frequency', 0)} issues")
            lines.append(f"- Affected: {', '.join(c.get('affected_repos', []))}")
            lines.append("")

    # Opportunities
    opps = payload.get("opportunities", [])
    if opps:
        lines.append("## Opportunities\n")
        for i, o in enumerate(opps, 1):
            lines.append(f"### {i}. {o.get('title', '')}")
            lines.append(f"- **Gap Score:** {o.get('gap_score', 0):.1f}")
            lines.append(f"- Demand: {o.get('demand_score', 0):.1f} / Competition: {o.get('competition_score', 0):.1f}")
            lines.append(f"- Action: {o.get('recommended_action', '')}")
            signals = o.get("signals", [])
            if signals:
                lines.append(f"- Signals: {'; '.join(signals[:3])}")
            lines.append("")

    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    return str(output_path)


def report(
    data: str = typer.Option(..., "--data", "-d", help="Input result JSON"),
    fmt: str = typer.Option("md", "--format", "-f", help="Output format: md or json"),
    output_dir: str = typer.Option("./output", "--output-dir", "-o", help="Output directory"),
) -> None:
    """Render structured results to a report."""
    data_path = Path(data)
    if not data_path.exists():
        console.print(f"[red]Input file not found: {data}[/red]")
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")

    if fmt == "json":
        out = Path(output_dir) / f"report-{ts}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    else:
        out = Path(output_dir) / f"report-{ts}.md"
        _render_md(raw, out)

    console.print(f"[green]Report → {out}[/green]")
