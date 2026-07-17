"""L1 Insight Aggregator — rule-based Signal clustering.

Groups related Signals by topic co-occurrence using Jaccard similarity.
No LLM involved. Outputs SignalCluster objects for L2 processing.
"""

from collections import defaultdict

from models.signal import Signal, SignalCluster

JACCARD_THRESHOLD = 0.3
RECENT_WINDOW_DAYS = 30


def aggregate(signals: list[Signal], window_days: int = RECENT_WINDOW_DAYS) -> list[SignalCluster]:
    """Aggregate signals into clusters based on topic co-occurrence.

    Args:
        signals: All signals to cluster.
        window_days: Days to consider as "recent" for growth_rate.

    Returns:
        List of SignalCluster objects, sorted by total_weight descending.
    """
    if not signals:
        return []

    n = len(signals)
    signal_map = {i: signals[i] for i in range(n)}

    # Build topic→signal indices index
    topic_index: dict[str, set[int]] = defaultdict(set)
    for idx, s in enumerate(signals):
        for topic in s.meta.get("topics", []):
            topic_index[topic].add(idx)

    # Union-find
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Union signals sharing the same topic
    for indices in topic_index.values():
        idxs = list(indices)
        for i in range(1, len(idxs)):
            union(idxs[0], idxs[i])

    # Union by Jaccard similarity
    for i in range(n):
        topics_i = set(signals[i].meta.get("topics", []))
        if not topics_i:
            continue
        for j in range(i + 1, n):
            topics_j = set(signals[j].meta.get("topics", []))
            if not topics_j:
                continue
            inter = len(topics_i & topics_j)
            union_size = len(topics_i | topics_j)
            if union_size > 0 and inter / union_size >= JACCARD_THRESHOLD:
                union(i, j)

    # Collect clusters
    clusters_map: dict[int, list[int]] = defaultdict(list)
    for idx in range(n):
        clusters_map[find(idx)].append(idx)

    all_timestamps = [s.timestamp for s in signals]
    latest_ts = max(all_timestamps) if all_timestamps else None

    result: list[SignalCluster] = []
    for indices in clusters_map.values():
        cluster_signals = [signals[i] for i in indices]
        signal_ids = [s.id for s in cluster_signals]

        all_topics: set[str] = set()
        all_languages: set[str] = set()
        for s in cluster_signals:
            all_topics.update(s.meta.get("topics", []))
            lang = s.meta.get("language", "")
            if lang:
                all_languages.add(lang)

        total_weight = sum(s.weight for s in cluster_signals)

        timestamps = [s.timestamp for s in cluster_signals]
        time_span = int((max(timestamps) - min(timestamps)).total_seconds() / 86400) if timestamps else 0

        growth_rate = 0.0
        if latest_ts and total_weight > 0:
            recent_weight = sum(
                s.weight for s in cluster_signals
                if (latest_ts - s.timestamp).total_seconds() / 86400 <= window_days
            )
            growth_rate = recent_weight / total_weight

        result.append(SignalCluster(
            signals=signal_ids, topics=sorted(all_topics),
            languages=sorted(all_languages), total_weight=total_weight,
            time_span_days=time_span, growth_rate=round(growth_rate, 3),
        ))

    result.sort(key=lambda c: c.total_weight, reverse=True)
    return result
