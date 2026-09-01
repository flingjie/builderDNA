"""Tests for the Reddit evidence adapter (concepts/adapters/reddit.py).

Covers the hard requirements:
- RSS title/body findings normalize to ConceptEvidence with role=problem.
- Directness is DIRECT only for a first-hand report; otherwise conservative INDIRECT.
- Comments are INDIRECT and only meaningful when read (comments_read signal).
- Linked primary artifacts are preserved as DIRECT.
- independence_key encodes independent communities + upstream links, not raw post count.
- Signal evidence_role/directness/strength hints map onto strict enums.
"""
from datetime import datetime, timezone

import pytest

from concepts.adapters.reddit import (
    RedditEvidence,
    comment_to_evidence,
    from_signal,
    independence_key_for_post,
    infer_directness,
    linked_artifact_to_evidence,
    post_to_evidence,
)
from models.concept import (
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    SourceType,
)
from signals.models import Signal


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def first_hand_post(**overrides) -> dict:
    post = {
        "id": "t3_abc123",
        "title": "Agents keep losing state between retries",
        "author": "dev_user",
        "permalink": "https://www.reddit.com/r/AI_Agents/comments/abc123/title/",
        "published": "2026-08-30T10:00:00Z",
        "selftext": "I keep losing state between retries and we cannot figure out why.",
        "category": "AI_Agents",
    }
    post.update(overrides)
    return post


def second_hand_post(**overrides) -> dict:
    post = {
        "id": "t3_xyz789",
        "title": "Weekly roundup of agent failures",
        "author": "aggregator_bot",
        "permalink": "https://www.reddit.com/r/LangChain/comments/xyz789/roundup/",
        "published": "2026-08-30T11:00:00Z",
        "selftext": "A summary of this week's posts about agents failing in production.",
        "category": "LangChain",
    }
    post.update(overrides)
    return post


# ── Directness inference ──

class TestInferDirectness:
    def test_first_person_report_is_direct(self):
        assert infer_directness(first_hand_post()) is Directness.DIRECT

    def test_second_hand_summary_is_indirect(self):
        assert infer_directness(second_hand_post()) is Directness.INDIRECT

    def test_unclear_post_defaults_to_indirect(self):
        post = first_hand_post(
            title="Agents fail in production",
            selftext="Multiple teams report agents failing during long runs.",
        )
        assert infer_directness(post) is Directness.INDIRECT

    def test_explicit_default_can_be_overridden(self):
        post = first_hand_post(
            title="Agents fail in production",
            selftext="Multiple teams report agents failing during long runs.",
        )
        assert infer_directness(post, default=Directness.DIRECT) is Directness.DIRECT


# ── post -> evidence ──

class TestPostToEvidence:
    def test_first_hand_post_role_and_directness(self):
        result = post_to_evidence(first_hand_post(), "agent-reliability")
        assert isinstance(result, RedditEvidence)
        e = result.evidence
        assert e.source_type is SourceType.REDDIT
        assert e.role is EvidenceRole.PROBLEM
        assert e.directness is Directness.DIRECT
        assert e.strength is EvidenceStrength.MODERATE
        assert e.source_url == first_hand_post()["permalink"]
        assert result.comments_read is False

    def test_comments_read_is_exposed(self):
        result = post_to_evidence(first_hand_post(), "agent-reliability", comments_read=True)
        assert result.comments_read is True
        # Default remains False for RSS-only import.
        assert post_to_evidence(first_hand_post(), "agent-reliability").comments_read is False

    def test_second_hand_post_is_indirect_and_weak(self):
        e = post_to_evidence(second_hand_post(), "agent-reliability").evidence
        assert e.directness is Directness.INDIRECT
        assert e.strength is EvidenceStrength.WEAK

    def test_explicit_role_override(self):
        e = post_to_evidence(first_hand_post(), "c1", role="counterexample").evidence
        assert e.role is EvidenceRole.COUNTER

    def test_explicit_directness_hint_maps_l1_l2_l3(self):
        assert (
            post_to_evidence(first_hand_post(), "c1", directness="l1").evidence.directness
            is Directness.DIRECT
        )
        assert (
            post_to_evidence(first_hand_post(), "c1", directness="l2").evidence.directness
            is Directness.INDIRECT
        )
        assert (
            post_to_evidence(first_hand_post(), "c1", directness="l3").evidence.directness
            is Directness.INFERRED
        )

    def test_requires_id_or_permalink(self):
        with pytest.raises(ValueError):
            post_to_evidence({"id": "", "permalink": ""}, "c1")

    def test_immutable_evidence(self):
        e = post_to_evidence(first_hand_post(), "c1").evidence
        with pytest.raises(Exception):
            e.directness = Directness.INDIRECT  # frozen model


