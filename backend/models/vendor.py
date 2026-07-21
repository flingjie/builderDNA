"""Vendor data models -- tracking GitHub organizations/accounts as vendors."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class VendorSignal(BaseModel):
    """A single activity signal from a vendor."""
    type: str                                    # "new_repo", "star_growth", "release", "member_starred"
    repo: str = ""                               # related repo full_name
    timestamp: str = ""                          # ISO timestamp


class VendorDirection(BaseModel):
    """A technology direction the vendor is actively investing in."""
    topic: str                                   # e.g. "agent-framework"
    intensity: float = 0.0                       # 0.0-1.0, how heavily invested
    trend: Literal["↑", "→", "↓"] = "→"


class VendorProfile(BaseModel):
    """A vendor's complete tracked profile."""
    name: str                                    # GitHub org name, e.g. "deepseek-ai"
    display_name: str = ""                       # Friendly name, e.g. "DeepSeek"
    accounts: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)  # ["🇨🇳 国产", "大模型"]
    comparison_group: str = ""                   # "domestic" | "overseas"
    active_directions: list[VendorDirection] = Field(default_factory=list)
    recent_signals: list[VendorSignal] = Field(default_factory=list)
    total_public_repos: int = 0
    total_stars: int = 0


class VendorSnapshot(BaseModel):
    """A snapshot of all vendor profiles at a point in time."""
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_days: int = 60
    profiles: list[VendorProfile] = Field(default_factory=list)


class VendorDiff(BaseModel):
    """Comparison between domestic and overseas vendors on one dimension."""
    dimension: str                               # topic name
    domestic_summary: str = ""                   # LLM-generated: what domestic vendors are doing
    overseas_summary: str = ""                   # LLM-generated: what overseas vendors are doing
    common_patterns: str = ""                    # shared patterns
    domestic_vendors: list[str] = Field(default_factory=list)
    overseas_vendors: list[str] = Field(default_factory=list)
