"""Signal Graph — NetworkX-based relationship graph for BuilderDNA signals.

Builds a MultiDiGraph from Signal collections. Supports:
- Co-occurring topic detection
- Bridging repo discovery (repos connecting two distinct topics)
- Developer influence scoring via PageRank
- Subgraph export for individual engines
"""
from collections import defaultdict

import networkx as nx


class SignalGraph:
    """In-memory NetworkX MultiDiGraph built from Signal collections.

    Not persisted — rebuilt each run from Signal Lake. Signal Lake (DuckDB/SQLite)
    is the source of truth. The graph is an in-memory index for relationship queries.
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def build_from_signals(self, signals: list) -> None:
        """Build the full graph from signal list.

        Adds nodes for developers, repos, topics.
        Adds edges for CREATES, STARS, BELONGS_TO relationships.
        """
        self.graph.clear()

        # Track edge weights for co-occurrence
        topic_co_occurrence: dict[tuple[str, str], int] = defaultdict(int)
        repo_topics: dict[str, set[str]] = defaultdict(set)

        for sig in signals:
            # Ensure nodes exist
            if sig.actor and sig.actor not in self.graph:
                self.graph.add_node(sig.actor, kind="developer")
            if sig.target_repo and sig.target_repo not in self.graph:
                self.graph.add_node(sig.target_repo, kind="repo")

            # Developer → Repo edges
            if sig.type == "repo_created":
                self.graph.add_edge(sig.actor, sig.target_repo, kind="CREATES", weight=1.0)
            elif sig.type == "star_growth":
                self.graph.add_edge(sig.actor, sig.target_repo, kind="STARS", weight=sig.impact)

            # Topic nodes from payload
            topics = sig.payload.get("topics", [])
            for topic in topics:
                if topic not in self.graph:
                    self.graph.add_node(topic, kind="topic")
                self.graph.add_edge(sig.target_repo, topic, kind="BELONGS_TO", weight=sig.velocity)
                repo_topics[sig.target_repo].add(topic)

            # Co-occurrence: every pair of topics on the same signal
            topic_list = list(topics)
            for i in range(len(topic_list)):
                for j in range(i + 1, len(topic_list)):
                    pair = tuple(sorted([topic_list[i], topic_list[j]]))
                    topic_co_occurrence[pair] += 1

        # Store co-occurrence on graph for fast lookup
        for (t1, t2), weight in topic_co_occurrence.items():
            self.graph.add_edge(t1, t2, kind="CO_OCCURS", weight=weight)

        # Store repo-topic index on graph
        self.graph.graph["repo_topics"] = dict(repo_topics)

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def get_co_occurring_topics(self, min_weight: int = 3) -> list[tuple[str, str]]:
        """Return topic pairs that frequently appear together."""
        result = []
        for u, v, data in self.graph.edges(data=True):
            if data.get("kind") == "CO_OCCURS" and data.get("weight", 0) >= min_weight:
                result.append((u, v))
        return result

    def find_bridging_repos(self, topic_a: str, topic_b: str) -> list[str]:
        """Find repos that have BOTH of the given topics."""
        repo_topics = self.graph.graph.get("repo_topics", {})
        return [
            repo for repo, topics in repo_topics.items()
            if topic_a in topics and topic_b in topics
        ]

    def get_developer_influence(self, login: str) -> float:
        """Compute developer influence via PageRank on the undirected graph.

        Uses undirected PageRank so that rank flows bidirectionally between
        developers, repos, and topics via all relationship edges.
        """
        if self.graph.number_of_nodes() == 0:
            return 0.0
        try:
            # Convert to undirected so rank flows back to developers
            # (directed MultiDiGraph has no edges pointing toward devs)
            undirected = nx.Graph(self.graph)
            pr = nx.pagerank(undirected, weight="weight")
            return round(pr.get(login, 0.0), 4)
        except Exception:
            return 0.0

    def export_for_engine(self, engine: str) -> dict:
        """Export relevant subgraph data for a specific engine.

        Args:
            engine: "trend" | "pain" | "opportunity"

        Returns:
            dict with engine-specific data.
        """
        if engine == "trend":
            return {
                "co_occurring_topics": self.get_co_occurring_topics(min_weight=2),
                "topic_count": sum(1 for n, d in self.graph.nodes(data=True) if d.get("kind") == "topic"),
            }
        elif engine == "opportunity":
            repo_topics = self.graph.graph.get("repo_topics", {})
            return {
                "repo_count": len(repo_topics),
                "bridging_repos": [
                    (repo, list(topics))
                    for repo, topics in repo_topics.items()
                    if len(topics) >= 2
                ][:10],
            }
        return {}
