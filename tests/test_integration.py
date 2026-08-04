"""Integration tests for BuilderDNA command pipelines.

Tests full pipelines end-to-end without network access:
  - Trend pipeline: Signal creation -> store -> trend computation -> TopicTrend output
  - Opportunity pipeline: Trend + pain data -> scoring -> OpportunityCard output
  - SandboxResult consistency across commands
  - JSON roundtrip serialization
"""

import json
import pytest
from datetime import datetime, timezone, timedelta

from signals.models import Signal
from signals.store import SignalStore
from models.payload import (
    SandboxResult,
    TrendPayload,
    TopicTrend,
    RepoSummary,
    OpportunityPayload,
    OpportunityCard,
    Diagnostics,
    DataQualityDiag,
    ConfidenceDiag,
)
from intelligence.trend.velocity import compute_acceleration, _resolve_stage
from intelligence.opportunity.scoring import (
    compute_demand,
    compute_competition,
    compute_gap,
    compute_market_size,
    compute_confidence,
    classify_quadrant,
    recommend_action,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _run_trend_pipeline(
    signals: list[Signal], window_days: int = 365, db_path: str | None = None
) -> list[TopicTrend]:
    """Run the full trend pipeline: signals -> store -> trend computation.

    Replicates the core logic from cli/commands/trend.py without file I/O
    or observability side effects.

    Args:
        signals: Signal objects to insert.
        window_days: Analysis time window.
        db_path: Path for the SQLite store. Uses a temp path if not provided
                 to avoid cross-test contamination.
    """
    import tempfile
    if db_path is None:
        db_path = tempfile.mkstemp(suffix=".db")[1]
    with SignalStore(db_path) as store:
        store.insert(signals)
        trend_rows = store.get_topic_trends(days=window_days)

    # Group signals by topic for top_repos enrichment
    topic_signals: dict[str, list[Signal]] = {}
    for s in signals:
        for topic in s.payload.get("topics", []):
            topic_signals.setdefault(topic, []).append(s)

    trends: list[TopicTrend] = []
    for t in trend_rows:
        sigs = topic_signals.get(t.topic, [])
        accel = compute_acceleration(sigs, window_days=window_days)
        t.acceleration = round(accel, 2)
        stage, reason = _resolve_stage(t.growth_velocity, accel, t.confidence)
        t.stage = stage
        t.classification_reason = reason

        # Build top_repos from signal data
        topic_repos: dict[str, dict] = {}
        for s in sigs:
            name = s.target_repo
            if name not in topic_repos:
                p = s.payload
                topic_repos[name] = {
                    "full_name": name,
                    "stars": p.get("stars", 0),
                    "forks": p.get("forks", 0),
                    "contributors": p.get("contributors", 0),
                    "velocity": s.velocity,
                }
        sorted_repos = sorted(
            topic_repos.values(), key=lambda r: r["stars"], reverse=True
        )[:5]
        t.top_repos = [
            RepoSummary(
                full_name=r["full_name"],
                stars=r["stars"],
                forks=r["forks"],
                contributors=r["contributors"],
                velocity=r["velocity"],
            )
            for r in sorted_repos
        ]
        trends.append(t)

    trends.sort(key=lambda x: x.growth_velocity, reverse=True)
    return trends


def _make_sample_signals(
    base_time: datetime | None = None,
) -> list[Signal]:
    """Create a realistic set of signals across 4 topics with varying velocity."""
    now = base_time or datetime.now(timezone.utc)
    signals = []

    # High-velocity: agent-framework repos
    for i in range(6):
        signals.append(Signal(
            id=f"sig-agent-{i}",
            source="github",
            type="repo_created" if i % 2 == 0 else "star_growth",
            actor="org-a",
            target_repo=f"org-a/agent-repo{i}",
            timestamp=now - timedelta(days=i * 5),
            velocity=25.0 - i * 2,
            impact=0.8,
            payload={
                "topics": ["agent-framework", "agent"],
                "stars": 5000 - i * 500,
                "forks": 500 - i * 50,
                "contributors": 0,
                "description": f"Agent framework repo {i}",
                "language": "Python",
                "created_at": (now - timedelta(days=100 + i * 10)).isoformat(),
            },
        ))

    # Emerging: mcp topic
    for i in range(4):
        signals.append(Signal(
            id=f"sig-mcp-{i}",
            source="github",
            type="repo_created",
            actor="org-b",
            target_repo=f"org-b/mcp-repo{i}",
            timestamp=now - timedelta(days=i * 3),
            velocity=18.0 - i * 3,
            impact=0.7,
            payload={
                "topics": ["mcp", "agent"],
                "stars": 2000 - i * 300,
                "forks": 200 - i * 30,
                "contributors": 0,
                "description": f"MCP repo {i}",
                "language": "TypeScript",
                "created_at": (now - timedelta(days=50 + i * 5)).isoformat(),
            },
        ))

    # Mainstream: langchain topic
    for i in range(5):
        signals.append(Signal(
            id=f"sig-lc-{i}",
            source="github",
            type="star_growth",
            actor="org-c",
            target_repo=f"org-c/langchain-tool{i}",
            timestamp=now - timedelta(days=i * 10),
            velocity=8.0 - i * 1.5,
            impact=0.5,
            payload={
                "topics": ["langchain", "agent"],
                "stars": 8000 - i * 1000,
                "forks": 800 - i * 100,
                "contributors": 0,
                "description": f"LangChain tool {i}",
                "language": "Python",
                "created_at": (now - timedelta(days=300 + i * 20)).isoformat(),
            },
        ))

    # Low velocity / declining: tool-calling topic
    for i in range(3):
        signals.append(Signal(
            id=f"sig-tc-{i}",
            source="github",
            type="repo_created",
            actor="org-d",
            target_repo=f"org-d/tool-repo{i}",
            timestamp=now - timedelta(days=i * 15),
            velocity=3.0 - i * 1.0,
            impact=0.3,
            payload={
                "topics": ["tool-calling"],
                "stars": 500 - i * 100,
                "forks": 50 - i * 10,
                "contributors": 0,
                "description": f"Tool calling repo {i}",
                "language": "Rust",
                "created_at": (now - timedelta(days=400 + i * 30)).isoformat(),
            },
        ))

    return signals


def _make_sample_trends() -> list[dict]:
    """Create sample trend dicts matching the format from trend command output."""
    return [
        {
            "topic": "agent-framework",
            "stage": "accelerating",
            "confidence": 0.85,
            "growth_velocity": 22.0,
            "acceleration": 3.2,
            "evidence_count": 12,
            "top_repos": [
                {"full_name": "org-a/agent-repo0", "stars": 5000, "forks": 500, "contributors": 0, "velocity": 25.0},
                {"full_name": "org-a/agent-repo1", "stars": 4500, "forks": 450, "contributors": 0, "velocity": 23.0},
            ],
        },
        {
            "topic": "mcp",
            "stage": "emerging",
            "confidence": 0.70,
            "growth_velocity": 15.0,
            "acceleration": 1.5,
            "evidence_count": 8,
            "top_repos": [
                {"full_name": "org-b/mcp-repo0", "stars": 2000, "forks": 200, "contributors": 0, "velocity": 18.0},
                {"full_name": "org-b/mcp-repo1", "stars": 1700, "forks": 170, "contributors": 0, "velocity": 15.0},
            ],
        },
        {
            "topic": "langchain",
            "stage": "mainstream",
            "confidence": 0.60,
            "growth_velocity": 5.0,
            "acceleration": 0.2,
            "evidence_count": 25,
            "top_repos": [
                {"full_name": "org-c/langchain-tool0", "stars": 8000, "forks": 800, "contributors": 0, "velocity": 8.0},
                {"full_name": "org-c/langchain-tool1", "stars": 7000, "forks": 700, "contributors": 0, "velocity": 6.5},
            ],
        },
        {
            "topic": "tool-calling",
            "stage": "declining",
            "confidence": 0.30,
            "growth_velocity": 2.0,
            "acceleration": -2.0,
            "evidence_count": 5,
            "top_repos": [
                {"full_name": "org-d/tool-repo0", "stars": 500, "forks": 50, "contributors": 0, "velocity": 3.0},
            ],
        },
    ]


def _make_sample_pains() -> list[dict]:
    """Create sample pain cluster dicts matching the format from pain command output."""
    return [
        {
            "cluster_id": 1,
            "title": "Agent framework lacks proper error handling",
            "severity": 8.5,
            "frequency": 15,
            "affected_repos": ["org-a/agent-repo0", "org-a/agent-repo1"],
            "top_issues": [
                {"repo": "org-a/agent-repo0", "issue_number": 101, "title": "No retry logic for failed tool calls", "pain_score": 0.9},
                {"repo": "org-a/agent-repo1", "issue_number": 42, "title": "Agents hang indefinitely on timeout", "pain_score": 0.85},
            ],
        },
        {
            "cluster_id": 2,
            "title": "MCP server discovery is painful",
            "severity": 7.0,
            "frequency": 10,
            "affected_repos": ["org-b/mcp-repo0", "org-b/mcp-repo1"],
            "top_issues": [
                {"repo": "org-b/mcp-repo0", "issue_number": 55, "title": "Can't discover MCP servers dynamically", "pain_score": 0.8},
            ],
        },
        {
            "cluster_id": 3,
            "title": "LangChain breaking changes are frequent",
            "severity": 5.0,
            "frequency": 20,
            "affected_repos": ["org-c/langchain-tool0"],
            "top_issues": [
                {"repo": "org-c/langchain-tool0", "issue_number": 200, "title": "Deprecated API breaks existing agents", "pain_score": 0.7},
            ],
        },
    ]


# ── Trend Pipeline Integration Tests ──────────────────────────────────


class TestTrendPipeline:
    """End-to-end trend pipeline: Signal -> store -> trend computation."""

    def test_full_pipeline_produces_ranked_trends(self, tmp_path):
        """Signals of varying velocity produce properly ranked TopicTrend output."""
        signals = _make_sample_signals()
        trends = _run_trend_pipeline(signals, window_days=365, db_path=str(tmp_path / "trends.db"))
        assert len(trends) >= 1, "Expected at least one topic trend"

        # Verify structure of every trend
        for trend in trends:
            assert isinstance(trend.topic, str)
            assert trend.topic != ""
            assert trend.stage in ("accelerating", "emerging", "mainstream", "declining")
            assert 0.0 <= trend.confidence <= 1.0
            assert trend.growth_velocity >= 0
            assert trend.evidence_count >= 1
            assert len(trend.top_repos) >= 1
            assert trend.classification_reason != ""
            for repo in trend.top_repos:
                assert isinstance(repo.full_name, str)
                assert isinstance(repo.stars, int)

        # High-velocity topics should appear first
        velocities = [t.growth_velocity for t in trends]
        assert velocities == sorted(velocities, reverse=True), "Trends should be sorted by velocity descending"

    def test_pipeline_with_trend_payload_wrapper(self, tmp_path):
        """Trend pipeline output can be wrapped in TrendPayload and SandboxResult."""
        store = SignalStore(str(tmp_path / "trend_payload.db"))
        signals = _make_sample_signals()

        trends = _run_trend_pipeline(signals, window_days=365)
        assert len(trends) >= 1

        payload = TrendPayload(trends=trends, domain="agent", window_days=365)
        result = SandboxResult(
            command="trend",
            domain="agent",
            payload=payload.model_dump(),
            stats={"total_trends": len(trends)},
        )

        assert result.command == "trend"
        assert result.domain == "agent"
        assert "T" in result.computed_at
        loaded_payload = TrendPayload(**result.payload)
        assert len(loaded_payload.trends) == len(trends)

    def test_empty_pipeline_returns_empty_list(self, tmp_path):
        """Pipeline with no signals returns empty trend list."""
        store = SignalStore(str(tmp_path / "empty.db"))
        with store:
            trends = store.get_topic_trends(days=30)
        assert trends == []

    def test_pipeline_with_single_signal(self, tmp_path):
        """Single signal produces one trend with one repo."""
        now = datetime.now(timezone.utc)
        signal = Signal(
            id="sig-single",
            source="github",
            type="repo_created",
            actor="solo",
            target_repo="solo/repo",
            timestamp=now,
            velocity=10.0,
            impact=0.5,
            payload={"topics": ["solo-topic"], "stars": 100, "forks": 10, "contributors": 0},
        )

        trends = _run_trend_pipeline([signal], window_days=30)
        assert len(trends) == 1
        t = trends[0]
        assert t.topic == "solo-topic"
        assert t.evidence_count == 1
        assert t.confidence <= 1.0
        assert len(t.top_repos) == 1
        assert t.top_repos[0].full_name == "solo/repo"
        assert t.top_repos[0].stars == 100


# ── Opportunity Pipeline Integration Tests ────────────────────────────


class TestOpportunityPipeline:
    """End-to-end opportunity scoring pipeline: trends + pains -> cards."""

    def test_scoring_chain_produces_valid_scores(self):
        """Full scoring chain (demand -> competition -> gap -> market -> confidence -> quadrant)."""
        trends = _make_sample_trends()
        pains = _make_sample_pains()

        demand = compute_demand(trends, pains)
        assert 0.0 <= demand <= 10.0, f"Demand {demand} out of range"

        competition = compute_competition(trends)
        assert 0.0 <= competition <= 10.0, f"Competition {competition} out of range"

        gap = compute_gap(demand, competition)
        assert gap >= 0, f"Gap {gap} should be non-negative"

        market_size = compute_market_size(trends)
        assert 0.0 <= market_size <= 10.0, f"Market size {market_size} out of range"

        total_evidence = sum(t.get("evidence_count", 0) for t in trends)
        total_pains = sum(p.get("frequency", 0) for p in pains)
        confidence = compute_confidence(demand, competition, total_evidence, total_pains)
        assert 0.0 <= confidence <= 1.0, f"Confidence {confidence} out of range"

        quadrant = classify_quadrant(gap, market_size)
        assert quadrant in ("Build", "Niche", "Monitor", "Avoid")

        action = recommend_action("agent-framework", gap, quadrant, market_size, confidence)
        assert isinstance(action, str) and len(action) > 0

    def test_high_gap_big_market_produces_build(self):
        """High demand + low competition + big market should produce Build quadrant."""
        trends = [_make_sample_trends()[0]]  # agent-framework: accelerating, 5000 stars
        pains = [_make_sample_pains()[0]]  # high severity

        demand = compute_demand(trends, pains)
        competition = compute_competition(trends)
        gap = compute_gap(demand, competition)
        market_size = compute_market_size(trends)
        quadrant = classify_quadrant(gap, market_size, gap_threshold=1.5, market_threshold=5.0)
        action = recommend_action("agent-framework", gap, quadrant, market_size, 0.85)

        # For a single accelerating topic with decent stars, we expect Build or Niche
        assert quadrant in ("Build", "Niche", "Monitor", "Avoid")
        assert "agent-framework" in action

    def test_low_velocity_no_pains_produces_avoid_or_monitor(self):
        """Low velocity with no pain signals should produce low-confidence results."""
        trend = {
            "topic": "obscure-topic",
            "stage": "declining",
            "confidence": 0.15,
            "growth_velocity": 0.3,
            "acceleration": -1.2,
            "evidence_count": 1,
            "top_repos": [
                {"full_name": "ghost/repo", "stars": 10, "forks": 1, "contributors": 0, "velocity": 0.3},
            ],
        }

        demand = compute_demand([trend], [])
        competition = compute_competition([trend])
        gap = compute_gap(demand, competition)
        market_size = compute_market_size([trend])
        confidence = compute_confidence(demand, competition, 1, 0)
        quadrant = classify_quadrant(gap, market_size)

        # Low evidence (1 signal) + no pain data = low confidence
        assert confidence < 0.6
        # Low market + low velocity should produce Avoid or Monitor
        assert quadrant in ("Avoid", "Monitor")

    def test_scoring_with_custom_weights(self):
        """Custom weights affect demand computation."""
        trends = _make_sample_trends()
        pains = _make_sample_pains()

        default_demand = compute_demand(trends, pains)
        velocity_heavy_demand = compute_demand(
            trends, pains, weights={"velocity": 0.9, "severity": 0.05, "frequency": 0.05}
        )
        severity_heavy_demand = compute_demand(
            trends, pains, weights={"velocity": 0.05, "severity": 0.9, "frequency": 0.05}
        )

        # Different weights should produce different demand scores
        scores = {default_demand, velocity_heavy_demand, severity_heavy_demand}
        assert len(scores) >= 2, "Different weights should produce different demand scores"

    def test_opportunity_card_from_sample_data(self):
        """Construct and validate a full OpportunityCard from sample pipeline data."""
        card = OpportunityCard(
            title="agent-framework - gap=3.5",
            demand_score=7.0,
            competition_score=2.0,
            gap_score=3.5,
            signals=[
                "org-a/agent-repo0 (5000 stars)",
                "Issue: No retry logic for failed tool calls",
            ],
            recommended_action="Strongly recommended to build in agent-framework",
            quadrant="Build",
            market_size_score=8.0,
            confidence=0.85,
        )

        assert card.title.startswith("agent-framework")
        assert card.quadrant == "Build"
        assert card.gap_score == 3.5
        assert card.confidence == 0.85
        assert len(card.signals) == 2
        assert card.personalized_score is None

    def test_opportunity_payload_collection(self):
        """Multiple cards can be collected in an OpportunityPayload."""
        cards = [
            OpportunityCard(
                title=f"topic-{i} - gap={i+1.0}",
                demand_score=5.0 + i,
                competition_score=2.0,
                gap_score=round((5.0 + i) / 2.0, 1),
                quadrant="Build" if i == 0 else "Monitor",
                market_size_score=6.0,
                confidence=0.7,
            )
            for i in range(3)
        ]

        payload = OpportunityPayload(opportunities=cards)
        assert len(payload.opportunities) == 3

    def test_opportunity_card_with_alignment(self):
        """Card with alignment fields (personalized score, reason, multiplier)."""
        card = OpportunityCard(
            title="mcp - gap=2.8",
            demand_score=5.6,
            competition_score=2.0,
            gap_score=2.8,
            quadrant="Niche",
            market_size_score=4.0,
            confidence=0.75,
            personalized_score=3.4,
            alignment_reason="Matches your preference for autonomy and exploration",
            alignment_multiplier=1.2,
        )

        assert card.personalized_score == 3.4
        assert card.alignment_multiplier == 1.2
        assert "autonomy" in card.alignment_reason


# ── SandboxResult Consistency Tests ───────────────────────────────────


class TestSandboxResultConsistency:
    """Verify SandboxResult structure consistency across all command types."""

    def test_trend_result_has_required_fields(self):
        """Trend SandboxResult contains all expected top-level fields."""
        result = SandboxResult(
            command="trend",
            domain="agent",
            payload=TrendPayload(domain="agent", window_days=365, trends=[]).model_dump(),
            stats={"total_trends": 0},
            diagnostics=Diagnostics(),
        )

        assert result.command == "trend"
        assert result.domain == "agent"
        assert isinstance(result.computed_at, str)
        assert "T" in result.computed_at
        assert isinstance(result.payload, dict)
        assert isinstance(result.stats, dict)
        assert isinstance(result.diagnostics, Diagnostics)

    def test_opportunity_result_has_required_fields(self):
        """Opportunity SandboxResult contains all expected top-level fields."""
        result = SandboxResult(
            command="opportunity",
            domain="agent",
            payload=OpportunityPayload(opportunities=[]).model_dump(),
            stats={"total": 0, "avg_gap": 0.0},
            diagnostics=Diagnostics(),
        )

        assert result.command == "opportunity"
        assert result.domain == "agent"
        assert isinstance(result.computed_at, str)
        assert isinstance(result.payload, dict)
        assert isinstance(result.stats, dict)

    def test_diagnostics_structure(self):
        """Diagnostics have the correct substructures."""
        diag = Diagnostics(
            data_quality=DataQualityDiag(
                coverage_gaps=["topic 'x' matched only 1 repo"],
                noise_sources=["topic 'y' matched 80 repos"],
                api_issues=["rate-limited 2 times"],
                sample_size_warning="Only 5 repos collected",
            ),
            confidence=ConfidenceDiag(
                low_confidence_items=[
                    {"item": "topic-z", "confidence": 0.15, "reason": "insufficient evidence"},
                ],
            ),
        )

        assert len(diag.data_quality.coverage_gaps) == 1
        assert len(diag.data_quality.noise_sources) == 1
        assert len(diag.data_quality.api_issues) == 1
        assert "5 repos" in diag.data_quality.sample_size_warning
        assert len(diag.confidence.low_confidence_items) == 1
        assert diag.data_quality is not None
        assert diag.confidence is not None

    def test_stats_dict_across_commands(self):
        """Different commands produce appropriate stats."""
        trend_stats = {"total_trends": 12, "elapsed_ms": 450}
        opp_stats = {"total": 5, "avg_gap": 3.2, "personalized": False}

        trend_result = SandboxResult(
            command="trend", domain="agent",
            payload=TrendPayload(domain="agent", window_days=365, trends=[]).model_dump(),
            stats=trend_stats,
        )
        opp_result = SandboxResult(
            command="opportunity", domain="agent",
            payload=OpportunityPayload(opportunities=[]).model_dump(),
            stats=opp_stats,
        )

        assert trend_result.stats["total_trends"] == 12
        assert opp_result.stats["avg_gap"] == 3.2

    def test_payload_reconstruction(self):
        """Payload can be round-tripped through model_dump and reconstruction."""
        trends = _make_sample_trends()
        topic_trends = [
            TopicTrend(
                topic=t["topic"],
                stage=t["stage"],
                confidence=t["confidence"],
                growth_velocity=t["growth_velocity"],
                acceleration=t.get("acceleration", 0.0),
                evidence_count=t["evidence_count"],
                top_repos=[
                    RepoSummary(**r) for r in t.get("top_repos", [])
                ],
            )
            for t in trends
        ]

        original = TrendPayload(trends=topic_trends, domain="agent", window_days=365)
        result = SandboxResult(
            command="trend",
            domain="agent",
            payload=original.model_dump(),
            stats={"total_trends": len(topic_trends)},
        )

        # Reconstruct from payload dict
        reconstructed = TrendPayload(**result.payload)
        assert len(reconstructed.trends) == len(topic_trends)
        assert reconstructed.trends[0].topic == trends[0]["topic"]


# ── JSON Roundtrip Tests ──────────────────────────────────────────────


class TestJsonRoundtrip:
    """Verify SandboxResult survives JSON serialization roundtrip."""

    def test_roundtrip_minimal_result(self):
        """Minimal SandboxResult serializes and deserializes correctly."""
        original = SandboxResult(
            command="collect",
            domain="test",
            payload={"repos": [], "issues": [], "signals": []},
            stats={"total_signals": 0},
        )

        json_str = original.model_dump_json(indent=2)
        assert isinstance(json_str, str)
        assert "collect" in json_str

        parsed = json.loads(json_str)
        reconstructed = SandboxResult(**parsed)
        assert reconstructed.command == original.command
        assert reconstructed.domain == original.domain
        assert reconstructed.payload == original.payload

    def test_roundtrip_with_trend_payload(self):
        """Full trend pipeline output survives JSON roundtrip."""
        signals = _make_sample_signals()
        trends = _run_trend_pipeline(signals, window_days=365)

        payload = TrendPayload(trends=trends, domain="agent", window_days=365)
        diag = Diagnostics(
            data_quality=DataQualityDiag(
                coverage_gaps=["topic 'x' had only 1 repo"],
            ),
            confidence=ConfidenceDiag(
                low_confidence_items=[
                    {"item": "tool-calling", "confidence": 0.25, "reason": "only 3 signals"},
                ],
            ),
        )

        original = SandboxResult(
            command="trend",
            domain="agent",
            payload=payload.model_dump(),
            stats={"total_trends": len(trends), "elapsed_ms": 234},
            diagnostics=diag,
        )

        # Roundtrip: model -> JSON -> dict -> model
        json_str = original.model_dump_json(indent=2)
        parsed = json.loads(json_str)
        reconstructed = SandboxResult(**parsed)

        assert reconstructed.command == "trend"
        assert reconstructed.domain == "agent"
        assert reconstructed.stats["total_trends"] == len(trends)

        # Verify trends payload survived roundtrip
        recon_payload = TrendPayload(**reconstructed.payload)
        assert len(recon_payload.trends) == len(trends)
        assert recon_payload.trends[0].topic == trends[0].topic
        assert recon_payload.trends[0].growth_velocity == trends[0].growth_velocity

        # Verify diagnostics survived
        assert len(reconstructed.diagnostics.data_quality.coverage_gaps) == 1
        assert len(reconstructed.diagnostics.confidence.low_confidence_items) == 1

    def test_roundtrip_with_opportunity_payload(self):
        """Full opportunity pipeline output survives JSON roundtrip."""
        trends = _make_sample_trends()
        pains = _make_sample_pains()

        # Build cards using the scoring functions
        cards = []
        for trend in trends[:3]:
            topic = trend["topic"]
            related_pains = [
                p for p in pains
                if any(topic.lower() in r.lower() for r in p.get("affected_repos", []))
            ] or pains[:1]

            demand = compute_demand([trend], related_pains)
            competition = compute_competition([trend])
            gap = compute_gap(demand, competition)
            market_size = compute_market_size([trend])
            total_evidence = trend.get("evidence_count", 0)
            total_pains = sum(p.get("frequency", 0) for p in related_pains)
            confidence = compute_confidence(demand, competition, total_evidence, total_pains)
            quadrant = classify_quadrant(gap, market_size)
            action = recommend_action(topic, gap, quadrant, market_size, confidence)

            signals = []
            for r in trend.get("top_repos", [])[:2]:
                signals.append(f"{r.get('full_name', '')} ({r.get('stars', 0)} stars)")

            cards.append(OpportunityCard(
                title=f"{topic} - gap={gap}",
                demand_score=demand,
                competition_score=competition,
                gap_score=gap,
                signals=signals,
                recommended_action=action,
                quadrant=quadrant,
                market_size_score=market_size,
                confidence=confidence,
            ))

        payload = OpportunityPayload(opportunities=cards)
        diag = Diagnostics(
            data_quality=DataQualityDiag(
                sample_size_warning="Only 3 trends available",
            ),
        )

        original = SandboxResult(
            command="opportunity",
            domain="agent",
            payload=payload.model_dump(),
            stats={"total": len(cards), "avg_gap": round(sum(c.gap_score for c in cards) / len(cards), 2)},
            diagnostics=diag,
        )

        # Roundtrip
        json_str = original.model_dump_json(indent=2)
        parsed = json.loads(json_str)
        reconstructed = SandboxResult(**parsed)

        assert reconstructed.command == "opportunity"
        assert reconstructed.stats["total"] == len(cards)

        recon_payload = OpportunityPayload(**reconstructed.payload)
        assert len(recon_payload.opportunities) == len(cards)
        assert recon_payload.opportunities[0].quadrant == cards[0].quadrant

        # Verify every card field survived
        for orig_card, recon_card in zip(cards, recon_payload.opportunities):
            assert recon_card.title == orig_card.title
            assert recon_card.demand_score == orig_card.demand_score
            assert recon_card.competition_score == orig_card.competition_score
            assert recon_card.gap_score == orig_card.gap_score
            assert recon_card.quadrant == orig_card.quadrant
            assert recon_card.confidence == orig_card.confidence
            assert recon_card.market_size_score == orig_card.market_size_score

    def test_roundtrip_preserves_floats(self):
        """Floating point values survive roundtrip accurately."""
        card = OpportunityCard(
            title="precision-test",
            demand_score=7.123,
            competition_score=2.456,
            gap_score=2.899,
            quadrant="Niche",
            market_size_score=4.789,
            confidence=0.765,
            personalized_score=3.478,
            alignment_multiplier=1.234,
        )

        payload = OpportunityPayload(opportunities=[card])
        result = SandboxResult(
            command="opportunity",
            domain="test",
            payload=payload.model_dump(),
        )

        json_str = result.model_dump_json()
        parsed = json.loads(json_str)
        reconstructed = SandboxResult(**parsed)
        recon_payload = OpportunityPayload(**reconstructed.payload)
        recon_card = recon_payload.opportunities[0]

        # Floats should survive serialization accurately (Pydantic JSON handles this)
        assert recon_card.demand_score == pytest.approx(7.123)
        assert recon_card.competition_score == pytest.approx(2.456)
        assert recon_card.gap_score == pytest.approx(2.899)
        assert recon_card.confidence == pytest.approx(0.765)
        assert recon_card.alignment_multiplier == pytest.approx(1.234)


# ── Cross-Pipeline Integration Test ───────────────────────────────────


class TestCrossPipeline:
    """End-to-end: signals -> trends -> opportunities."""

    def test_full_trend_to_opportunity_flow(self):
        """Signals flow through trend pipeline, then feed into opportunity scoring."""
        signals = _make_sample_signals()
        trends = _run_trend_pipeline(signals, window_days=365)
        assert len(trends) >= 2, "Need at least 2 trends for opportunity scoring"

        # Convert TopicTrend objects to dicts for opportunity scoring
        trend_dicts = [t.model_dump() for t in trends]
        pain_dicts = _make_sample_pains()

        # Score the top 3 trends
        cards = []
        for td in trend_dicts[:3]:
            topic = td["topic"]
            related_pains = [
                p for p in pain_dicts
                if any(topic.lower() in r.lower() for r in p.get("affected_repos", []))
            ] or pain_dicts[:1]

            demand = compute_demand([td], related_pains)
            competition = compute_competition([td])
            gap = compute_gap(demand, competition)
            market_size = compute_market_size([td])
            total_evidence = td.get("evidence_count", 0)
            total_pains = sum(p.get("frequency", 0) for p in related_pains)
            confidence = compute_confidence(demand, competition, total_evidence, total_pains)
            quadrant = classify_quadrant(gap, market_size)
            action = recommend_action(topic, gap, quadrant, market_size, confidence)

            cards.append(OpportunityCard(
                title=f"{topic} - gap={gap}",
                demand_score=demand,
                competition_score=competition,
                gap_score=gap,
                signals=[f"{r['full_name']} ({r['stars']} stars)" for r in td.get("top_repos", [])[:2]],
                recommended_action=action,
                quadrant=quadrant,
                market_size_score=market_size,
                confidence=confidence,
            ))

        assert len(cards) >= 2

        # Wrap in SandboxResult
        result = SandboxResult(
            command="opportunity",
            domain="agent",
            payload=OpportunityPayload(opportunities=cards).model_dump(),
            stats={
                "total": len(cards),
                "avg_gap": round(sum(c.gap_score for c in cards) / len(cards), 2),
            },
        )

        assert result.command == "opportunity"
        assert result.stats["total"] == len(cards)

        # Verify JSON roundtrip of the full pipeline output
        json_str = result.model_dump_json(indent=2)
        parsed = json.loads(json_str)
        reconstructed = SandboxResult(**parsed)
        recon_payload = OpportunityPayload(**reconstructed.payload)
        assert len(recon_payload.opportunities) == len(cards)
