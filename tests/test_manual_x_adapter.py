"""Tests for the manual X capture adapter (concepts/adapters/manual_x.py).

Covers the hard requirements:
- a manual note is INFERRED unless it quotes or links primary content.
- a verbatim quote of primary content is DIRECT; a link-only note is INDIRECT.
- repost chains share an independence_key when the upstream source is known.
- unavailable fields are stored as unknown and the coverage gap is explicit.
"""
from datetime import datetime, timezone

from concepts.adapters.manual_x import (
    independence_key,
    infer_directness,
    to_evidence,
    from_signal,
)
from models.concept import (
    Directness,
    EvidenceRole,
    EvidenceStrength,
    SourceType,
)
from signals.models import Signal


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── directness inference ──

class TestInferDirectness:
    def test_note_without_quoted_source_is_inferred(self):
        assert infer_directness("I think agents are getting more reliable", None) is Directness.INFERRED

    def test_verbatim_quote_is_direct(self):
        assert infer_directness('The author wrote "agents still lose state" in the issue', "https://x.com/u/status/1") is Directness.DIRECT

    def test_link_without_quote_is_indirect(self):
        assert infer_directness("Here is a link describing the failure", "https://x.com/u/status/1") is Directness.INDIRECT


# ── to_evidence ──

class TestToEvidence:
    def test_default_is_inferred_and_weak(self):
        e = to_evidence(
            concept_id="agent-reliability",
            url="https://x.com/author/status/1",
            author="author",
            note="I suspect agents will keep failing in production.",
        )
        assert e.source_type is SourceType.X
        assert e.role is EvidenceRole.PROBLEM
        assert e.directness is Directness.INFERRED
        assert e.strength is EvidenceStrength.WEAK

    def test_verbatim_quote_is_direct(self):
        e = to_evidence(
            concept_id="agent-reliability",
            url="https://x.com/author/status/1",
            author="author",
            note='Quoting the maintainer: "we still see silent state loss".',
            quoted_source_url="https://github.com/org/repo/issues/9",
        )
        assert e.directness is Directness.DIRECT
        assert e.strength is EvidenceStrength.MODERATE

    def test_link_only_is_indirect(self):
        e = to_evidence(
            concept_id="agent-reliability",
            url="https://x.com/author/status/1",
            author="author",
            note="People report this failure here.",
            quoted_source_url="https://github.com/org/repo/issues/9",
        )
        assert e.directness is Directness.INDIRECT

    def test_explicit_role_override(self):
        e = to_evidence(concept_id="c1", note="n", role="implementation")
        assert e.role is EvidenceRole.IMPLEMENTATION

    def test_explicit_directness_override(self):
        e = to_evidence(concept_id="c1", note="n", directness="l1")
        assert e.directness is Directness.DIRECT


# ── independence keys / repost chains ──

class TestIndependenceKey:
    def test_repost_chain_shares_key_from_upstream(self):
        k1 = independence_key(
            url="https://x.com/reposter/status/2",
            upstream_origin="https://x.com/original/status/1",
        )
        k2 = independence_key(
            url="https://x.com/another_reposter/status/3",
            upstream_origin="https://x.com/original/status/1",
        )
        assert k1 == k2 == "x:x.com/original/status/1"

    def test_quoted_source_is_the_anchor_when_no_upstream(self):
        k = independence_key(
            url="https://x.com/u/status/9",
            quoted_source_url="https://github.com/org/repo/issues/9",
        )
        assert k == "x:github.com/org/repo/issues/9"

    def test_own_url_when_no_upstream_or_quote(self):
        k = independence_key(url="https://x.com/u/status/9")
        assert k == "x:x.com/u/status/9"


# ── coverage gaps for unavailable fields ──

class TestCoverageGaps:
    def test_missing_author_and_url_are_recorded(self):
        e = to_evidence(concept_id="c1", url="", author="", note="Agents seem flaky.")
        assert e.source_url == ""
        assert "[coverage gap: author unknown; source URL unknown]" in e.note

    def test_present_fields_have_no_gap(self):
        e = to_evidence(concept_id="c1", url="https://x.com/u/status/1", author="u", note="Agents seem flaky.")
        assert "coverage gap" not in e.note

    def test_no_url_still_has_source_type_x(self):
        e = to_evidence(concept_id="c1", note="manual note")
        assert e.source_type is SourceType.X


# ── Signal bridge ──

class TestFromSignal:
    def test_maps_signal_hints(self):
        sig = Signal(
            id="sig-x",
            source="x",
            type="note",
            actor="author",
            target_repo="https://x.com/author/status/1",
            timestamp=utc_now(),
            evidence_role="problem",
            directness="l2",
            strength=0.4,
            payload={
                "note": 'They said "agents fail" here.',
                "quoted_source_url": "https://github.com/org/repo/issues/9",
            },
        )
        e = from_signal(sig, "agent-reliability")
        assert e.source_type is SourceType.X
        assert e.directness is Directness.INDIRECT  # explicit l2 hint wins
        assert e.strength is EvidenceStrength.MODERATE
        assert e.role is EvidenceRole.PROBLEM

    def test_signal_without_url_gets_inferred(self):
        sig = Signal(
            id="sig-x",
            source="manual",
            type="note",
            actor="",
            target_repo="",
            timestamp=utc_now(),
        )
        e = from_signal(sig, "agent-reliability")
        assert e.directness is Directness.INFERRED
        assert "author unknown" in e.note
