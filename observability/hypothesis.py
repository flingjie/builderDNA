"""Hypothesis tree lifecycle management.

Provides CRUD operations for state/hypotheses.json, pruning detection,
and session-start summary generation. Used by the builderdna skill
to track exploration state across conversations.

Usage:
    from observability.hypothesis import HypothesisManager

    hm = HypothesisManager()
    hm.add("Agent State Engine 存在市场机会", "agent",
           "opportunity分析 — gap_score=2.3", confidence=0.65)
    hm.add_evidence("hyp_001", "supporting", "collect → 3 related repos, avg stars up")
    hm.get_summary()  # → "2 exploring, 1 ready to validate"
    pruning = hm.check_pruning("hyp_001")  # → None or pruning proposal
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

HYPOTHESES_PATH = "state/hypotheses.json"

# Pruning thresholds — defaults, overridden by config.yaml if available
CONTRADICT_WINDOW = 3  # look at last N evidence entries
CONTRADICT_THRESHOLD = 2  # ≥ this many contradicting in window triggers pruning


def _load_observability_config() -> dict:
    """Load observability section from config.yaml. Returns {} on failure."""
    try:
        import yaml
        with open("config.yaml") as f:
            cfg = yaml.safe_load(f)
            return cfg.get("observability", {})
    except Exception:
        return {}


_obs_cfg = _load_observability_config()
EXPIRY_DAYS = _obs_cfg.get("expiry_days", 30)  # days after last update before expiry check


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days_ago(iso_date: str) -> float:
    """Days between an ISO date and now."""
    if not iso_date:
        return float("inf")
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return float("inf")


def _generate_id(nodes: list[dict]) -> str:
    """Generate the next hypothesis ID (hyp_001, hyp_002, ...)."""
    max_n = 0
    for n in nodes:
        nid = n.get("id", "")
        if nid.startswith("hyp_"):
            try:
                max_n = max(max_n, int(nid[4:]))
            except ValueError:
                pass
    return f"hyp_{max_n + 1:03d}"


class HypothesisManager:
    """Manages the hypothesis tree lifecycle."""

    def __init__(self, path: str = HYPOTHESES_PATH):
        self._path = Path(path)

    # ── Read / Write ─────────────────────────────────────────

    def _read(self) -> dict:
        """Read hypotheses.json. Returns skeleton if missing."""
        if not self._path.exists():
            return {"version": 1, "last_updated": "", "domain": "", "nodes": []}
        try:
            data = json.loads(self._path.read_text())
            data.setdefault("version", 1)
            data.setdefault("last_updated", "")
            data.setdefault("domain", "")
            data.setdefault("nodes", [])
            return data
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "last_updated": "", "domain": "", "nodes": []}

    def _write(self, data: dict) -> None:
        """Write hypotheses.json."""
        data["last_updated"] = _now_iso()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # ── Node CRUD ────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """Return all hypothesis nodes."""
        return self._read()["nodes"]

    def get(self, node_id: str) -> dict | None:
        """Get a single hypothesis by ID."""
        for n in self._read()["nodes"]:
            if n["id"] == node_id:
                return n
        return None

    def add(
        self,
        title: str,
        domain: str,
        source: str,
        confidence: float = 0.5,
    ) -> str:
        """Create a new hypothesis node. Returns the node ID."""
        data = self._read()
        node = {
            "id": _generate_id(data["nodes"]),
            "title": title,
            "domain": domain,
            "status": "exploring",
            "confidence": confidence,
            "source": source,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "evidence_log": [],
        }
        data["nodes"].append(node)
        if not data["domain"]:
            data["domain"] = domain
        self._write(data)
        return node["id"]

    def update_status(
        self,
        node_id: str,
        status: Literal["exploring", "validated", "pruned"],
        confidence: float | None = None,
    ) -> bool:
        """Update hypothesis status and optionally confidence. Returns True if found."""
        data = self._read()
        for n in data["nodes"]:
            if n["id"] == node_id:
                n["status"] = status
                if confidence is not None:
                    n["confidence"] = confidence
                n["updated_at"] = _now_iso()
                self._write(data)
                return True
        return False

    def add_evidence(
        self,
        node_id: str,
        etype: Literal["supporting", "contradicting"],
        summary: str,
    ) -> bool:
        """Add an evidence entry to a hypothesis. Returns True if found."""
        data = self._read()
        for n in data["nodes"]:
            if n["id"] == node_id:
                n.setdefault("evidence_log", []).append({
                    "date": _now_iso(),
                    "type": etype,
                    "summary": summary,
                })
                n["updated_at"] = _now_iso()
                self._write(data)
                return True
        return False

    # ── Pruning detection ────────────────────────────────────

    def check_pruning(self, node_id: str) -> dict | None:
        """Check if a hypothesis should be proposed for pruning.

        Returns a prune proposal dict with reason, or None if node is fine.
        Checks 3 conditions (any trigger returns a proposal):
          1. Evidence-based: last N entries have ≥N/2 contradicting
          2. Expiry: node not updated in EXPIRY_DAYS
          3. Stale validated: validated but untouched for EXPIRY_DAYS
        """
        node = self.get(node_id)
        if not node:
            return None
        if node["status"] == "pruned":
            return None  # already pruned

        evidence = node.get("evidence_log", [])
        updated = node.get("updated_at", node.get("created_at", ""))

        # Check 1: Evidence-based contradiction
        if len(evidence) >= CONTRADICT_WINDOW:
            recent = evidence[-CONTRADICT_WINDOW:]
            contradict_count = sum(1 for e in recent if e["type"] == "contradicting")
            if contradict_count >= CONTRADICT_THRESHOLD:
                return {
                    "node_id": node_id,
                    "title": node.get("statement", node.get("title", "")),
                    "reason": "evidence_contradiction",
                    "detail": f"{contradict_count}/{CONTRADICT_WINDOW} recent evidence entries contradict",
                    "severity": "high",
                }

        # Check 2: Stale validated (re-evaluate after shorter period)
        days_stale = _days_ago(updated)
        if node["status"] == "validated" and days_stale > EXPIRY_DAYS // 2:
            return {
                "node_id": node_id,
                "title": node.get("statement", node.get("title", "")),
                "reason": "stale_validated",
                "detail": f"Validated but untouched for {days_stale:.0f} days — re-evaluate?",
                "severity": "low",
            }

        # Check 3: Expiry (all nodes)
        if days_stale > EXPIRY_DAYS:
            return {
                "node_id": node_id,
                "title": node.get("statement", node.get("title", "")),
                "reason": "expired",
                "detail": f"Last updated {days_stale:.0f} days ago (threshold: {EXPIRY_DAYS})",
                "severity": "medium",
            }

        return None

    def check_all_pruning(self) -> list[dict]:
        """Check all hypotheses for pruning proposals."""
        proposals = []
        data = self._read()
        for n in data["nodes"]:
            proposal = self.check_pruning(n["id"])
            if proposal:
                proposals.append(proposal)
        return proposals

    # ── Session-start summary ─────────────────────────────────

    def get_summary(self) -> dict:
        """Generate a concise session-start summary of hypothesis state.

        Returns a dict with counts, ready-to-validate nodes, and pruning proposals.
        """
        data = self._read()
        nodes = data["nodes"]

        if not nodes:
            return {
                "total": 0,
                "summary_line": "",
                "exploring": 0,
                "validated": 0,
                "pruned": 0,
                "ready_to_validate": [],
                "pruning_proposals": [],
                "pending_prune_count": 0,
            }

        by_status = {"exploring": 0, "validated": 0, "pruned": 0}
        for n in nodes:
            by_status[n.get("status", "exploring")] = by_status.get(n.get("status", "exploring"), 0) + 1

        # Ready to validate: exploring with confidence >= 0.8
        ready = [
            {"id": n["id"], "title": n.get("statement", n.get("title", "")), "confidence": n["confidence"]}
            for n in nodes
            if n["status"] == "exploring" and n.get("confidence", 0) >= 0.8
        ]

        # Pruning proposals
        pruning = self.check_all_pruning()

        # Build summary line
        parts = []
        if by_status["exploring"] > 0:
            parts.append(f"{by_status['exploring']} exploring")
        if ready:
            parts.append(f"{len(ready)} ready to validate")
        if pruning:
            parts.append(f"{len(pruning)} prune proposals")

        summary_line = ", ".join(parts) if parts else f"all {by_status['validated']} validated"

        return {
            "total": len(nodes),
            "summary_line": summary_line,
            "exploring": by_status["exploring"],
            "validated": by_status["validated"],
            "pruned": by_status["pruned"],
            "ready_to_validate": ready,
            "pruning_proposals": pruning,
            "pending_prune_count": len(pruning),
        }
