"""Trend data models for BuilderDNA 2.0 Phase 1."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DomainConfig(BaseModel):
    name: str                              # "agent"
    topics: list[str]                      # ["mcp", "langchain", ...]
    window_days: int = 60


class RepoTrend(BaseModel):
    full_name: str                         # "modelcontextprotocol/servers"
    stars: int
    stars_delta: int = 0                   # 周期内新增
    forks: int
    contributors: int
    contributor_growth: float = 0.0        # 周期内增长率
    velocity: float = 0.0                  # stars/day
    trend_score: float = 0.0               # 综合趋势分
    days_since_first_release: int = 0      # 距离首次发布天数


class TopicTrend(BaseModel):
    topic: str
    stage: Literal["emerging", "accelerating", "mainstream", "declining"]
    confidence: float                      # 0-1
    growth_velocity: float                 # 聚合增速
    evidence_count: int                    # 支撑 repo 数量
    top_repos: list[RepoTrend] = Field(default_factory=list)


class TrendSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_days: int
    topics: list[TopicTrend] = Field(default_factory=list)
