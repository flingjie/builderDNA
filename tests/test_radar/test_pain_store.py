"""Tests for pain store."""
from backend.models.pain import PainSnapshot, PainCluster, PainIssue
from backend.store.pain_store import PainStore


class TestPainStore:
    def test_save_and_retrieve(self, tmp_path):
        store = PainStore(str(tmp_path / "test.db"))
        snap = PainSnapshot(
            domain="agent",
            clusters=[
                PainCluster(
                    title="Agent State Debugging",
                    severity=4.2,
                    frequency=15,
                    description="Debugging agent state is hard",
                    evidence=[
                        PainIssue(
                            repo="a/b", issue_number=1,
                            title="state bug", body="desc",
                            comments=3, participants=2,
                            pain_score=4.0, labels=["bug"],
                            url="https://github.com/a/b/issues/1",
                        ),
                    ],
                    affected_repos=["a/b"],
                ),
            ],
            issue_count=15,
            repos_analyzed=["a/b", "c/d"],
        )
        sid = store.save(snap)
        assert sid == snap.id

        loaded = store.get_latest("agent")
        assert loaded is not None
        assert loaded.domain == "agent"
        assert len(loaded.clusters) == 1
        assert loaded.clusters[0].title == "Agent State Debugging"
        assert loaded.clusters[0].severity == 4.2
        assert loaded.issue_count == 15
        assert loaded.repos_analyzed == ["a/b", "c/d"]

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = PainStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None
