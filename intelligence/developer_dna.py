"""Deterministic DeveloperDNA feature computation.

Computes evidence-backed judgments about a developer's technical practices from
already-collected repo + issue signals. Semantic induction (narratives, what a
pattern *means*) is left to the ``builderdna`` Skill; this module only computes
deterministic facts with explicit evidence references and an
observed/inferred/unknown status.

Hard rules (from the refactor plan P5):
- Every judgment cites a repo or issue fact.
- Nothing is inferred from stars, followers, or a single README.
- Missing data → ``unknown`` — never story completion.
- No relationship judgments ("worth knowing", etc.).

Idempotency: the computation is a pure function of its inputs, so identical
repos+issues produce identical output. The ``merge`` helper lets a Skill detect
new/changed evidence and only re-derive the affected dimensions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from models.payload import DeveloperDNA, DNADimension, DNAEvidence

DIMENSIONS: tuple[str, ...] = (
    "problem_domains",
    "build_patterns",
    "technology_choices",
    "iteration_style",
    "maintenance_behavior",
    "testing_reliability_signals",
    "open_source_collaboration",
    "idea_to_shipping_evidence",
)

_TOPIC_TO_DOMAIN = {
    "mcp": "agent / tooling",
    "agent": "agent",
    "agent-framework": "agent",
    "llm": "llm / ai",
    "ai": "llm / ai",
    "vector": "data / retrieval",
    "database": "data / infra",
    "cli": "developer tooling",
    "sdk": "developer tooling",
    "infrastructure": "infrastructure",
    "kubernetes": "infrastructure",
    "observability": "observability",
    "testing": "developer tooling / testing",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dim(
    dimension: str,
    status: str,
    confidence: float,
    summary: str,
    evidence: list[DNAEvidence] | None = None,
) -> DNADimension:
    return DNADimension(
        dimension=dimension,
        status=status,
        confidence=round(confidence, 2),
        summary=summary,
        evidence=evidence or [],
    )


def compute_developer_dna(
    developer: str,
    repos: list[dict] | None = None,
    issues: list[dict] | None = None,
    activity: list[dict] | None = None,
) -> DeveloperDNA:
    """Compute an evidence-backed DeveloperDNA from repo + issue + activity signals.

    Args:
        developer: login to attribute the analysis to.
        repos: list of repo dicts (full_name, language, topics, stars, forks,
            velocity, created_at).
        issues: list of issue dicts (repo, issue_number, title, labels).
        activity: list of RepoActivity dicts (repo, open_prs, merged_prs,
            recent_commits, releases, has_ci, has_tests). When present, the
            commit/PR/CI-backed dimensions are populated; otherwise ``unknown``.
    """
    repos = list(repos or [])
    issues = list(issues or [])

    dims: list[DNADimension] = []

    # ── technology_choices: observed from language + topics ────────────────
    langs: dict[str, int] = {}
    topics: dict[str, int] = {}
    for r in repos:
        lang = (r.get("language") or "").strip()
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
        for t in r.get("topics") or []:
            topics[t] = topics.get(t, 0) + 1

    if langs:
        top_langs = sorted(langs, key=langs.get, reverse=True)[:3]
        tech_ev = [
            DNAEvidence(ref=f"repo:{r.get('full_name', '')}", kind="repo", note=f"language={r.get('language', '')}")
            for r in repos if (r.get("language") or "").strip()
        ][:8]
        summary = f"主要语言: {', '.join(top_langs)}"
        if topics:
            top_topics = sorted(topics, key=topics.get, reverse=True)[:3]
            summary += f"; 主要 topic: {', '.join(top_topics)}"
        dims.append(_dim("technology_choices", "observed", 0.9, summary, tech_ev))
    else:
        dims.append(_dim("technology_choices", "unknown", 0.0, "无语言/主题数据", []))

    # ── problem_domains: observed from issue labels, else inferred from topics
    domain_hits: dict[str, int] = {}
    domain_evidence: list[DNAEvidence] = []
    for i in issues:
        for lbl in i.get("labels") or []:
            domain_hits[lbl] = domain_hits.get(lbl, 0) + 1
            domain_evidence.append(
                DNAEvidence(ref=f"issue:{i.get('repo', '')}#{i.get('issue_number', '')}", kind="issue", note=f"label={lbl}")
            )
    if domain_hits:
        top_domains = sorted(domain_hits, key=domain_hits.get, reverse=True)[:5]
        dims.append(_dim("problem_domains", "observed", 0.8, f"反复出现的 issue 标签: {', '.join(top_domains)}", domain_evidence[:8]))
    elif topics:
        mapped = sorted({_TOPIC_TO_DOMAIN.get(t, t) for t in topics})
        topic_ev = [DNAEvidence(ref=f"repo:{r.get('full_name', '')}", kind="repo", note=f"topics={r.get('topics', [])}") for r in repos if r.get("topics")]
        dims.append(_dim("problem_domains", "inferred", 0.5, f"从 topic 推断: {', '.join(mapped[:5])}", topic_ev[:8]))
    else:
        dims.append(_dim("problem_domains", "unknown", 0.0, "无 issue 或 topic 数据", []))

    # ── maintenance_behavior: inferred from recency + velocity ─────────────
    if repos:
        velocities = [float(r.get("velocity") or 0.0) for r in repos]
        active = sum(1 for v in velocities if v > 0.5)
        recency = _recent_created(repos)
        ev = [DNAEvidence(ref=f"repo:{r.get('full_name', '')}", kind="repo", note=f"velocity={r.get('velocity', 0)}") for r in repos][:5]
        if active > 0:
            dims.append(_dim("maintenance_behavior", "inferred", 0.6, f"{active}/{len(repos)} 个仓库有近期增长信号（velocity>0.5）", ev))
        elif recency:
            dims.append(_dim("maintenance_behavior", "inferred", 0.5, f"最近活跃（{recency} 个仓库创建于近 180 天）", ev))
        else:
            dims.append(_dim("maintenance_behavior", "inferred", 0.3, "仓库增长信号弱，可能已停滞", ev))
    else:
        dims.append(_dim("maintenance_behavior", "unknown", 0.0, "无仓库数据", []))

    # ── open_source_collaboration: inferred from forks (not stars) ────────
    if repos:
        total_forks = sum(int(r.get("forks") or 0) for r in repos)
        ev = [DNAEvidence(ref=f"repo:{r.get('full_name', '')}", kind="repo", note=f"forks={r.get('forks', 0)}") for r in repos if int(r.get("forks") or 0) > 0][:5]
        if total_forks >= 100:
            dims.append(_dim("open_source_collaboration", "inferred", 0.6, f"合计 {total_forks} forks，社区参与度较高", ev))
        elif total_forks > 0:
            dims.append(_dim("open_source_collaboration", "inferred", 0.4, f"合计 {total_forks} forks，有少量社区参与", ev))
        else:
            dims.append(_dim("open_source_collaboration", "unknown", 0.0, "无 fork 数据", []))
    else:
        dims.append(_dim("open_source_collaboration", "unknown", 0.0, "无仓库数据", []))

    # ── idea_to_shipping_evidence: inferred from velocity + repo count ────
    if repos:
        shipped = [r for r in repos if float(r.get("velocity") or 0.0) > 1.0]
        ev = [DNAEvidence(ref=f"repo:{r.get('full_name', '')}", kind="repo", note=f"velocity={r.get('velocity', 0)}") for r in shipped][:5]
        if shipped:
            dims.append(_dim("idea_to_shipping_evidence", "inferred", 0.6, f"{len(shipped)} 个仓库有显著增长（velocity>1.0），具备从想法到交付的迹象", ev))
        elif len(repos) >= 3:
            dims.append(_dim("idea_to_shipping_evidence", "inferred", 0.4, f"维护 {len(repos)} 个仓库，但增长信号弱", ev))
        else:
            dims.append(_dim("idea_to_shipping_evidence", "unknown", 0.0, "仓库数量不足或增长信号弱", []))
    else:
        dims.append(_dim("idea_to_shipping_evidence", "unknown", 0.0, "无仓库数据", []))

    # ── Dimensions requiring commit/PR/release data ──────────────────────
    # Populated from the limited activity collection when present; otherwise
    # honestly unknown (per the plan's "missing data → unknown" rule).
    dims.extend(_compute_activity_dimensions(activity or []))

    return DeveloperDNA(
        developer=developer,
        dimensions=dims,
        source_repos=[r.get("full_name", "") for r in repos],
        source_issues=len(issues),
    )


def _compute_activity_dimensions(activity: list[dict]) -> list[DNADimension]:
    """Compute build_patterns / iteration_style / testing_reliability_signals.

    Each is evidence-cited from the bounded ``RepoActivity`` facts. With no
    activity data, all three are ``unknown``.
    """
    activity = list(activity)
    total_prs = sum(int(a.get("merged_prs", 0)) + int(a.get("open_prs", 0)) for a in activity)
    merged_prs = sum(int(a.get("merged_prs", 0)) for a in activity)
    commits = sum(int(a.get("recent_commits", 0)) for a in activity)
    releases = sum(int(a.get("releases", 0)) for a in activity)
    ci = any(a.get("has_ci", False) for a in activity)
    tests = any(a.get("has_tests", False) for a in activity)

    pr_evidence = [
        DNAEvidence(ref=f"repo:{a.get('repo', '')}", kind="repo", note=f"merged_prs={a.get('merged_prs', 0)}, open_prs={a.get('open_prs', 0)}")
        for a in activity if int(a.get("merged_prs", 0)) + int(a.get("open_prs", 0)) > 0
    ][:5]

    if not activity:
        return [
            _dim("build_patterns", "unknown", 0.0, "需要 commit/PR 数据（当前信号未采集）", []),
            _dim("iteration_style", "unknown", 0.0, "需要 commit/PR 频率数据（当前信号未采集）", []),
            _dim("testing_reliability_signals", "unknown", 0.0, "需要 CI/测试数据（当前信号未采集）", []),
        ]

    dims: list[DNADimension] = []

    # build_patterns — inferred from PR volume (small reviewable changes vs few large).
    if total_prs >= 5:
        dims.append(_dim("build_patterns", "inferred", 0.6, f"频繁 PR（合计 {total_prs}，含 {merged_prs} merged）→ 小而可审查的变更", pr_evidence))
    elif total_prs > 0:
        dims.append(_dim("build_patterns", "inferred", 0.4, f"少量 PR（合计 {total_prs}）→ 变更较大或提交较集中", pr_evidence))
    else:
        dims.append(_dim("build_patterns", "unknown", 0.0, "无 PR 数据", []))

    # iteration_style — inferred from commit + release cadence.
    if commits >= 20:
        dims.append(_dim("iteration_style", "inferred", 0.6, f"快速迭代（近期 {commits} commits，{releases} releases）", [
            DNAEvidence(ref=f"repo:{a.get('repo', '')}", kind="repo", note=f"recent_commits={a.get('recent_commits', 0)}, releases={a.get('releases', 0)}")
            for a in activity if int(a.get("recent_commits", 0)) > 0
        ][:5]))
    elif commits > 0 or releases > 0:
        dims.append(_dim("iteration_style", "inferred", 0.4, f"温和迭代（{commits} commits，{releases} releases）", [
            DNAEvidence(ref=f"repo:{a.get('repo', '')}", kind="repo", note=f"recent_commits={a.get('recent_commits', 0)}, releases={a.get('releases', 0)}")
            for a in activity if int(a.get("recent_commits", 0)) > 0 or int(a.get("releases", 0)) > 0
        ][:5]))
    else:
        dims.append(_dim("iteration_style", "unknown", 0.0, "无 commit/release 数据", []))

    # testing_reliability_signals — observed from CI/test presence.
    signals = []
    if ci:
        signals.append("CI workflow 存在")
    if tests:
        signals.append("test 目录存在")
    if signals:
        dims.append(_dim("testing_reliability_signals", "observed", 0.7, "；".join(signals), [
            DNAEvidence(ref=f"repo:{a.get('repo', '')}", kind="repo", note=f"has_ci={a.get('has_ci', False)}, has_tests={a.get('has_tests', False)}")
            for a in activity if a.get("has_ci") or a.get("has_tests")
        ][:5]))
    else:
        dims.append(_dim("testing_reliability_signals", "inferred", 0.3, "未检出 CI/test 信号", []))

    return dims


def _recent_created(repos: list[dict]) -> int:
    """Count repos created within the last 180 days (from today)."""
    now = datetime.now(timezone.utc)
    count = 0
    for r in repos:
        created = (r.get("created_at") or "").strip()
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if (now - dt).days <= 180:
                count += 1
        except ValueError:
            continue
    return count


def merge_developer_dna(previous: DeveloperDNA, current: DeveloperDNA) -> tuple[DeveloperDNA, bool]:
    """Merge a previous DNA with a fresh computation, returning (dna, changed).

    Only re-derives when the evidence changed: if the fresh computation draws
    from the same repos and issue count, the previous result is returned
    unchanged (``changed=False``). This is the deterministic "only process
    new/changed evidence" contract.
    """
    same_sources = (
        sorted(previous.source_repos) == sorted(current.source_repos)
        and previous.source_issues == current.source_issues
    )
    if same_sources:
        return previous, False
    return current, True
