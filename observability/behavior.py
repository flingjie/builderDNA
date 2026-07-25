"""Behavior tracking and DNA mismatch detection.

Tracks user behavior (command invocations, output retention, config changes)
to behavior_log.jsonl and detects mismatches between stated User DNA values
and observed behavior patterns.

Usage:
    from observability.behavior import record_command, detect_mismatches

    # At end of each command:
    record_command(
        command="collect", domain="agent",
        flags={"verbose": 1, "quiet": False, "no_cache": False, "window": 365},
        output_path="output/signals.json", user_dna_used=True,
        elapsed_seconds=12.5, status="success",
    )

    # Triggered by skill or explicitly:
    mismatches = detect_mismatches()
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from observability.output import OutputLevel, vprint

BEHAVIOR_LOG_PATH = "state/behavior_log.jsonl"
MISMATCH_REPORT_PATH = "state/mismatch_report.json"
USER_DNA_PATH = "state/user_dna.json"
CONFIG_PATH = "config.yaml"
MISMATCH_THRESHOLD = 7  # events before auto-suggest

# Domain → output type mapping (reverse of OUTPUT_DOMAIN_MAP)
DOMAIN_OUTPUT_MAP: dict[str, str] = {
    "agent": "devtools",
    "devtools": "devtools",
    "consumer": "end_user",
    "fintech": "end_user",
    "infrastructure": "infrastructure",
    "knowledge": "knowledge",
}

# Commercial-leaning domain indicators (for reward/wealth detection)
COMMERCIAL_DOMAINS = {"fintech", "consumer", "enterprise", "saas", "b2b"}


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(filepath: str) -> None:
    """Ensure parent directory exists for a file path."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)


