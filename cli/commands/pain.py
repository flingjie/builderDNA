"""pain — cluster issue signals via HDBSCAN, output pain clusters."""
import json
import math
from pathlib import Path

import typer

from intelligence.pain.cluster import PainClusterer
from intelligence.pain.severity import compute_severity
from models.payload import (
    SandboxResult, PainPayload, PainCluster, IssueSummary,
)
from observability import RunTelemetry, OutputLevel, vprint


def _get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a list of texts with exponential backoff retry."""
    import os
    import time
    from openai import OpenAI, APIError

    base_url = os.environ.get("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("EMBEDDING_MODEL", "bge-m3:latest")
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
) -> None:
    """Mine pain points from collected issue signals."""
    tel = RunTelemetry()
    data_path = Path(data)
    if not data_path.exists():
        vprint(f"[red]Input file not found: {data}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    payload = raw.get("payload", raw)
    issues = payload.get("issues", [])

    if not issues:
        result = SandboxResult(
            command="pain",
            domain=domain,
            payload=PainPayload().model_dump(),
            stats={"issue_count": 0, "repos_analyzed": [], "noise_count": 0, **tel.to_stats()},
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
        embeddings = _get_embeddings(texts)
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
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    vprint(f"[green]{len(pain_clusters_list)} pain clusters → {output}[/green]", level=OutputLevel.NORMAL)
    noise_info = f" ({noise_count} noise)" if noise_count else ""
    vprint(f"[dim]Done in {tel.elapsed_seconds}s, {len(issues)} issues analyzed{noise_info}[/dim]",
           level=OutputLevel.NORMAL)
