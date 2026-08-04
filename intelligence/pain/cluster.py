"""Pain clusterer — groups pain issues into clusters using HDBSCAN.

Migrated from backend/engine/pain.py (Phase 2) — replaces LLM-based
clustering with density-based HDBSCAN over issue embeddings.

Note: sklearn's BallTree (used internally by HDBSCAN) does not support
``cosine`` as a distance metric. Use ``euclidean`` with L2-normalised
embeddings for equivalent angular-distance behaviour, or pass
``algorithm="generic"`` for full metric support.
"""

import warnings

from hdbscan import HDBSCAN
import numpy as np


class PainClusterer:
    """Cluster pain issues by their semantic embeddings using HDBSCAN.

    Args:
        min_cluster_size: Minimum number of points to form a cluster.
        min_samples: Minimum points in a neighbourhood for core point.
        metric: Distance metric for HDBSCAN. Use ``euclidean`` (default)
            with L2-normalised embeddings for cosine-like behaviour.
            For true cosine distance, pass ``algorithm="generic"``
            to the HDBSCAN constructor instead.
    """

    def __init__(
        self,
        min_cluster_size: int = 3,
        min_samples: int = 2,
        metric: str = "euclidean",
    ):
        self.clusterer = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric=metric,
        )

    def fit(self, embeddings: list[list[float]]) -> dict[int, list[int]]:
        """Cluster embeddings and return label-to-index mapping.

        Args:
            embeddings: List of embedding vectors for each issue.

        Returns:
            Dictionary mapping cluster label (int) to list of issue indices.
            Noise points (label == -1) are excluded.
        """
        if len(embeddings) < self.clusterer.min_cluster_size:
            warnings.warn(f"Insufficient data for clustering: {len(embeddings)} < {self.clusterer.min_cluster_size}")
            return {}

        matrix = np.array(embeddings)
        labels = self.clusterer.fit_predict(matrix)

        clusters: dict[int, list[int]] = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue
            clusters.setdefault(int(label), []).append(idx)

        return clusters
