"""Tests for L1 Insight Aggregator."""

from datetime import datetime, timezone

from models.signal import Signal
from insight.aggregator import aggregate


def _make_signal(id_, actor, type_, topics, language, weight):
    return Signal(
        id=id_, source="github", type=type_,
        timestamp=datetime(2026, 7, 15, tzinfo=timezone.utc),
        weight=weight, actor=actor, target=f"{actor}/repo_{id_}",
        meta={"language": language, "topics": topics, "description": ""}, raw={},
    )


class TestAggregate:
    def test_single_topic_cluster(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["llm"], "Python", 5.0),
            _make_signal("s2", "alice", "star", ["llm", "agent"], "Python", 1.0),
            _make_signal("s3", "alice", "commit", ["llm"], "Python", 3.0),
        ]
        clusters = aggregate(signals)
        llm_clusters = [c for c in clusters if "llm" in c.topics]
        assert len(llm_clusters) >= 1
        assert llm_clusters[0].total_weight == 9.0

    def test_multiple_disjoint_clusters(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["llm", "agent"], "Python", 5.0),
            _make_signal("s2", "alice", "repo", ["rust", "systems"], "Rust", 5.0),
        ]
        clusters = aggregate(signals)
        assert len(clusters) >= 2

    def test_empty_signals(self):
        assert aggregate([]) == []

    def test_cluster_fields_populated(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["llm", "agent"], "Python", 5.0),
            _make_signal("s2", "alice", "star", ["llm"], "Python", 1.0),
        ]
        clusters = aggregate(signals)
        for c in clusters:
            assert len(c.signals) > 0
            assert len(c.topics) > 0
            assert c.total_weight > 0
            assert 0.0 <= c.growth_rate <= 1.0
            assert c.time_span_days >= 0

    def test_language_grouping(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["web"], "Python", 5.0),
            _make_signal("s2", "alice", "star", ["web"], "JavaScript", 1.0),
        ]
        clusters = aggregate(signals)
        web_clusters = [c for c in clusters if "web" in c.topics]
        languages = set()
        for c in web_clusters:
            languages.update(c.languages)
        assert "Python" in languages
        assert "JavaScript" in languages
