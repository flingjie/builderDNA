"""Tests for the GitHub evidence adapter (concepts/adapters/github.py).

Covers the hard requirements:
- repo code/tests/releases -> implementation evidence.
- external-user issues/docs -> adoption evidence.
- stars/velocity are retrieval hints, NOT adoption evidence.
- a popular demo cannot independently satisfy adoption.
- URLs and provenance are preserved (source_url, note).
- independence_key separates implementation (per repo) from adoption (per external user).
"""
from datetime import datetime, timezone

from concepts.adapters.github import (
    classify_role,
    independence_key_for_signal,
    is_external_user,
    source_url_for,
    to_evidence,
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


def make_signal(signal_type, actor, target_repo="org/repo", **overrides) -> Signal:
    fields = dict(
        id=f"sig-{signal_type}",
        source="github",
        type=signal_type,
        actor=actor,
        target_repo=target_repo,
        timestamp=utc_now(),
    )
    fields.update(overrides)
    return Signal(**fields)


# ── role classification ──

class TestClassifyRole:
    def test_repo_created_is_implementation(self):
        sig = make_signal("repo_created", "org", velocity=100.0, impact=1.0)
        assert classify_role(sig) is EvidenceRole.IMPLEMENTATION

    def test_release_is_implementation(self):
        assert classify_role(make_signal("release", "org")) is EvidenceRole.IMPLEMENTATION

    def test_external_issue_is_adoption(self):
        sig = make_signal("issue_opened", "external_user", target_repo="org/repo")
        assert classify_role(sig) is EvidenceRole.ADOPTION

    def test_owner_issue_is_not_adoption(self):
        sig = make_signal("issue_opened", "org", target_repo="org/repo")
        assert classify_role(sig) is EvidenceRole.IMPLEMENTATION

    def test_external_discussion_is_adoption(self):
        sig = make_signal("discussion", "external_user", target_repo="org/repo")
        assert classify_role(sig) is EvidenceRole.ADOPTION

    def test_star_growth_and_fork_are_retrieval_hints(self):
        assert classify_role(make_signal("star_growth", "someone")) is None
        assert classify_role(make_signal("fork", "someone")) is None

    def test_external_override(self):
        sig = make_signal("issue_opened", "org", target_repo="org/repo")
        assert classify_role(sig, external=True) is EvidenceRole.ADOPTION


class TestIsExternalUser:
    def test_different_actor_is_external(self):
        sig = make_signal("issue_opened", "jane", target_repo="acme/tool")
        assert is_external_user(sig) is True

    def test_owner_actor_is_not_external(self):
        sig = make_signal("issue_opened", "acme", target_repo="acme/tool")
        assert is_external_user(sig) is False

    def test_unknown_actor_is_not_external(self):
        sig = make_signal("issue_opened", "", target_repo="acme/tool")
        assert is_external_user(sig) is False


# ── to_evidence ──

class TestToEvidence:
    def test_repo_created_is_implementation_direct(self):
        e = to_evidence(make_signal("repo_created", "org", velocity=500.0), "agent-reliability")
        assert e is not None
        assert e.role is EvidenceRole.IMPLEMENTATION
        assert e.directness is Directness.DIRECT
        assert e.source_type is SourceType.GITHUB

    def test_popular_demo_cannot_satisfy_adoption(self):
        # High stars and velocity must NOT become adoption evidence.
        e = to_evidence(
            make_signal("repo_created", "org", velocity=999.0, impact=1.0),
            "agent-reliability",
        )
        assert e.role is EvidenceRole.IMPLEMENTATION
        assert e.role is not EvidenceRole.ADOPTION

    def test_star_growth_is_not_evidence(self):
        assert to_evidence(make_signal("star_growth", "someone", velocity=50.0), "c1") is None
        assert to_evidence(make_signal("fork", "someone"), "c1") is None

    def test_external_issue_is_adoption(self):
        e = to_evidence(
            make_signal("issue_opened", "jane", target_repo="acme/tool", payload={
                "html_url": "https://github.com/acme/tool/issues/12",
                "body": "We use this in production and it broke after upgrade.",
            }),
            "agent-reliability",
        )
        assert e.role is EvidenceRole.ADOPTION
        assert e.directness is Directness.DIRECT
        assert e.strength is EvidenceStrength.MODERATE
        assert "[adoption: external user jane]" in e.note

    def test_release_is_strong_implementation(self):
        e = to_evidence(make_signal("release", "org", payload={"html_url": "https://github.com/org/repo/releases/tag/v1.0"}), "c1")
        assert e.role is EvidenceRole.IMPLEMENTATION
        assert e.strength is EvidenceStrength.STRONG

    def test_source_url_preserved_from_payload(self):
        e = to_evidence(
            make_signal("issue_opened", "jane", target_repo="acme/tool", payload={"html_url": "https://github.com/acme/tool/issues/12"}),
            "c1",
        )
        assert e.source_url == "https://github.com/acme/tool/issues/12"

    def test_source_url_falls_back_to_repo_url(self):
        e = to_evidence(make_signal("repo_created", "org", target_repo="acme/tool"), "c1")
        assert e.source_url == "https://github.com/acme/tool"

    def test_explicit_role_hint_override(self):
        e = to_evidence(make_signal("issue_opened", "jane", target_repo="acme/tool"), "c1", role="counterexample")
        assert e.role is EvidenceRole.COUNTER

    def test_retrieval_hint_never_becomes_adoption_even_with_role_hint(self):
        e = to_evidence(make_signal("star_growth", "someone"), "c1", role="adoption")
        assert e is None


# ── independence key / source URL helpers ──

class TestIndependenceKey:
    def test_implementation_key_is_repo_scoped(self):
        sig = make_signal("repo_created", "org", target_repo="Acme/Tool")
        assert independence_key_for_signal(sig) == "github:acme/tool"

    def test_adoption_key_is_per_external_user(self):
        sig = make_signal("issue_opened", "Jane", target_repo="acme/tool")
        assert independence_key_for_signal(sig) == "github:acme/tool:actor:jane"

    def test_two_issues_from_same_user_share_key(self):
        a = make_signal("issue_opened", "jane", target_repo="acme/tool")
        b = make_signal("issue_commented", "jane", target_repo="acme/tool")
        assert independence_key_for_signal(a) == independence_key_for_signal(b)


class TestSourceUrlFor:
    def test_payload_url_wins(self):
        sig = make_signal("release", "org", payload={"url": "https://github.com/org/repo/releases/tag/v2"})
        assert source_url_for(sig) == "https://github.com/org/repo/releases/tag/v2"

    def test_fallback(self):
        sig = make_signal("repo_created", "org", target_repo="org/repo")
        assert source_url_for(sig) == "https://github.com/org/repo"
