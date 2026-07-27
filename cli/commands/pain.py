"""pain — cluster issue signals via HDBSCAN, output pain clusters."""
import json
import math
from pathlib import Path

import typer

from config import load_config
from intelligence.pain.cluster import PainClusterer
from intelligence.pain.severity import compute_severity
from models.payload import (
    SandboxResult, PainPayload, PainCluster, IssueSummary,
    Diagnostics, DataQualityDiag, ConfidenceDiag,
)
from observability import RunTelemetry, OutputLevel, vprint, record_command, record_output_retention
from observability.snapshot import save_pain_snapshot


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


def pain(
    domain: str = typer.Argument(..., help="Domain name"),
    data: str = typer.Option("output/signals.json", "--data", "-d", help="Input signals JSON"),
    output: str = typer.Option("output/pain_clusters.json", "--output", "-o", help="Output JSON file"),
    config: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Mine pain points from collected issue signals."""
    tel = RunTelemetry()
    cfg = load_config(config)
    embedding_model = cfg.embedding.model
    embedding_base_url = cfg.embedding.base_url

    data_path = Path(data)
    if not data_path.exists():
        vprint(f"[red]Input file not found: {data}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    payload = raw.get("payload", raw)
    issues = payload.get("issues", [])

    if not issues:
        diag = Diagnostics()
        diag.data_quality.sample_size_warning = "No issues found in input data — cannot cluster. Consider re-running collect with different repos or a broader topic scope."
        result = SandboxResult(
            command="pain",
            domain=domain,
            payload=PainPayload().model_dump(),
            stats={"issue_count": 0, "repos_analyzed": [], "noise_count": 0, **tel.to_stats()},
            diagnostics=diag,
        )
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
        vprint("[yellow]No issues to cluster[/yellow]", level=OutputLevel.NORMAL)
        return

    # Build texts for embedding
    texts = [f"{iss.get('title', '')}\n{iss.get('body', '')}"[:1000] for iss in issues]

    # Get embeddings and cluster
    try:
        embeddings = _get_embeddings(texts, model=embedding_model, base_url=embedding_base_url)
    except Exception as e:
        vprint(f"[yellow]Embedding failed: {e}. Falling back to title-based grouping.[/yellow]",
               level=OutputLevel.NORMAL)
        embeddings = []

    pain_clusters_list = []
    noise_count = 0
    if embeddings:
        clusterer = PainClusterer(min_cluster_size=3)
        clusters = clusterer.fit(embeddings)
        # Count noise points: all indices that were NOT assigned to any cluster
        all_assigned = set()
        for indices in clusters.values():
            all_assigned.update(indices)
        noise_count = len(embeddings) - len(all_assigned)
        for cluster_id, indices in clusters.items():
            cluster_issues = [issues[i] for i in indices]
            severities = [
                compute_severity(
                    iss.get("comments", 0),
                    iss.get("participants", 0),
                    (iss.get("title", "") + " " + iss.get("body", ""))[:500],
                    iss.get("reactions", 0),
                )
                for iss in cluster_issues
            ]
            repos = list(set(iss.get("repo", "") for iss in cluster_issues))
            top = sorted(cluster_issues, key=lambda x: x.get("reactions", 0) + x.get("comments", 0), reverse=True)[:3]

            pain_clusters_list.append(PainCluster(
                cluster_id=cluster_id,
                title=f"Pain Cluster {cluster_id}",
                severity=round(sum(severities) / len(severities), 2),
                frequency=len(cluster_issues),
                affected_repos=repos,
                top_issues=[
                    IssueSummary(
                        repo=iss.get("repo", ""),
                        issue_number=iss.get("issue_number", 0),
                        title=iss.get("title", "")[:100],
                        pain_score=compute_severity(
                            iss.get("comments", 0),
                            iss.get("participants", 0),
                            (iss.get("title", "") + " " + iss.get("body", ""))[:500],
                            iss.get("reactions", 0),
                        ),
                    )
                    for iss in top
                ],
            ))

    # ── Build diagnostics ──────────────────────────────────────────
    diag = Diagnostics()

    # data_quality: sample size
    if len(issues) < 10:
        diag.data_quality.sample_size_warning = (
            f"Only {len(issues)} issues analyzed — clustering results may be unstable. "
            f"Consider collecting issues from more repos."
        )
    if noise_count > len(issues) * 0.5:
        diag.data_quality.noise_sources.append(
            f"{noise_count}/{len(issues)} issues classified as noise — "
            f"topics may be too diverse for meaningful clustering"
        )

    # confidence: weak clusters
    for c in pain_clusters_list:
        if c.frequency == 1:
            diag.confidence.low_confidence_items.append({
                "item": f"Cluster {c.cluster_id}: {c.title}",
                "confidence": 0.1,
                "reason": "single-issue cluster — not a real pain pattern; noise that barely exceeded threshold",
            })
        if c.severity < 0.3:
            diag.confidence.low_confidence_items.append({
                "item": f"Cluster {c.cluster_id}: {c.title}",
                "confidence": round(c.severity, 2),
                "reason": f"severity={c.severity:.2f} — issues in this cluster have low engagement, may not represent real pain",
            })

    result = SandboxResult(
        command="pain",
        domain=domain,
        payload=PainPayload(
            clusters=pain_clusters_list,
            issue_count=len(issues),
            repos_analyzed=list(set(iss.get("repo", "") for iss in issues)),
        ).model_dump(),
        stats={"clusters": len(pain_clusters_list), "issues_analyzed": len(issues),
               "noise_count": noise_count, **tel.to_stats()},
        diagnostics=diag,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    vprint(f"[green]{len(pain_clusters_list)} pain clusters → {output}[/green]", level=OutputLevel.NORMAL)
    noise_info = f" ({noise_count} noise)" if noise_count else ""
    vprint(f"[dim]Done in {tel.elapsed_seconds}s, {len(issues)} issues analyzed{noise_info}[/dim]",
           level=OutputLevel.NORMAL)

    # Behavior tracking + prediction snapshot
    cluster_dicts = [c.model_dump() for c in pain_clusters_list]
    record_command(
        command="pain",
        domain=domain,
        flags={"data": data},
        output_path=output,
        user_dna_used=False,
        elapsed_seconds=tel.elapsed_seconds,
        status="success",
    )
    record_output_retention(output)
    save_pain_snapshot(domain=domain, clusters=cluster_dicts,
                       issue_count=len(issues), noise_count=noise_count)
