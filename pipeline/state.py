from typing import TypedDict, NotRequired
from signals.models import Signal


class AgentState(TypedDict):
    domain: str
    window_days: int
    mode: str                     # "full_auto" | "supervised" | "expert"
    signals: NotRequired[list[Signal]]
    topic_trends: NotRequired[list[dict]]
    pain_clusters: NotRequired[list[dict]]
    opportunities: NotRequired[list[dict]]
    critic_reviews: NotRequired[list[dict]]
    interrupt_triggered: NotRequired[bool]
    human_feedback: NotRequired[str]
    report_path: NotRequired[str]
