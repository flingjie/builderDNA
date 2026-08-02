"""opportunity — generate opportunity cards from trends + pain clusters.

Delegates scoring to intelligence/opportunity/scoring.py and alignment
to intelligence/opportunity/alignment.py. The CLI command is a thin
orchestrator: read inputs → score → render → write output.

With User DNA integration:
  personalized_score = gap_score × alignment_multiplier

Scoring config (weights, thresholds) is loaded from config.yaml →
opportunity section, enabling bootstrap-driven weight tuning without
code changes.
"""
import json
from pathlib import Path

import typer

from config import load_config
from models.payload import (
    SandboxResult, OpportunityPayload, OpportunityCard,
    Diagnostics, ConfidenceDiag,
)
from models.user_dna_schema import load_user_dna
from intelligence.opportunity.scoring import (
    compute_demand, compute_competition, compute_gap,
    compute_market_size, compute_confidence, classify_quadrant,
    recommend_action,
)
from intelligence.opportunity.alignment import compute_alignment
from observability import RunTelemetry, OutputLevel, vprint, record_command, record_output_retention
from observability.snapshot import save_opportunity_snapshot


def _generate_cards(
    trends: list[dict],
    pain_clusters: list[dict],
    user_dna= None,
    weights: dict | None = None,
    gap_threshold: float = 1.5,
    market_threshold: float = 5.0,
) -> list[OpportunityCard]:
    """Generate opportunity cards from trend + pain intersections.

    Applies two-axis scoring: gap (demand/competition) × market_size
    → quadrant classification (Build/Niche/Monitor/Avoid).
    """
    cards = []
    top_trends = sorted(trends, key=lambda t: t.get("growth_velocity", 0), reverse=True)[:5]
    top_pains = sorted(pain_clusters, key=lambda p: p.get("severity", 0), reverse=True)[:5]

    for trend in top_trends:
        topic = trend.get("topic", "unknown")

        related_pains = [
            p for p in top_pains
            if any(topic.lower() in r.lower() for r in p.get("affected_repos", []))
        ] or top_pains[:2]

        # ── Core scoring ──────────────────────────────────────────
        demand = compute_demand([trend], related_pains, weights=weights)
        competition = compute_competition([trend])
        gap = compute_gap(demand, competition)
        market_size = compute_market_size([trend])
        quadrant = classify_quadrant(gap, market_size, gap_threshold, market_threshold)

        total_evidence = trend.get("evidence_count", 0)
        total_pain_issues = sum(p.get("frequency", 0) for p in related_pains)
        confidence = compute_confidence(demand, competition, total_evidence, total_pain_issues)

        # ── Scoring breakdown for transparency ────────────────────
        import math as _math
        avg_velocity = trend.get("growth_velocity", 0)
        avg_severity = sum(p.get("severity", 0) for p in related_pains) / max(1, len(related_pains))
        total_frequency = sum(p.get("frequency", 0) for p in related_pains)
        w = weights or {"velocity": 0.4, "severity": 0.4, "frequency": 0.2}
        scoring_breakdown = {
            "velocity_contribution": round(min(10, avg_velocity / 10) * w.get("velocity", 0.4), 1),
            "severity_contribution": round(min(10, avg_severity * 2) * w.get("severity", 0.4), 1),
            "frequency_contribution": round(min(10, _math.log(total_frequency + 1) * 3) * w.get("frequency", 0.2), 1),
            "demand_score": demand,
            "competition_score": competition,
            "gap_formula": f"{demand} / max(0.1, {competition}) = {gap}",
            "market_size_score": market_size,
            "quadrant": quadrant,
            "confidence": confidence,
        }

        signals = []
        top_repos = trend.get("top_repos", [])
        for r in top_repos[:3]:
            signals.append(f"{r.get('full_name', '')} ({r.get('stars', 0)}★)")
        for p in related_pains[:1]:
            for iss in p.get("top_issues", [])[:2]:
                signals.append(f"Issue: {iss.get('title', '')[:60]}")

        action = recommend_action(topic, gap, quadrant, market_size, confidence)

        # ── Alignment ─────────────────────────────────────────────
        personalized_score = None
        alignment_reason = ""
        alignment_multiplier = 1.0
        if user_dna:
            alignment_multiplier, alignment_reason = compute_alignment(
                trend, top_repos, user_dna
            )
            personalized_score = round(gap * alignment_multiplier, 1)

        cards.append(OpportunityCard(
            title=f"{topic} — gap={gap}",
            demand_score=demand,
            competition_score=competition,
            gap_score=gap,
            signals=signals[:5],
            recommended_action=action,
            quadrant=quadrant,
            market_size_score=market_size,
            confidence=confidence,
            personalized_score=personalized_score,
            alignment_reason=alignment_reason,
            alignment_multiplier=alignment_multiplier,
            scoring_breakdown=scoring_breakdown,
        ))

    cards.sort(key=lambda c: c.personalized_score if c.personalized_score is not None else c.gap_score, reverse=True)
    return cards


