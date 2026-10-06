"""Request spec, fingerprinting, and run-ID generation for repo-evolution-learning.

``request.yaml`` in a run workspace holds a :class:`RequestSpec`. The spec
fingerprint is what ``resume`` checks: any change to the request fails a resume
closed rather than silently continuing under different inputs.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field, ValidationError

from config import RepoLearningLimits, RepoLearningPromotion

__all__ = [
    "RequestError",
    "RequestOutput",
    "RequestSpec",
    "request_hash",
    "generate_run_id",
    "parse_repo_ref",
    "load_request",
    "save_request",
]


class RequestError(Exception):
    """Raised for an invalid or missing request spec."""


class RequestOutput(BaseModel):
    """Output preferences for the report (spec §3 ``output``)."""

    format: str = Field(default="interactive_html", description="Report format")
    language: str = Field(default="zh-CN", description="Report language code")
    standalone: bool = Field(default=True, description="Self-contained single file")
    writing_reference: str = Field(default="ASD-STE100", description="Writing reference")
    compliance: str = Field(
        default="principles_adapted_for_chinese",
        description="How the writing reference is applied",
    )


class RequestSpec(BaseModel):
    """The resolved inputs for one repo-evolution-learning run (spec §3)."""

    repo: str = Field(min_length=1, description="GitHub repo URL or owner/repo")
    entry_url: str | None = Field(default=None, description="Optional PR/Issue URL")
    focus: str | None = Field(default=None, description="Optional feature/dir/design-question focus")
    learning_goal: str = Field(
        default="学习开发取舍与传播方法", description="The learning goal"
    )
    mode: Literal["report", "guided"] = Field(default="report", description="report / guided")
    depth: Literal["single_episode", "feature_history"] = Field(
        default="single_episode", description="Analysis depth"
    )
    target_project: str | None = Field(default=None, description="Optional migration target")
    development_period: str | None = Field(default=None, description="Development analysis window")
    promotion_period: str | None = Field(default=None, description="Promotion search window")
    promotion_research: RepoLearningPromotion = Field(default_factory=RepoLearningPromotion)
    limits: RepoLearningLimits = Field(default_factory=RepoLearningLimits)
    output: RequestOutput = Field(default_factory=RequestOutput)

    @property
    def owner(self) -> str:
        return parse_repo_ref(self.repo)[0]

    @property
    def name(self) -> str:
        return parse_repo_ref(self.repo)[1]

    @property
    def full_name(self) -> str:
        owner, name = parse_repo_ref(self.repo)
        return f"{owner}/{name}"


# ── URL parsing ──

_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([^/?#]+)/([^/?#]+)", re.IGNORECASE
)
_SHORT_REF_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")


def parse_repo_ref(repo: str) -> tuple[str, str]:
    """Return ``(owner, name)`` from a GitHub URL or ``owner/name`` short form.

    Strips any trailing ``/pull/<n>``, ``/issues/<n>``, ``/tree/…`` path, so a PR
    or issue URL yields its owning repo. Raises :class:`RequestError` on failure.
    """
    m = _GITHUB_URL_RE.match(repo.strip())
    if m:
        return m.group(1).lower(), m.group(2).lower()
    m = _SHORT_REF_RE.match(repo.strip())
    if m:
        return m.group(1).lower(), m.group(2).lower()
    raise RequestError(
        f"cannot parse repo from {repo!r}; use https://github.com/owner/repo or owner/repo"
    )


# ── Fingerprint ──


def _canonicalize(value):
    """Recursively sort dict keys so equal structures serialize identically."""
    if isinstance(value, dict):
        return {key: _canonicalize(val) for key, val in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def request_hash(request: RequestSpec) -> str:
    """Return a deterministic SHA-256 hex digest of the request spec."""
    data = _canonicalize(request.model_dump(mode="json"))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_run_id(repo: str) -> str:
    """A unique, filesystem-safe run id derived from the repo name."""
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    owner, name = parse_repo_ref(repo)
    safe = f"{owner}-{name}"
    return f"{safe}-{stamp}-{uuid4().hex[:6]}"


# ── Load / save ──


def load_request(run_dir: Path) -> RequestSpec:
    """Load and validate ``request.yaml`` from a run workspace."""
    path = run_dir / "request.yaml"
    if not path.exists():
        raise RequestError(f"request.yaml not found in {run_dir}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RequestError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RequestError(f"{path} must be a YAML mapping")
    try:
        return RequestSpec.model_validate(raw)
    except ValidationError as exc:
        raise RequestError(f"invalid request spec in {path}: {exc}") from exc


def save_request(run_dir: Path, request: RequestSpec) -> Path:
    """Write ``request.yaml`` into the run workspace (atomic)."""
    from repo_learning.workspace import atomic_write_json

    path = run_dir / "request.yaml"
    atomic_write_json(path, request.model_dump(mode="json"))
    return path
