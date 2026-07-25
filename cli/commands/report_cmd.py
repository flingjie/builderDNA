"""report — render structured results to Markdown or JSON."""
import json
from pathlib import Path
from datetime import datetime

import typer

import time as _time

from observability import OutputLevel, vprint, record_command, record_output_retention


def _render_md(data: dict, output_path: Path, verbose: bool = False) -> str:
    """Render a structured result dict to Markdown."""
    payload = data.get("payload", data)
    stats = data.get("stats", {})
    lines = [
        f"# BuilderDNA Report\n",
        f"**Command:** {data.get('command', 'unknown')}",
        f"**Domain:** {data.get('domain', '')}",
        f"**Generated:** {datetime.now().isoformat()}\n",
    ]

    # Stats summary (if present)
    if stats:
        stat_items = []
        for key in ("total_signals", "total_trends", "total", "clusters",
                     "repos", "issues", "elapsed_seconds", "errors", "warnings"):
            if key in stats:
                val = stats[key]
                if isinstance(val, float):
                    val = f"{val:.1f}"
                stat_items.append(f"{key}={val}")
        if stat_items:
            lines.append(f"**Stats:** {', '.join(stat_items)}\n")

    # Trends section
    trends = payload.get("trends", [])
    if trends:
        lines.append("## Trends\n")
        lines.append("| Topic | Stage | Velocity | Evidence | Classification |")
        lines.append("|-------|-------|----------|----------|----------------|")
        for t in trends:
            reason = t.get('classification_reason', '') if verbose else ''
            lines.append(f"| {t.get('topic', '')} | {t.get('stage', '')} | {t.get('growth_velocity', 0):.1f} | {t.get('evidence_count', 0)} | {reason} |")
        lines.append("")

        # Verbose: detailed trend breakdown
        if verbose:
            for t in trends:
                lines.append(f"### {t.get('topic', '')} — {t.get('stage', '')}")
                lines.append(f"- **Reason:** {t.get('classification_reason', 'N/A')}")
                lines.append(f"- Confidence: {t.get('confidence', 0):.2f}")
                lines.append(f"- Acceleration: {t.get('acceleration', 0):.2f}")
                lines.append(f"- Growth Velocity: {t.get('growth_velocity', 0):.2f}")
                top_repos = t.get('top_repos', [])
                if top_repos:
                    lines.append(f"- Top Repos: {', '.join(r.get('full_name', '') for r in top_repos[:3])}")
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

        # Noise info
        if stats.get("noise_count"):
            lines.append(f"*{stats['noise_count']} issues classified as noise (excluded from clusters)*\n")

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

            # Verbose: scoring breakdown
            if verbose:
                bd = o.get("scoring_breakdown", {})
                if bd:
                    lines.append(f"- **Scoring Breakdown:**")
                    lines.append(f"  - Velocity contribution: {bd.get('velocity_contribution', '?')}")
                    lines.append(f"  - Severity contribution: {bd.get('severity_contribution', '?')}")
                    lines.append(f"  - Frequency contribution: {bd.get('frequency_contribution', '?')}")
                    lines.append(f"  - Formula: {bd.get('gap_formula', '?')}")
                if o.get("personalized_score") is not None:
                    lines.append(f"- Personalized Score: {o.get('personalized_score', 0):.1f} "
                               f"(multiplier: {o.get('alignment_multiplier', 0):.2f})")
                    lines.append(f"- Alignment: {o.get('alignment_reason', '')}")

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
    from observability import get_output_level
    verbose = get_output_level().value >= OutputLevel.VERBOSE.value
    t0 = _time.time()

    data_path = Path(data)
    if not data_path.exists():
        vprint(f"[red]Input file not found: {data}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")

    if fmt == "json":
        out = Path(output_dir) / f"report-{ts}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    else:
        out = Path(output_dir) / f"report-{ts}.md"
        _render_md(raw, out, verbose=verbose)

    vprint(f"[green]Report → {out}[/green]", level=OutputLevel.NORMAL)

    # Behavior tracking
    elapsed = round(_time.time() - t0, 2)
    record_command(
        command="report",
        domain=raw.get("domain", ""),
        flags={"format": fmt, "output_dir": output_dir},
        output_path=str(out),
        user_dna_used=False,
        elapsed_seconds=elapsed,
        status="success",
    )
    record_output_retention(str(out))
