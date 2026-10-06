"""Data contracts for repo-evolution-learning.

These Pydantic models are the authoritative machine contract the orchestration
skill reads and writes: ``SourceRecord`` / ``SearchRecord`` lines in the run
workspace, and the ``Analysis`` root in ``analysis.json``. They mirror the human
description in ``.claude/skills/repo-evolution-learning/references/output-contract.md``.

Design rules enforced structurally here:

- All timestamps are timezone-aware UTC (``UtcDatetime`` from ``models.concept``).
- Unknown timestamps are ``None`` — never ``0`` and never an empty string.
- Closed sets are ``str, Enum``.
- Every record written to JSONL carries a stable ``id`` (``state/jsonl.py``
  deduplicates on ``.id``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from models.concept import UtcDatetime

__all__ = [
    "EvidenceStatus",
    "FetchStatus",
    "ActorType",
    "RepoMatch",
    "Relation",
    "StageStatus",
    "Platform",
    "SourceKind",
    "SmallExperiment",
    "SourceRef",
    "RepoIdentity",
    "SourceRecord",
    "SearchRecord",
    "Claim",
    "Episode",
    "PromotionContent",
    "FeedbackLink",
    "LearningCard",
    "RunManifest",
    "Analysis",
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ──


class EvidenceStatus(str, Enum):
    """How well a claim is supported by collected material."""

    SOURCED = "sourced"      # material directly supports the statement
    INFERRED = "inferred"    # analyst's reconstruction, not stated by material
    UNKNOWN = "unknown"      # neither sourced nor confidently inferred


class FetchStatus(str, Enum):
    """Whether a source body was fully fetched."""

    FULL = "full"
    PARTIAL = "partial"      # summary only, or truncated
    BLOCKED = "blocked"      # access limited (login wall, paywall)
    FAILED = "failed"        # fetch errored


class ActorType(str, Enum):
    """Who authored a piece of promotion content."""

    AUTHOR = "author"
    CONTRIBUTOR = "contributor"
    THIRD_PARTY = "third_party"
    USER = "user"
    UNKNOWN = "unknown"


class RepoMatch(str, Enum):
    """Whether content's subject matches the analysed repo."""

    CONFIRMED = "confirmed"    # link / homepage / author relation confirms identity
    PROBABLE = "probable"      # same name, no strong confirmation
    REJECTED = "rejected"      # same-name different project


class Relation(str, Enum):
    """How strongly public feedback links to later development."""

    EXPLICIT = "explicit"        # development record cites the feedback, or the author says so
    POSSIBLE = "possible"        # topic and timing match, no direct citation
    UNCONFIRMED = "unconfirmed"  # only temporal order, or insufficient material


