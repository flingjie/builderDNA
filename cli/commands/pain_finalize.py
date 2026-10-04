"""pain-finalize — validate confirmed groupings and emit final pain clusters.

Second stage of the two-stage pain pipeline. Reads candidate groups from the
``pain`` command, applies an optional Agent-written confirmation file, and emits
the final ``PainPayload`` consumed by ``opportunity`` / ``report``.

- With ``--confirmations``: resolves every ``issue_key`` against the candidate
  set (unknown refs abort, duplicates are skipped with a warning), then computes
  severity / frequency / cross-repo reach / recurrence span per confirmed cluster.
- Without ``--confirmations``: deterministic fallback — each candidate group is
  promoted to a cluster with a ``title_hint`` label.
"""

import json
from pathlib import Path

import typer

from intelligence.pain.summarize import summarize_cluster, title_hint
from models.payload import (
    SandboxResult, CandidateGroupsPayload, PainPayload, Diagnostics,
)
from observability import RunTelemetry, OutputLevel, vprint, record_command, record_output_retention
from observability.snapshot import save_pain_snapshot
from observability.versions import algorithm_version


def _load_candidates(path: Path) -> CandidateGroupsPayload:
    raw = json.loads(path.read_text())
    payload = raw.get("payload", raw)
    return CandidateGroupsPayload.model_validate(payload)


def _load_confirmations(path: Path) -> list[dict]:
    """Parse the Agent-written confirmation file.

    Accepted shapes: ``{"clusters": [{"title", "issue_keys", "rationale"}]}`` or
    a bare ``[...]`` list. Returns a list of cluster specs.
    """
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        return raw.get("clusters", [])
    if isinstance(raw, list):
        return raw
    return []


def _deterministic_clusters(cand: CandidateGroupsPayload) -> list[tuple[str, list]]:
    """Promote each candidate group to a ``(title, members)`` cluster."""
    return [(title_hint(g), g.issues) for g in cand.groups]


def pain_finalize(
    domain: str = typer.Argument(..., help="Domain name"),
    candidates: str = typer.Option("output/pain_candidates.json", "--candidates", help="Candidate groups JSON (from the pain command)"),
    confirmations: str = typer.Option(None, "--confirmations", help="Agent-written confirmation JSON (optional)"),
    output: str = typer.Option("output/pain_clusters.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Finalize candidate groups into pain clusters (validating issue references)."""
    tel = RunTelemetry()

    candidates_path = Path(candidates)
    if not candidates_path.exists():
        vprint(f"[red]Candidates file not found: {candidates}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    cand = _load_candidates(candidates_path)

    # issue_key → candidate, spanning grouped + noise (for fallback review).
    by_key = {c.issue_key: c for g in cand.groups for c in g.issues}
    by_key.update({c.issue_key: c for c in cand.noise})

    diag = Diagnostics()

    if confirmations and Path(confirmations).exists():
        specs = _load_confirmations(Path(confirmations))
        seen: set[str] = set()
        final: list[tuple[str, list]] = []
        for i, spec in enumerate(specs):
            title = spec.get("title") or f"Pain Cluster {i}"
            resolved = []
            for key in spec.get("issue_keys", []):
                if key not in by_key:
                    vprint(f"[red]Unknown issue_key {key!r} in confirmation cluster {i}.[/red]",
                           level=OutputLevel.QUIET)
                    raise typer.Exit(1)
                if key in seen:
                    vprint(f"[yellow]Duplicate issue_key {key!r} — skipping repeat.[/yellow]",
                           level=OutputLevel.NORMAL)
                    continue
                seen.add(key)
                resolved.append(by_key[key])
            if resolved:
                final.append((title, resolved))
    else:
        final = _deterministic_clusters(cand)

    clusters = [
        summarize_cluster(resolved, cluster_id=idx, title=title)
        for idx, (title, resolved) in enumerate(final)
    ]
    clusters.sort(key=lambda c: c.severity, reverse=True)
    for idx, c in enumerate(clusters):
        c.cluster_id = idx

    for c in clusters:
        if c.frequency == 1:
            diag.confidence.low_confidence_items.append({
                "item": f"Cluster {c.cluster_id}: {c.title}",
                "confidence": 0.1,
                "reason": "single-issue cluster — not a real pain pattern",
            })
        if c.severity < 0.3:
            diag.confidence.low_confidence_items.append({
                "item": f"Cluster {c.cluster_id}: {c.title}",
                "confidence": round(c.severity, 2),
                "reason": f"severity={c.severity:.2f} — low engagement, may not represent real pain",
            })

    result = SandboxResult(
        command="pain-finalize",
        domain=domain,
        payload=PainPayload(
            clusters=clusters,
            issue_count=cand.issue_count,
            repos_analyzed=cand.repos_analyzed,
        ).model_dump(),
        stats={"clusters": len(clusters), "issues_analyzed": cand.issue_count,
               "noise_count": cand.noise_count, "algorithm_version": algorithm_version("pain"),
               **tel.to_stats()},
        diagnostics=diag,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2))
    vprint(f"[green]{len(clusters)} pain clusters → {output}[/green]", level=OutputLevel.NORMAL)

    cluster_dicts = [c.model_dump() for c in clusters]
    record_command(
        command="pain-finalize",
        domain=domain,
        flags={"candidates": candidates, "confirmations": confirmations},
        output_path=output,
        user_dna_used=False,
        elapsed_seconds=tel.elapsed_seconds,
        status="success",
    )
    record_output_retention(output)
    save_pain_snapshot(domain=domain, clusters=cluster_dicts,
                       issue_count=cand.issue_count, noise_count=cand.noise_count)
