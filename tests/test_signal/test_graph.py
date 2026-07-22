"""Tests for SignalGraph (NetworkX)."""
from datetime import datetime, timezone
from signals.models import Signal
from signals.graph import SignalGraph


class TestSignalGraph:
    def test_builds_graph_from_signals(self):
        signals = [
            Signal(
                id="s1", source="github", type="repo_created",
                actor="dev1", target_repo="org/repo1",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "mcp"]},
            ),
            Signal(
                id="s2", source="github", type="repo_created",
                actor="dev2", target_repo="org/repo2",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "rag"]},
            ),
        ]
        graph = SignalGraph()
        graph.build_from_signals(signals)
        assert graph.node_count() > 0
        assert graph.edge_count() > 0

    def test_co_occurring_topics(self):
        signals = [
            Signal(
                id=f"s{i}", source="github", type="repo_created",
                actor="dev", target_repo=f"org/repo{i}",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "mcp"]},
            )
            for i in range(5)
        ] + [
            Signal(
                id=f"sa{i}", source="github", type="repo_created",
                actor="dev", target_repo=f"org/other{i}",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["rag", "vector"]},
            )
            for i in range(2)
        ]
        graph = SignalGraph()
        graph.build_from_signals(signals)
        pairs = graph.get_co_occurring_topics(min_weight=2)
        assert len(pairs) >= 1
        assert ("agent", "mcp") in pairs or ("mcp", "agent") in pairs

    def test_developer_influence(self):
        signals = []
        for i in range(10):
            signals.append(Signal(
                id=f"d1-{i}", source="github", type="repo_created",
                actor="influential_dev", target_repo=f"org/repo{i}",
                timestamp=datetime.now(timezone.utc), impact=0.9,
            ))
        for i in range(2):
            signals.append(Signal(
                id=f"d2-{i}", source="github", type="star_growth",
                actor="regular_dev", target_repo="org/other",
                timestamp=datetime.now(timezone.utc), impact=0.1,
            ))
        graph = SignalGraph()
        graph.build_from_signals(signals)
        inf = graph.get_developer_influence("influential_dev")
        reg = graph.get_developer_influence("regular_dev")
        assert inf > reg

    def test_find_bridging_repos(self):
        signals = [
            Signal(
                id="bridge", source="github", type="repo_created",
                actor="dev", target_repo="org/bridge",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "blockchain"]},
            ),
            Signal(
                id="agent-only", source="github", type="repo_created",
                actor="dev", target_repo="org/agent-tool",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent"]},
            ),
        ]
        graph = SignalGraph()
        graph.build_from_signals(signals)
        bridges = graph.find_bridging_repos("agent", "blockchain")
        assert "org/bridge" in bridges

    def test_empty_graph(self):
        graph = SignalGraph()
        graph.build_from_signals([])
        assert graph.node_count() == 0
        assert graph.get_co_occurring_topics(1) == []
        assert graph.find_bridging_repos("a", "b") == []
