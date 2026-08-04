"""observability check — run self-iteration diagnostics: mismatch detection,
snapshot comparison, and hypothesis pruning."""

import json
import time as _time
from pathlib import Path

import typer

from observability import OutputLevel, vprint, record_command
from observability.behavior import detect_mismatches, save_mismatch_report
from observability.snapshot import compare_snapshots
from observability.hypothesis import HypothesisManager


def observability(
    domain: str = typer.Option("agent", "--domain", "-d", help="Domain to check (for snapshots)"),
    check_mismatches: bool = typer.Option(False, "--mismatches", help="Run behavior mismatch detection"),
    check_snapshots: bool = typer.Option(False, "--snapshots", help="Compare prediction snapshots against new data"),
    prune_hypotheses: bool = typer.Option(False, "--prune", help="Check all hypotheses for pruning eligibility"),
    all_checks: bool = typer.Option(False, "--all", help="Run all checks"),
) -> None:
    """Run self-iteration diagnostics to detect drifts and validate predictions."""
    t0 = _time.time()
    results: dict = {"domain": domain, "checks": {}}

    if all_checks:
        check_mismatches = check_snapshots = prune_hypotheses = True

    if not any([check_mismatches, check_snapshots, prune_hypotheses]):
        vprint("[yellow]Specify one or more checks: --mismatches, --snapshots, --prune, or --all[/yellow]",
               level=OutputLevel.NORMAL)
        return

    if check_mismatches:
        vprint("[bold]Running mismatch detection...[/bold]", level=OutputLevel.NORMAL)
        mismatches = detect_mismatches()
        results["checks"]["mismatches"] = {
            "count": len(mismatches),
            "mismatches": mismatches,
        }
        if mismatches:
            report_path = save_mismatch_report(mismatches)
            if report_path:
                results["checks"]["mismatches"]["report"] = report_path
                vprint(f"  Mismatch report saved to {report_path}", level=OutputLevel.NORMAL)
        else:
            vprint("  No mismatches detected.", level=OutputLevel.NORMAL)

    if check_snapshots:
        vprint(f"[bold]Comparing prediction snapshots for {domain}...[/bold]", level=OutputLevel.NORMAL)
        comparisons = compare_snapshots(domain)
        results["checks"]["snapshots"] = {
            "count": len(comparisons),
            "comparisons": comparisons,
        }
        vprint(f"  {len(comparisons)} snapshot comparisons completed.", level=OutputLevel.NORMAL)

    if prune_hypotheses:
        vprint("[bold]Checking hypothesis pruning eligibility...[/bold]", level=OutputLevel.NORMAL)
        manager = HypothesisManager()
        pruning_results = manager.check_all_pruning()
        results["checks"]["hypotheses"] = {
            "checked": len(pruning_results),
            "results": pruning_results,
        }
        prunable = [r for r in pruning_results if r.get("severity") == "high"]
        vprint(f"  {len(pruning_results)} checked, {len(prunable)} eligible for pruning.", level=OutputLevel.NORMAL)

    elapsed = _time.time() - t0
    results["elapsed_ms"] = round(elapsed * 1000)

    # Write results for downstream consumption
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"observability_check_{domain}.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    vprint(f"\nResults written to {out_file}", level=OutputLevel.NORMAL)

    record_command("observability", domain=domain, flags={
        "mismatches": check_mismatches,
        "snapshots": check_snapshots,
        "prune": prune_hypotheses,
    }, elapsed_seconds=round(elapsed, 3))