# ── comments ──

class TestCommentToEvidence:
    def test_comment_is_always_indirect(self):
        post = first_hand_post()
        comment = {"id": "c1", "body": "same exact issue here", "permalink": "https://reddit.com/r/x/comments/abc123/c1"}
        e = comment_to_evidence(comment, "agent-reliability", post=post)
        assert e.directness is Directness.INDIRECT
        assert e.source_type is SourceType.REDDIT
        assert e.strength is EvidenceStrength.WEAK

    def test_comment_shares_parent_post_independence_key(self):
        post = first_hand_post()
        comment = {"id": "c1", "body": "same here", "permalink": "https://reddit.com/r/x/comments/abc123/c1"}
        e = comment_to_evidence(comment, "agent-reliability", post=post)
        assert e.independence_key == independence_key_for_post(post)

    def test_comment_requires_id(self):
        with pytest.raises(ValueError):
            comment_to_evidence({"id": ""}, "c1")


# ── linked primary artifacts ──

class TestLinkedArtifact:
    def test_linked_artifact_is_direct_primary(self):
        e = linked_artifact_to_evidence(
            "https://github.com/org/repo/issues/1", "agent-reliability"
        )
        assert e.directness is Directness.DIRECT
        assert e.source_type is SourceType.GITHUB
        assert e.role is EvidenceRole.IMPLEMENTATION
        assert e.independence_key == "upstream:github.com/org/repo/issues/1"

    def test_linked_artifact_requires_url(self):
        with pytest.raises(ValueError):
            linked_artifact_to_evidence("", "c1")


# ── independence keys / cross-community recurrence ──

class TestIndependenceKey:
    def test_same_upstream_claim_shares_key_across_communities(self):
        a = first_hand_post(
            linked_primary_url="https://github.com/org/repo/issues/1",
            permalink="https://reddit.com/r/AI_Agents/comments/a1/title/",
        )
        b = second_hand_post(
            linked_primary_url="https://github.com/org/repo/issues/1",
            permalink="https://reddit.com/r/LangChain/comments/b1/roundup/",
        )
        assert independence_key_for_post(a) == independence_key_for_post(b)
        assert independence_key_for_post(a) == "upstream:github.com/org/repo/issues/1"

    def test_independent_first_hand_posts_have_distinct_keys(self):
        a = first_hand_post(permalink="https://reddit.com/r/AI_Agents/comments/a1/title/")
        b = first_hand_post(
            id="t3_other",
            permalink="https://reddit.com/r/SaaS/comments/b1/title/",
        )
        assert independence_key_for_post(a) != independence_key_for_post(b)

    def test_raw_post_count_is_not_independence(self):
        # Five posts in the same community, none citing an upstream claim, are
        # five distinct keys — not collapsed by raw count.
        posts = [
            first_hand_post(id=f"t3_{i}", permalink=f"https://reddit.com/r/AI_Agents/comments/{i}/t/")
            for i in range(5)
        ]
        keys = {independence_key_for_post(p) for p in posts}
        assert len(keys) == 5


# ── Signal bridge ──

class TestFromSignal:
    def test_maps_signal_hints_onto_enums(self):
        sig = Signal(
            id="t3_abc123",
            source="reddit",
            type="signal",
            actor="dev_user",
            target_repo="https://www.reddit.com/r/AI_Agents/comments/abc123/title/",
            timestamp=utc_now(),
            evidence_role="problem",
            directness="l1",
            strength=0.9,
            payload={
                "title": "Agents keep losing state",
                "selftext": "I keep losing state between retries.",
            },
        )
        result = from_signal(sig, "agent-reliability")
        assert result.evidence.role is EvidenceRole.PROBLEM
        assert result.evidence.directness is Directness.DIRECT
        assert result.evidence.strength is EvidenceStrength.STRONG
        assert result.comments_read is False
