"""Pipeline — orchestrates the full Collect→Understand→Recommend flow."""

from pathlib import Path
from typing import Any

from config import Config
from collect.github.client import GitHubClient
from collect.github.mapper import map_all
from collect.store import SignalStore
from insight.aggregator import aggregate
from insight.classifier import classify
from opportunity.detector import detect
from opportunity.evaluator import evaluate
from llm.client import OpenAIClient


class Pipeline:
    """Orchestrates the BuilderDNA analysis pipeline."""

    def __init__(self, config: Config):
        self.config = config
        self.github = GitHubClient(token=config.github.token)
        self.llm = OpenAIClient(
            api_key=config.llm.api_key,
            model=config.llm.model,
            base_url=config.llm.base_url,
        )
        self.store = SignalStore(Path("snapshots") / "builderdna.db")

    def run(self, compare: bool = False) -> dict[str, Any]:
        """Execute the full analysis pipeline."""
        snapshot_id = self.store.create_snapshot(self.config.accounts)

        # Phase 1: Collect
        all_signals = self._collect_all(compare)

        if not all_signals:
            return {"snapshot_id": snapshot_id, "signals": [], "insights": [],
                    "opportunities": [], "diff": None}

        self.store.insert_signals(all_signals, snapshot_id)

        # Phase 2: Understand
        insights = self._run_understand(all_signals, compare, snapshot_id)

        # Phase 3: Recommend
        opportunities = self._run_recommend(insights, snapshot_id)

        # Diff
        diff = None
        if compare:
            last = self.store.get_last_snapshot()
            if last and last["id"] != snapshot_id:
                diff = self._compute_diff(all_signals, last)

        return {
            "snapshot_id": snapshot_id, "signals": all_signals,
            "insights": insights, "opportunities": opportunities, "diff": diff,
        }

    def _collect_all(self, compare: bool = False) -> list:
        since = None
        if compare:
            last = self.store.get_last_snapshot()
            if last:
                since = last["created_at"]
        all_signals = []
        for account in self.config.accounts:
            try:
                all_signals.extend(self._collect_for_account(account, since))
            except Exception as e:
                print(f"Warning: failed to collect for {account}: {e}")
                continue
        return all_signals

    def _collect_for_account(self, actor: str, since: str | None = None) -> list:
        raw_repos = self.github.get_repos(actor)
        raw_starred = self.github.get_starred(actor)
        raw_commits: dict[str, list] = {}
        for repo in raw_repos:
            full_name = repo.get("full_name", "")
            if full_name:
                try:
                    commits = self.github.get_commits(actor, full_name, since=since)
                    if commits:
                        raw_commits[full_name] = commits
                except Exception:
                    continue
        return map_all(
            raw_repos=raw_repos, raw_starred=raw_starred,
            raw_commits_by_repo=raw_commits, actor=actor,
            repo=self.config.weights.repo, star=self.config.weights.star,
            commit=self.config.weights.commit,
        )

    def _run_understand(self, signals: list, compare: bool, snapshot_id: str) -> list:
        clusters = aggregate(signals)
        self.store.insert_signal_clusters([c.model_dump() for c in clusters], snapshot_id)
        previous = None
        if compare:
            last = self.store.get_last_snapshot()
            if last and last["id"] != snapshot_id:
                previous = self.store.get_insights(last["id"])
        actor = self.config.accounts[0] if self.config.accounts else "unknown"
        insights = classify(clusters, self.llm, actor, previous)
        self.store.insert_insights([i.model_dump() for i in insights], snapshot_id)
        return insights

    def _run_recommend(self, insights: list, snapshot_id: str) -> list:
        if not insights:
            return []
        opportunities = detect(insights, self.llm)
        opportunities = evaluate(opportunities)
        self.store.insert_opportunities([o.model_dump() for o in opportunities], snapshot_id)
        return opportunities

    def _compute_diff(self, signals: list, last_snapshot: dict) -> dict:
        previous_signals = self.store.get_signals_since("1970-01-01")

        new_by_type: dict[str, int] = {}
        prev_by_type: dict[str, int] = {}
        for s in signals:
            new_by_type[s.type] = new_by_type.get(s.type, 0) + 1
        for s in previous_signals:
            prev_by_type[s.type] = prev_by_type.get(s.type, 0) + 1

        new_topic_weight: dict[str, float] = {}
        prev_topic_weight: dict[str, float] = {}
        for s in signals:
            for t in s.meta.get("topics", []):
                new_topic_weight[t] = new_topic_weight.get(t, 0) + s.weight
        for s in previous_signals:
            for t in s.meta.get("topics", []):
                prev_topic_weight[t] = prev_topic_weight.get(t, 0) + s.weight

        topic_changes = {}
        all_topics = set(new_topic_weight) | set(prev_topic_weight)
        for t in all_topics:
            prev_w = prev_topic_weight.get(t, 0)
            new_w = new_topic_weight.get(t, 0)
            change_pct = round((new_w - prev_w) / prev_w * 100, 1) if prev_w > 0 else 100.0
            topic_changes[t] = {"previous": prev_w, "current": new_w, "change_pct": change_pct}

        return {
            "new_signals": len(signals) - len(previous_signals),
            "total_signals": len(signals),
            "signals_by_type": {"previous": prev_by_type, "current": new_by_type},
            "topic_weight_changes": topic_changes,
            "previous_snapshot_id": last_snapshot["id"],
        }
