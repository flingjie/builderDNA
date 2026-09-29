"""Tests for scripts/replay_report.py — deterministic P3 metrics."""
import json

from investigations.models import ActionRecord, EvidenceRecord
from investigations.store import InvestigationStore
from scripts.replay_report import compute_metrics


def test_compute_metrics_counts_source_calls_and_independence(tmp_path):
    store = InvestigationStore(state_dir=tmp_path)
    from investigations.service import InvestigationService

    svc = InvestigationService(store, fetcher=lambda s, sort, limit: [])
    svc.init("onboarding automation", subreddit="SaaS")

    metrics = compute_metrics(store, "inv_1")
    assert metrics["source_calls"] == 0
    assert "independent_evidence_chains" in metrics
    assert "candidate_count" in metrics
    assert "counterevidence_actions" in metrics


def test_compute_metrics_reports_human_slots(tmp_path):
    store = InvestigationStore(state_dir=tmp_path)
    from investigations.service import InvestigationService
    svc = InvestigationService(store, fetcher=lambda s, sort, limit: [])
    svc.init("onboarding automation", subreddit="SaaS")
    metrics = compute_metrics(store, "inv_1")
    # human-annotation slots are present and empty
    for key in ("actionability_score", "useful_annotation"):
        assert key in metrics
        assert metrics[key] in ("", None)