class StageStatus(str, Enum):
    """Lifecycle status of one run stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class Platform(str, Enum):
    """A promotion-content platform."""

    X = "x"
    HACKER_NEWS = "hackernews"
    REDDIT = "reddit"
    LINKEDIN = "linkedin"
    PRODUCT_HUNT = "producthunt"
    V2EX = "v2ex"
    JUEJIN = "juejin"
    ZHIHU = "zhihu"
    WECHAT = "wechat"
    XIAOHONGSHU = "xiaohongshu"
    DEV = "dev"
    MEDIUM = "medium"
    BLOG = "blog"
    OTHER = "other"


class SourceKind(str, Enum):
    """What kind of material a :class:`SourceRecord` holds."""

    GITHUB_REPO = "github_repo"
    GITHUB_README = "github_readme"
    GITHUB_PR = "github_pr"
    GITHUB_ISSUE = "github_issue"
    GITHUB_REVIEW = "github_review"
    GITHUB_REVIEW_COMMENT = "github_review_comment"
    GITHUB_ISSUE_COMMENT = "github_issue_comment"
    GITHUB_COMMIT = "github_commit"
    GITHUB_DIFF = "github_diff"
    GITHUB_FILE = "github_file"
    WEB_ARTICLE = "web_article"
    WEB_DISCUSSION = "web_discussion"
    SEARCH_RESULT = "search_result"


# ── Small experiment ──


class SmallExperiment(BaseModel):
    """A bounded, falsifiable migration experiment (spec §6-H)."""

    hypothesis: str = Field(min_length=1, description="The falsifiable hypothesis to test")
    minimal_change: str = Field(min_length=1, description="The smallest change that tests it")
    observe_method: str = Field(min_length=1, description="How to observe the result")
    stop_condition: str = Field(min_length=1, description="Bounded stop condition (time or cost)")


# ── Source references ──


class SourceRef(BaseModel):
    """A pointer into collected material supporting a statement."""

    source_id: str = Field(min_length=1, description="ID of the SourceRecord this points to")
    locator: str = Field(
        default="",
        description="Comment ID, commit SHA, line range, or body paragraph ID",
    )
    excerpt: str = Field(default="", description="Quoted or paraphrased supporting text")
    supports: list[str] = Field(
        default_factory=list,
        description="Short labels of what this ref supports",
    )


# ── Identity ──


class RepoIdentity(BaseModel):
    """Confirmed identity of the analysed repository."""

    owner: str = Field(min_length=1, description="GitHub owner (org or user)")
    name: str = Field(min_length=1, description="Repository name")
    canonical_url: str = Field(min_length=1, description="Canonical https://github.com/owner/repo")
    project_names: list[str] = Field(
        default_factory=list, description="Aliases and historical names"
    )
    author_accounts: list[str] = Field(
        default_factory=list, description="Public accounts of the author(s)"
    )
    website: str = Field(default="", description="Official website, when known")
    identity_evidence: list[SourceRef] = Field(
        default_factory=list, description="Sources backing the identity relationships"
    )


# ── Sources ──


class SourceRecord(BaseModel):
    """One collected piece of material (GitHub object or fetched web content)."""

    id: str = Field(min_length=1, description="Stable record ID (dedup key)")
    kind: SourceKind = Field(description="What kind of material this holds")
    url: str = Field(default="", description="Original URL")
    canonical_url: str = Field(default="", description="Canonical URL (tracking params stripped)")
    author: str = Field(default="", description="Author handle or name")
    published_at: UtcDatetime | None = Field(
        default=None, description="When the material was published (None = unknown)"
    )
    fetched_at: UtcDatetime = Field(
        default_factory=_now_utc, description="When this record was fetched (UTC)"
    )
    body: str = Field(default="", description="Full or partial body text")
    fetch_status: FetchStatus = Field(
        default=FetchStatus.FULL, description="Whether the body was fully fetched"
    )
    missing_scope: list[str] = Field(
        default_factory=list, description="What was not fetched (comments, scores, …)"
    )
    content_hash: str = Field(
        default="", description="SHA-1 of the body, for repost dedup and fingerprinting"
    )


class SearchRecord(BaseModel):
    """One logged search-engine query and its results."""

    id: str = Field(min_length=1, description="Stable search-record ID")
    query: str = Field(min_length=1, description="The query string")
    engine: str = Field(min_length=1, description="Search engine / adapter used")
    searched_at: UtcDatetime = Field(
        default_factory=_now_utc, description="When the search ran (UTC)"
    )
    period: str = Field(default="", description="Search time range, when applicable")
    results: list[dict] = Field(
        default_factory=list, description="Result summaries (title, url, snippet)"
    )
    coverage_notes: list[str] = Field(
        default_factory=list, description="Coverage caveats (engine unavailable, etc.)"
    )


# ── Episode / claims ──


class Claim(BaseModel):
    """One statement about the episode, with its evidence status."""

    text: str = Field(min_length=1, description="The statement")
    evidence_status: EvidenceStatus = Field(
        default=EvidenceStatus.UNKNOWN, description="sourced / inferred / unknown"
    )
    source_refs: list[SourceRef] = Field(
        default_factory=list, description="Sources backing the statement"
    )
    limitations: list[str] = Field(
        default_factory=list, description="Known limits of the statement"
    )


class Episode(BaseModel):
    """One reconstructed development episode."""

    id: str = Field(min_length=1, description="Stable episode ID (e.g. pr-<number>)")
    title: str = Field(min_length=1, description="Short episode title")
    problem: str = Field(min_length=1, description="The problem the change addressed")
    constraints: list[str] = Field(
        default_factory=list, description="Constraints that shaped the design"
    )
    alternatives: list[Claim] = Field(
        default_factory=list, description="Alternatives considered (author-stated vs analyst-proposed)"
    )
    decisions: list[Claim] = Field(
        default_factory=list, description="Decisions made and their rationale"
    )
    implementation_changes: list[str] = Field(
        default_factory=list, description="Concrete changes made during review/implementation"
    )
    validation: list[Claim] = Field(
        default_factory=list, description="How the change was validated and its outcome"
    )
    outcome: str = Field(default="", description="Final outcome and its evidence")
    source_refs: list[SourceRef] = Field(
        default_factory=list, description="Sources backing the episode"
    )


# ── Promotion / feedback ──


class PromotionContent(BaseModel):
    """One analysed piece of promotion content."""

    id: str = Field(min_length=1, description="Stable content ID")
    source_id: str = Field(min_length=1, description="ID of the SourceRecord holding the body")
    platform: Platform = Field(default=Platform.OTHER, description="Platform it appeared on")
    actor_type: ActorType = Field(default=ActorType.UNKNOWN, description="Who authored it")
    repo_match: RepoMatch = Field(default=RepoMatch.CONFIRMED, description="Identity match confidence")
    content_type: str = Field(default="", description="Launch / release / tutorial / review / …")
    audience: str = Field(default="", description="Target audience")
    hook: str = Field(default="", description="Opening hook / framing")
    promise: str = Field(default="", description="Core promise to the reader")
    proof: str = Field(default="", description="Demonstration or evidence offered")
    call_to_action: str = Field(default="", description="What it asks the reader to do")


class FeedbackLink(BaseModel):
    """A link between public feedback and later development."""

    feedback_refs: list[SourceRef] = Field(
        default_factory=list, description="Feedback sources"
    )
    development_refs: list[SourceRef] = Field(
        default_factory=list, description="Development sources the feedback may have shaped"
    )
    relation: Relation = Field(
        default=Relation.UNCONFIRMED, description="explicit / possible / unconfirmed"
    )
    rationale: str = Field(min_length=1, description="Why this link is classified as it is")


# ── Learning card ──


class LearningCard(BaseModel):
    """A transferable takeaway with an applicable-condition and a small experiment."""

    problem: str = Field(min_length=1, description="The problem the lesson addresses")
    decision: str = Field(min_length=1, description="The decision / tradeoff made")
    tradeoff: str = Field(default="", description="What was sacrificed")
    applicable_when: str = Field(min_length=1, description="When the lesson applies")
    avoid_when: str = Field(default="", description="When it does not apply")
    small_experiment: SmallExperiment = Field(description="A bounded, falsifiable experiment")
    source_refs: list[SourceRef] = Field(
        default_factory=list, description="Sources backing the lesson"
    )


# ── Run manifest ──


class RunManifest(BaseModel):
    """The run checkpoint: request fingerprint, stage status, budgets, errors."""

    run_id: str = Field(min_length=1, description="Stable run ID")
    request_hash: str = Field(min_length=1, description="SHA-256 of the request spec")
    stage_status: dict[str, StageStatus] = Field(
        default_factory=dict, description="Per-stage status"
    )
    budgets_used: dict[str, int] = Field(
        default_factory=dict, description="Per-stage budget consumption"
    )
    errors: list[str] = Field(default_factory=list, description="Errors recorded during the run")
    report_path: str = Field(default="", description="Path to the rendered report")
    generated_at: UtcDatetime | None = Field(
        default=None, description="When the report was rendered (None = not yet)"
    )
    observation_cutoff: UtcDatetime | None = Field(
        default=None, description="Observation cutoff date for follow-up material"
    )


# ── Analysis root ──


class Analysis(BaseModel):
    """The skill-written analysis that ``validate`` checks and ``render`` turns into HTML."""

    schema_version: Literal[1] = Field(default=1, description="Analysis schema version")
    repo_identity: RepoIdentity = Field(description="Confirmed repo identity")
    episode: Episode = Field(description="The reconstructed episode (single, P0–P5)")
    claims: list[Claim] = Field(
        default_factory=list, description="Supplementary claims outside the episode"
    )
    promotion_contents: list[PromotionContent] = Field(
        default_factory=list, description="Analysed promotion content"
    )
    feedback_links: list[FeedbackLink] = Field(
        default_factory=list, description="Feedback↔development links"
    )
    learning_cards: list[LearningCard] = Field(
        default_factory=list, description="Transferable lessons"
    )
    platform_stats: list[dict] = Field(
        default_factory=list, description="Per-platform distribution stats with their scope"
    )
    coverage_notes: list[str] = Field(
        default_factory=list, description="Coverage caveats (missing material, truncation)"
    )
    generated_at: UtcDatetime = Field(
        default_factory=_now_utc, description="When the analysis was written (UTC)"
    )