def opportunity(
    trends: str = typer.Option(..., "--trends", "-t", help="Input trends JSON"),
    pains: str = typer.Option(..., "--pains", "-p", help="Input pain clusters JSON"),
    output: str = typer.Option("output/opportunities.json", "--output", "-o", help="Output JSON file"),
    user_dna: str | None = typer.Option(None, "--user-dna", help="User DNA file for personalization (optional)"),
) -> None:
    """Generate opportunity cards from trends and pain clusters (rule engine).

    Optionally applies User DNA for personalized scoring.

    Scoring weights and thresholds are loaded from config.yaml → opportunity
    section (with sensible defaults if the section is absent).
    """
    tel = RunTelemetry()
    trends_path = Path(trends)
    pains_path = Path(pains)
    if not trends_path.exists():
        vprint(f"[red]Trends file not found: {trends}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)
    if not pains_path.exists():
        vprint(f"[yellow]Pain file not found: {pains}. Continuing without pain data.[/yellow]",
               level=OutputLevel.NORMAL)
        pains_data = {"payload": {"clusters": []}}
    else:
        pains_data = json.loads(pains_path.read_text())

    trends_data = json.loads(trends_path.read_text())
    t_payload = trends_data.get("payload", trends_data)
    p_payload = pains_data.get("payload", pains_data)

    trend_list = t_payload.get("trends", [])
    pain_list = p_payload.get("clusters", [])

    # Load scoring config (with defaults if config.yaml is missing the section)
    cfg = load_config("config.yaml")
    opp_cfg = cfg.opportunity
    weights = {
        "velocity": opp_cfg.weights.velocity,
        "severity": opp_cfg.weights.severity,
        "frequency": opp_cfg.weights.frequency,
    }
    gap_threshold = opp_cfg.gap_threshold_high
    market_threshold = opp_cfg.market_size_threshold

    # Load User DNA if available (only when explicitly requested)
    dna = load_user_dna(user_dna) if user_dna else None
    if dna:
        vprint(f"[dim]User DNA loaded — applying personalized alignment[/dim]", level=OutputLevel.VERBOSE)

    cards = _generate_cards(
        trend_list, pain_list, dna,
        weights=weights,
        gap_threshold=gap_threshold,
        market_threshold=market_threshold,
    )

    # ── Build diagnostics ──────────────────────────────────────────
    diag = Diagnostics()

    # data_quality: input availability
    if not pain_list:
        diag.data_quality.coverage_gaps.append(
            "No pain clusters available — opportunity scoring is trend-only (demand may be underestimated)"
        )
    if not trend_list:
        diag.data_quality.sample_size_warning = (
            "No trend data available — cannot generate opportunities. Re-run trend command first."
        )
    if len(trend_list) < 3:
        diag.data_quality.sample_size_warning = (
            f"Only {len(trend_list)} trends available — opportunity space is narrow. "
            f"Consider collecting more signals or broadening the topic scope."
        )

    # confidence: low-confidence cards (multi-dimensional checks)
    for c in cards:
        issues = []
        # Old check: high gap from low competition
        if c.gap_score > 5.0 and c.demand_score < 2.0:
            issues.append(
                f"gap={c.gap_score:.1f} but demand={c.demand_score:.1f} — "
                f"high gap may be from low competition, not real opportunity"
            )
        # New check: low confidence from scoring engine
        if c.confidence < 0.5:
            issues.append(
                f"confidence={c.confidence:.2f} — low evidence or signal conflict"
            )
        # New check: very low competition without strong demand
        if c.competition_score < 1.0 and c.demand_score < 5.0:
            issues.append(
                f"competition={c.competition_score:.1f} + demand={c.demand_score:.1f} — "
                f"insufficient market signal, may be \"no market\" not \"untapped gold\""
            )
        if issues:
            diag.confidence.low_confidence_items.append({
                "item": c.title,
                "confidence": c.confidence,
                "reason": " | ".join(issues),
            })

    result = SandboxResult(
        command="opportunity",
        domain=t_payload.get("domain", ""),
        payload=OpportunityPayload(opportunities=cards).model_dump(),
        stats={
            "total": len(cards),
            "avg_gap": round(sum(c.gap_score for c in cards) / max(1, len(cards)), 2),
            "personalized": dna is not None,
            **tel.to_stats(),
        },
        diagnostics=diag,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2))
    vprint(f"[green]{len(cards)} opportunities → {output}[/green]", level=OutputLevel.NORMAL)
    vprint(f"[dim]Done in {tel.elapsed_seconds}s[/dim]", level=OutputLevel.NORMAL)
    for c in cards[:5]:
        base = f"gap={c.gap_score:.1f} mkt={c.market_size_score:.1f} [{c.quadrant}]"
        if c.confidence < 0.5:
            base += f" ⚠️conf={c.confidence:.2f}"
        if c.personalized_score is not None:
            base += f"  personal={c.personalized_score:.1f} (×{c.alignment_multiplier:.2f})"
        vprint(f"  {base}  {c.title}", level=OutputLevel.NORMAL)
        if c.scoring_breakdown:
            bd = c.scoring_breakdown
            vprint(f"    demand={bd.get('demand_score','?')} competition={bd.get('competition_score','?')} "
                   f"market_size={bd.get('market_size_score','?')} confidence={bd.get('confidence','?')} "
                   f"| vel={bd.get('velocity_contribution','?')} sev={bd.get('severity_contribution','?')} "
                   f"freq={bd.get('frequency_contribution','?')}", level=OutputLevel.VERBOSE)

    # Behavior tracking + prediction snapshot
    card_dicts = [c.model_dump() for c in cards]
    record_command(
        command="opportunity",
        domain=t_payload.get("domain", ""),
        flags={"trends": trends, "pains": pains},
        output_path=output,
        user_dna_used=dna is not None,
        elapsed_seconds=tel.elapsed_seconds,
        status="success",
    )
    record_output_retention(output)
    save_opportunity_snapshot(domain=t_payload.get("domain", ""), cards=card_dicts)