def _read_jsonl(path: str) -> list[dict]:
    """Read a JSONL file, returning list of parsed objects. Empty list if missing."""
    p = Path(path)
    if not p.exists():
        return []
    events = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _read_json(path: str) -> dict | None:
    """Read a JSON file. Returns None if missing or invalid."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _append_jsonl(path: str, event: dict) -> None:
    """Append one JSON object as a line to a JSONL file."""
    _ensure_dir(path)
    with open(path, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── Config change detection ──────────────────────────────────────

def _config_hash() -> str:
    """Compute MD5 hash of config.yaml content."""
    p = Path(CONFIG_PATH)
    if not p.exists():
        return ""
    return hashlib.md5(p.read_bytes()).hexdigest()


def detect_config_change() -> dict | None:
    """Detect if config.yaml has changed since last recorded hash.

    Returns a config_change event dict if changed, None otherwise.
    Compares current hash against the most recent config_change event
    in behavior_log.jsonl.
    """
    current_hash = _config_hash()
    if not current_hash:
        return None

    events = _read_jsonl(BEHAVIOR_LOG_PATH)
    last_hash = None
    for e in reversed(events):
        if e.get("event_type") == "config_change":
            last_hash = e.get("config_hash")
            break

    if last_hash is None:
        # First recording — always record baseline
        return {
            "timestamp": _now_iso(),
            "event_type": "config_change",
            "config_hash": current_hash,
            "change_type": "baseline",
        }

    if current_hash != last_hash:
        return {
            "timestamp": _now_iso(),
            "event_type": "config_change",
            "config_hash": current_hash,
            "previous_hash": last_hash,
            "change_type": "modified",
        }

    return None


# ── Command invocation tracking ─────────────────────────────────

def record_command(
    command: str,
    domain: str = "",
    flags: dict | None = None,
    output_path: str = "",
    user_dna_used: bool = False,
    elapsed_seconds: float = 0.0,
    status: str = "success",
) -> None:
    """Record a command invocation to behavior_log.jsonl.

    Args:
        command: CLI command name (collect, trend, pain, opportunity, report, config).
        domain: Domain argument (e.g. 'agent', 'devtools').
        flags: Dict of flag values (e.g. {'verbose': 1, 'quiet': False}).
        output_path: Path to the output file written by this command.
        user_dna_used: Whether User DNA personalization was active.
        elapsed_seconds: Total run time from RunTelemetry.
        status: 'success' or 'failure'.
    """
    event = {
        "timestamp": _now_iso(),
        "event_type": "command_invocation",
        "command": command,
        "domain": domain,
        "flags": flags or {},
        "output_path": output_path,
        "user_dna_used": user_dna_used,
        "elapsed_seconds": elapsed_seconds,
        "status": status,
    }
    _append_jsonl(BEHAVIOR_LOG_PATH, event)

    # Also detect config changes
    config_event = detect_config_change()
    if config_event:
        _append_jsonl(BEHAVIOR_LOG_PATH, config_event)

    # Check if we should suggest mismatch detection
    events = _read_jsonl(BEHAVIOR_LOG_PATH)
    cmd_count = sum(1 for e in events if e.get("event_type") == "command_invocation")
    if cmd_count > 0 and cmd_count % MISMATCH_THRESHOLD == 0:
        vprint(
            f"[dim]Behavior log: {cmd_count} commands recorded. "
            f"Consider checking for DNA mismatches.[/dim]",
            level=OutputLevel.VERBOSE,
        )


# ── Output retention ─────────────────────────────────────────────

def record_output_retention(output_path: str, referenced_by: str = "") -> None:
    """Record that an output file was created/retained.

    Called when a command writes an output file. 'referenced_by' indicates
    which downstream command consumed this file (if known).
    """
    event = {
        "timestamp": _now_iso(),
        "event_type": "output_retention",
        "output_path": output_path,
        "referenced_by": referenced_by,
    }
    _append_jsonl(BEHAVIOR_LOG_PATH, event)


# ── Mismatch detection ───────────────────────────────────────────

def _load_user_dna_values() -> dict | None:
    """Load User DNA values for mismatch comparison. Returns None if no DNA."""
    dna = _read_json(USER_DNA_PATH)
    if not dna or not dna.get("values"):
        return None
    return dna["values"]


def _map_domain_to_output(domain: str) -> str:
    """Map a CLI domain to an output value type."""
    return DOMAIN_OUTPUT_MAP.get(domain.lower(), "devtools")


def _map_command_to_activity(events: list[dict]) -> tuple[int, int]:
    """Count pipeline completions vs partial runs.

    A full pipeline completion: collect → trend → pain → opportunity → report
    (at least 3 of the 4 analysis commands present after a collect).

    Returns:
        (full_pipeline_runs, total_collect_runs)
    """
    # Group events by collect runs (each collect starts a pipeline window)
    cmd_sequence = [e["command"] for e in events if e.get("event_type") == "command_invocation"]

    full_runs = 0
    collect_runs = 0
    i = 0
    while i < len(cmd_sequence):
        if cmd_sequence[i] == "collect":
            collect_runs += 1
            # Look ahead for analysis commands before next collect
            analysis_count = 0
            j = i + 1
            while j < len(cmd_sequence) and cmd_sequence[j] != "collect":
                if cmd_sequence[j] in ("trend", "pain", "opportunity"):
                    analysis_count += 1
                j += 1
            if analysis_count >= 3:
                full_runs += 1
            i = j
        else:
            i += 1
    return full_runs, collect_runs


def _map_domain_to_commercial_score(events: list[dict]) -> float:
    """Calculate the fraction of domains that lean commercial (wealth signal)."""
    cmd_events = [e for e in events if e.get("event_type") == "command_invocation"]
    domains = [e.get("domain", "") for e in cmd_events if e.get("domain")]
    if not domains:
        return 0.0
    commercial_count = sum(1 for d in domains if d.lower() in COMMERCIAL_DOMAINS)
    return commercial_count / len(domains)


def detect_mismatches() -> list[dict]:
    """Detect mismatches between User DNA and observed behavior.

    Analyzes 3 dimensions:
      - Output: domain choices vs stated output preference (confidence 0.85+)
      - Activity: pipeline completion rate vs stated activity preference (confidence 0.6-0.75)
      - Reward: commercial domain frequency vs stated wealth score (confidence 0.5-0.6)

    Returns a list of mismatch dicts, each with:
      dimension, dna_value, behavior_signal, confidence, detail, suggested_question
    """
    dna = _load_user_dna_values()
    if not dna:
        return []

    events = _read_jsonl(BEHAVIOR_LOG_PATH)
    cmd_events = [e for e in events if e.get("event_type") == "command_invocation"]
    if len(cmd_events) < MISMATCH_THRESHOLD:
        return []

    mismatches = []

    # ── Output dimension (high confidence) ──
    output_dna = dna.get("output", {})
    output_ranking = output_dna.get("ranking", [])
    output_scores = output_dna.get("scores", {})

    if output_ranking and cmd_events:
        # Map each command's domain to output type and count
        output_counts: dict[str, int] = {}
        for e in cmd_events:
            domain = e.get("domain", "")
            if domain:
                output_type = _map_domain_to_output(domain)
                output_counts[output_type] = output_counts.get(output_type, 0) + 1

        total = sum(output_counts.values())
        top_dna_output = output_ranking[0]  # what user says matters most

        if top_dna_output and total > 0:
            top_behavior_fraction = output_counts.get(top_dna_output, 0) / total
            if top_behavior_fraction < 0.30:
                # Find what they actually do most
                actual_top = max(output_counts, key=output_counts.get) if output_counts else "unknown"
                mismatches.append({
                    "dimension": "output",
                    "dna_value": f"top output preference: {top_dna_output} (score={output_scores.get(top_dna_output, '?')})",
                    "behavior_signal": f"only {top_behavior_fraction:.0%} of domains match {top_dna_output}; most frequent: {actual_top} ({output_counts.get(actual_top, 0)}/{total})",
                    "confidence": 0.85,
                    "detail": f"DNA ranks '{top_dna_output}' #1 but behavior shows only {top_behavior_fraction:.0%} alignment across {total} commands.",
                    "suggested_question": f"你的DNA显示你最看重'{top_dna_output}'类产品，但最近{total}次分析中有{total - output_counts.get(top_dna_output, 0)}次在看'{actual_top}'方向——是兴趣变了还是DNA需要更新？",
                })

    # ── Activity dimension (medium confidence) ──
    activity_dna = dna.get("activity", {})
    activity_ranking = activity_dna.get("ranking", [])
    activity_scores = activity_dna.get("scores", {})

    if activity_ranking and len(cmd_events) >= 5:
        full_runs, collect_runs = _map_command_to_activity(cmd_events)
        completion_rate = full_runs / max(1, collect_runs)

        top_activity = activity_ranking[0]
        creation_score = activity_scores.get("creation", 5)
        exploration_score = activity_scores.get("exploration", 5)

        # If DNA says "creation" but completion rate is low, they behave more like exploration
        if top_activity == "creation" and creation_score > exploration_score and completion_rate < 0.30:
            if collect_runs >= 3:
                mismatches.append({
                    "dimension": "activity",
                    "dna_value": f"top activity: creation (score={creation_score})",
                    "behavior_signal": f"pipeline completion rate: {completion_rate:.0%} ({full_runs}/{collect_runs} runs)",
                    "confidence": 0.65,
                    "detail": f"DNA values 'creation' highly but only {completion_rate:.0%} of collect runs result in full pipeline completion — behavior looks more like exploration.",
                    "suggested_question": f"你的DNA里creation={creation_score}，但{collect_runs}次collect只有{full_runs}次跑完了全流水线——更像在探索而非创造，要不要调高exploration的权重？",
                })

    # ── Reward dimension (lower confidence) ──
    reward_dna = dna.get("reward", {})
    reward_scores = reward_dna.get("scores", {})
    wealth_score = reward_scores.get("wealth", 5)

    if len(cmd_events) >= 5:
        commercial_fraction = _map_domain_to_commercial_score(cmd_events)
        if commercial_fraction > 0.60 and wealth_score < 5:
            mismatches.append({
                "dimension": "reward",
                "dna_value": f"wealth={wealth_score} (low commercial interest)",
                "behavior_signal": f"{commercial_fraction:.0%} of domains are commercial (fintech/consumer/enterprise)",
                "confidence": 0.55,
                "detail": f"DNA says wealth is low priority ({wealth_score}/10) but {commercial_fraction:.0%} of analyses target commercial domains.",
                "suggested_question": f"你的DNA里wealth只有{wealth_score}分，但最近{commercial_fraction:.0%}的分析都在商业化领域——是DNA需要更新，还是你在做竞品调研？",
            })

    return mismatches


def save_mismatch_report(mismatches: list[dict]) -> str | None:
    """Save mismatch detection results to state/mismatch_report.json.

    Returns the file path if mismatches found, None otherwise.
    """
    if not mismatches:
        # Remove stale report if no mismatches
        p = Path(MISMATCH_REPORT_PATH)
        if p.exists():
            p.unlink()
        return None

    report = {
        "generated_at": _now_iso(),
        "event_count": len(_read_jsonl(BEHAVIOR_LOG_PATH)),
        "mismatches": mismatches,
    }
    _ensure_dir(MISMATCH_REPORT_PATH)
    Path(MISMATCH_REPORT_PATH).write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    return MISMATCH_REPORT_PATH
