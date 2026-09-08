"""Input schema validation for the collect → trend/pain → opportunity chain.

Each consuming command validates its input *before* processing and fails with a
clear error rather than silently producing garbage from a malformed file. The
validators are structural (shape + required keys), not full pydantic
round-trips, so they tolerate the flat-vs-normalized output formats that
``collect`` has produced across versions.
"""


def validate_collect_payload(payload: dict) -> list[str]:
    """Validate a collect-output payload. Empty list = valid.

    A collect output carries ``repos``/``issues`` (flat) and/or ``signals``
    (normalized). Downstream ``trend``/``pain`` need at least one repo or
    signal source to work on.
    """
    errors: list[str] = []
    for key in ("repos", "issues", "signals"):
        if key in payload and not isinstance(payload[key], list):
            errors.append(f"payload.{key} must be a list, got {type(payload[key]).__name__}")

    if "repos" not in payload and "signals" not in payload:
        errors.append("payload must contain 'repos' or 'signals' (not a collect output)")

    for r in payload.get("repos", []) or []:
        if isinstance(r, dict) and not r.get("full_name"):
            errors.append("each repo entry requires a 'full_name'")
    for i in payload.get("issues", []) or []:
        if isinstance(i, dict) and not i.get("repo"):
            errors.append("each issue entry requires a 'repo'")
    return errors


def validate_trend_payload(payload: dict) -> list[str]:
    """Validate a trend-output payload. Empty list = valid."""
    errors: list[str] = []
    trends = payload.get("trends")
    if trends is None:
        errors.append("payload must contain 'trends'")
    elif not isinstance(trends, list):
        errors.append(f"payload.trends must be a list, got {type(trends).__name__}")
    else:
        for t in trends:
            if isinstance(t, dict) and not t.get("topic"):
                errors.append("each trend entry requires a 'topic'")
    return errors


def validate_pain_payload(payload: dict) -> list[str]:
    """Validate a pain-output payload. Empty list = valid (no clusters is fine)."""
    errors: list[str] = []
    clusters = payload.get("clusters")
    if clusters is None:
        errors.append("payload must contain 'clusters'")
    elif not isinstance(clusters, list):
        errors.append(f"payload.clusters must be a list, got {type(clusters).__name__}")
    return errors


def validate_and_exit(payload: dict, command: str, violations: list[str], vprint, OutputLevel) -> None:
    """Shared helper: print violations and exit non-zero when invalid."""
    if not violations:
        return
    vprint(
        f"[red]Input schema invalid for {command}: {'; '.join(violations)}[/red]",
        level=OutputLevel.QUIET,
    )
    import typer

    raise typer.Exit(1)
