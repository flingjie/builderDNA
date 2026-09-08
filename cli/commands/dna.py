"""dna — compute an evidence-backed DeveloperDNA from collected signals.

Reads a collect output (``output/signals.json``) and derives deterministic,
evidence-cited judgments about a developer's technical practices. Semantic
induction (what a pattern means) is left to the builderdna Skill.
"""
from pathlib import Path

import typer

from models.payload import (
    SandboxResult,
    DeveloperDNA,
    Diagnostics,
    ConfidenceDiag,
)
from intelligence.developer_dna import compute_developer_dna
from observability import RunTelemetry, OutputLevel, vprint, record_command, record_output_retention


def dna(
    data: str = typer.Option(..., "--data", "-d", help="Input signals JSON (collect output)"),
    developer: str = typer.Option(..., "--developer", help="Developer/org login to analyze"),
    output: str = typer.Option("output/developer_dna.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Compute an evidence-backed DeveloperDNA from collected signals."""
    tel = RunTelemetry()
    data_path = Path(data)
    if not data_path.exists():
        vprint(f"[red]Signals file not found: {data}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    import json

    raw = json.loads(data_path.read_text(encoding="utf-8"))
    payload = raw.get("payload", raw)

    repos = payload.get("repos", [])
    issues = payload.get("issues", [])
    if isinstance(repos[0], dict) and "full_name" not in repos[0] and "signals" in payload:
        # Fall back to the normalized Signal list if flat repos are absent.
        repos = []
        for s in payload.get("signals", []):
            if s.get("type") == "repo_created":
                repos.append(s.get("payload", {}))

    result_dna = compute_developer_dna(developer, repos, issues)

    diag = Diagnostics()
    for d in result_dna.dimensions:
        if d.status == "unknown":
            diag.data_quality.coverage_gaps.append(
                f"{d.dimension}: {d.summary}"
            )

    result = SandboxResult(
        command="dna",
        domain=developer,
        payload=result_dna.model_dump(),
        stats={
            "repos": len(result_dna.source_repos),
            "issues": result_dna.source_issues,
            "observed": sum(1 for d in result_dna.dimensions if d.status == "observed"),
            "inferred": sum(1 for d in result_dna.dimensions if d.status == "inferred"),
            "unknown": sum(1 for d in result_dna.dimensions if d.status == "unknown"),
            **tel.to_stats(),
        },
        diagnostics=diag,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    vprint(f"[green]DeveloperDNA for {developer} → {output}[/green]", level=OutputLevel.NORMAL)
    for d in result_dna.dimensions:
        vprint(f"  [{d.status:9s}] {d.dimension}: {d.summary}", level=OutputLevel.NORMAL)

    record_command(
        command="dna",
        domain=developer,
        flags={"data": data},
        output_path=output,
        user_dna_used=False,
        elapsed_seconds=tel.elapsed_seconds,
        status="success",
    )
    record_output_retention(output)
