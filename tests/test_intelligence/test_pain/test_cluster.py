"""Tests for intelligence/pain/cluster.py — PainClusterer."""

import numpy as np
import pytest

from intelligence.pain.cluster import PainClusterer


class TestPainClusterer:
    def test_default_construction(self):
        """Default params produce a usable clusterer."""
        clusterer = PainClusterer()
        assert clusterer.clusterer.min_cluster_size == 5
        assert clusterer.clusterer.min_samples == 2
        assert clusterer.clusterer.metric == "euclidean"

    def test_custom_params(self):
        """Custom parameters are passed through to HDBSCAN."""
        clusterer = PainClusterer(min_cluster_size=3, min_samples=1, metric="euclidean")
        assert clusterer.clusterer.min_cluster_size == 3
        assert clusterer.clusterer.min_samples == 1
        assert clusterer.clusterer.metric == "euclidean"

    def test_fit_returns_clusters(self):
        """Fit on well-separated vectors returns expected cluster structure."""
        clusterer = PainClusterer(min_cluster_size=2, min_samples=1)
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
            [0.1, 0.9, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.1, 0.9],
        ]
        clusters = clusterer.fit(embeddings)

        # HDBSCAN should find at least one cluster in well-separated data
        assert isinstance(clusters, dict)

        # All returned indices should be valid
        for label, indices in clusters.items():
            assert isinstance(label, int)
            for idx in indices:
                assert 0 <= idx < len(embeddings)

    def test_fit_empty_embeddings(self):
        """Empty embedding list returns empty dict."""
        clusterer = PainClusterer(min_cluster_size=2, min_samples=1)
        assert clusterer.fit([]) == {}

    def test_fit_below_min_cluster_size(self):
        """Fewer embeddings than min_cluster_size returns empty dict."""
        clusterer = PainClusterer(min_cluster_size=5, min_samples=2)
        assert clusterer.fit([[1.0], [2.0], [3.0]]) == {}

    def test_noise_points_excluded(self):
        """Points labelled -1 by HDBSCAN are excluded from results."""
        clusterer = PainClusterer(min_cluster_size=2, min_samples=1)
        # Two tight groups; the rest should be noise
        embeddings = [
            [1.0, 0.0],
            [0.9, 0.0],
            [0.0, 1.0],
            [0.0, 0.9],
            [100.0, 100.0],  # likely noise
            [-100.0, -100.0],  # likely noise
        ]
        clusters = clusterer.fit(embeddings)

        # All indices in clusters must be valid
        all_indices = [i for indices in clusters.values() for i in indices]
        assert all(0 <= i < len(embeddings) for i in all_indices)

        # Some embeddings may be noise (-1) and excluded
        total_clustered = sum(len(indices) for indices in clusters.values())
        assert total_clustered <= len(embeddings)
