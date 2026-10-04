"""pain — clean, dedupe, and group issue signals into candidate pain groups.

This is the first stage of the two-stage pain pipeline. It produces
``CandidateGroupsPayload`` (lexical recall only — text similarity is a hint,
not proof of the same pain point). The skill's Agent confirmation step and the
``pain-finalize`` command turn these candidates into final ``PainCluster``s.

Default backend is ``tfidf`` (offline, deterministic). ``embedding`` is an
optional backend (local Ollama) that degrades to ``tfidf`` on failure instead
of returning empty results.
"""

import json
from pathlib import Path

import typer

from config import load_config
from intelligence.pain.candidates import (
    build_candidate_groups,
    build_candidates,
    shared_features,
)
from intelligence.pain.cluster import PainClusterer
from intelligence.pain.clean import dedupe_issues
from models.payload import (
    SandboxResult, CandidateGroup, CandidateGroupsPayload, Diagnostics,
)
from observability import RunTelemetry, OutputLevel, vprint, record_command, record_output_retention
from observability.versions import algorithm_version
from cli.commands.schema_validation import validate_collect_payload, validate_and_exit


def _get_embeddings(texts: list[str], model: str, base_url: str) -> list[list[float]]:
    """Get embeddings for a list of texts with exponential backoff retry."""
    import time
    from openai import OpenAI, APIError

    client = OpenAI(base_url=base_url, api_key="ollama")

    embeddings = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i + 50]
        for attempt in range(3):
            try:
                resp = client.embeddings.create(model=model, input=batch)
                embeddings.extend([d.embedding for d in resp.data])
                break
            except (APIError, Exception) as e:
                if attempt < 2:
                    delay = 1.0 * (2 ** attempt)
                    vprint(f"[yellow]Embedding retry {attempt + 1}/3 after {delay}s: {e}[/yellow]",
                           level=OutputLevel.NORMAL)
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Embedding failed after 3 attempts: {e}") from e
    return embeddings


def _embedding_groups(
    issues: list[dict],
    model: str,
    base_url: str,
) -> tuple[list[CandidateGroup], list]:
    """Embedding backend: HDBSCAN over Ollama embeddings → candidate groups."""
    texts = [f"{iss.get('title', '')}\n{iss.get('body', '')}"[:1000] for iss in issues]
    embeddings = _get_embeddings(texts, model=model, base_url=base_url)
    clusterer = PainClusterer(min_cluster_size=3)
    clusters = clusterer.fit(embeddings)

    candidates = build_candidates(issues)
    groups: list[CandidateGroup] = []
    for label, indices in clusters.items():
        if len(indices) < 2:
            continue
        members = [candidates[i] for i in indices]
        groups.append(CandidateGroup(
            group_id=label,
            issues=members,
            shared_features=shared_features(members),
            mean_similarity=0.0,
        ))

    assigned_idx = {i for indices in clusters.values() for i in indices}
    noise = [candidates[i] for i in range(len(candidates)) if i not in assigned_idx]
    return groups, noise


def pain(
    domain: str = typer.Argument(..., help="Domain name"),
    data: str = typer.Option("output/signals.json", "--data", "-d", help="Input signals JSON"),
    output: str = typer.Option("output/pain_candidates.json", "--output", "-o", help="Output JSON file"),
    backend: str = typer.Option("tfidf", "--backend", "-b", help="Grouping backend: tfidf (default) or embedding"),
    config: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Group collected issue signals into candidate pain groups (lexical recall)."""
    tel = RunTelemetry()
    cfg = load_config(config)

    if backend not in ("tfidf", "embedding"):
        vprint(f"[red]Unknown backend: {backend}. Use 'tfidf' or 'embedding'.[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    data_path = Path(data)
    if not data_path.exists():
        vprint(f"[red]Input file not found: {data}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    payload = raw.get("payload", raw)
    issues = payload.get("issues", [])

    validate_and_exit(payload, "pain", validate_collect_payload(payload), vprint, OutputLevel)

    diag = Diagnostics()

    if not issues:
        diag.data_quality.sample_size_warning = "No issues found in input data — cannot group. Consider re-running collect with different repos or a broader topic scope."
        result = SandboxResult(
            command="pain",
            domain=domain,
            payload=CandidateGroupsPayload().model_dump(),
            stats={"groups": 0, "issues_analyzed": 0, "noise_count": 0,
                   "backend": backend, **tel.to_stats()},
            diagnostics=diag,
        )
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.model_dump_json(indent=2))
        vprint("[yellow]No issues to group[/yellow]", level=OutputLevel.NORMAL)
        return

    # Stage 1a: dedupe (URL, then repo#number).
    issues, removed = dedupe_issues(issues)

    # Stage 1b: group via the selected backend.
    if backend == "embedding":
        try:
            groups, noise = _embedding_groups(
                issues, model=cfg.embedding.model, base_url=cfg.embedding.base_url
            )
        except Exception as e:
            vprint(f"[yellow]Embedding backend failed ({e}) — falling back to tfidf.[/yellow]",
                   level=OutputLevel.NORMAL)
            groups, noise = build_candidate_groups(issues)
    else:
        groups, noise = build_candidate_groups(issues)

    noise_count = len(noise)

    if len(issues) < 10:
        diag.data_quality.sample_size_warning = (
            f"Only {len(issues)} issues analyzed — grouping results may be unstable. "
            f"Consider collecting issues from more repos."
        )
    if noise_count > len(issues) * 0.5:
        diag.data_quality.noise_sources.append(
            f"{noise_count}/{len(issues)} issues left ungrouped — "
            f"topics may be too diverse for meaningful grouping"
        )

    result = SandboxResult(
        command="pain",
        domain=domain,
        payload=CandidateGroupsPayload(
            groups=groups,
            noise=noise,
            issue_count=len(issues),
            noise_count=noise_count,
            repos_analyzed=list(set(iss.get("repo", "") for iss in issues)),
        ).model_dump(),
        stats={"groups": len(groups), "issues_analyzed": len(issues),
               "noise_count": noise_count, "removed_duplicates": removed,
               "backend": backend, "algorithm_version": algorithm_version("pain"),
               **tel.to_stats()},
        diagnostics=diag,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2))
    vprint(f"[green]{len(groups)} candidate groups → {output}[/green]", level=OutputLevel.NORMAL)
    noise_info = f" ({noise_count} noise)" if noise_count else ""
    vprint(f"[dim]Done in {tel.elapsed_seconds}s, {len(issues)} issues analyzed{noise_info}[/dim]",
           level=OutputLevel.NORMAL)

    record_command(
        command="pain",
        domain=domain,
        flags={"data": data, "backend": backend},
        output_path=output,
        user_dna_used=False,
        elapsed_seconds=tel.elapsed_seconds,
        status="success",
    )
    record_output_retention(output)
