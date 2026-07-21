"""Tests for opportunity store."""
from backend.models.opportunity import OpportunitySnapshot, OpportunityCard, OpportunityEvidence
from backend.store.opportunity_store import OpportunityStore


class TestOpportunityStore:
    def test_save_and_retrieve(self, tmp_path):
        store = OpportunityStore(str(tmp_path / "test.db"))
        snap = OpportunitySnapshot(
            domain="agent",
            cards=[
                OpportunityCard(
                    title="Agent Replay Visualizer",
                    why_now="Debugging agent runs is painful",
                    problem="No way to replay agent traces",
                    evidence=OpportunityEvidence(
                        trends=["mcp adoption"],
                        pain_clusters=["debugging"],
                        key_issues=["a/b#42"],
                        key_repos=["a/b"],
                    ),
                    existing_solutions=["manual logs"],
                    gap="No visual replay exists",
                    mvp="Build a trace viewer",
                    score=4.5,
                    risk="medium",
                ),
            ],
        )
        sid = store.save(snap)
        assert sid == snap.id

        loaded = store.get_latest("agent")
        assert loaded is not None
        assert loaded.domain == "agent"
        assert len(loaded.cards) == 1
        assert loaded.cards[0].title == "Agent Replay Visualizer"
        assert loaded.cards[0].score == 4.5
        assert loaded.cards[0].risk == "medium"
        assert loaded.cards[0].evidence.trends == ["mcp adoption"]

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = OpportunityStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None
