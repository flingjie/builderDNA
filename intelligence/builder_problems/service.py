"""Deterministic service logic for builder problem trajectories.

No network, no LLM. The CLI layer parses options and renders JSON; this module
owns validation, snapshot updates, append-only event creation, structured
comparison, and verifiable opportunity-card generation.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from models.builder_problem import (
    BuilderProblem,
    ProblemComparison,
    ProblemEvent,
    ProblemEventType,
    ProblemEvidenceRef,
    ProblemOpportunityCard,
    ProblemStatus,
    ValidationTarget,
)
from intelligence.builder_problems.store import BuilderProblemStore


class BuilderProblemError(Exception):
    """Base service error."""


class BuilderProblemValidationError(BuilderProblemError):
    """Bad input or unknown problem."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", (text or "").lower()).strip("-")
    return value or "problem"


def _parse_status(value: str) -> ProblemStatus:
    try:
        return ProblemStatus((value or "").strip().lower())
    except ValueError:
        valid = ", ".join(s.value for s in ProblemStatus)
        raise BuilderProblemValidationError(f"invalid status {value!r}; expected one of {valid}")


def _parse_event_type(value: str) -> ProblemEventType:
    try:
        return ProblemEventType((value or "").strip().lower())
    except ValueError:
        valid = ", ".join(e.value for e in ProblemEventType)
        raise BuilderProblemValidationError(f"invalid event type {value!r}; expected one of {valid}")


def _unique_problem_id(store: BuilderProblemStore, base: str) -> str:
    existing = {p.problem_id for p in store.list_problems()}
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def _new_event_id(problem_id: str) -> str:
    stamp = _now_utc().strftime("%Y%m%dT%H%M%S%f")
    return f"evt-{problem_id}-{stamp}-{uuid4().hex[:8]}"


def _snapshot_fields(
    *,
    person_ref: str,
    statement: str,
    project_ref: str,
    context: str,
    current_workaround: str,
    user_segment: str,
    trigger_context: str,
    job_to_be_done: str,
    primary_cost: str,
    source_refs: list[str],
) -> dict:
    return {
        "person_ref": person_ref,
        "statement": statement,
        "project_ref": project_ref,
        "context": context,
        "current_workaround": current_workaround,
        "user_segment": user_segment,
        "trigger_context": trigger_context,
        "job_to_be_done": job_to_be_done,
        "primary_cost": primary_cost,
        "source_refs": sorted(set(source_refs)),
    }


def capture_problem(
    store: BuilderProblemStore,
    *,
    person_ref: str,
    statement: str,
    project_ref: str = "",
    context: str = "",
    current_workaround: str = "",
    user_segment: str = "",
    trigger_context: str = "",
    job_to_be_done: str = "",
    primary_cost: str = "",
    source_refs: list[str] | None = None,
    problem_id: str | None = None,
    status: str = "observed",
) -> dict:
    """Create or update a problem snapshot and append its first/update event."""
    person_ref = (person_ref or "").strip()
    statement = (statement or "").strip()
    if not person_ref:
        raise BuilderProblemValidationError("capture requires --person-ref")
    if not statement:
        raise BuilderProblemValidationError("capture requires --statement")

    parsed_status = _parse_status(status)
    source_refs = sorted(set(source_refs or []))
    now = _now_utc()

    if problem_id:
        existing = store.get_problem(problem_id)
        new_id = problem_id
    else:
        existing = None
        new_id = _unique_problem_id(
            store, f"{_slugify(person_ref)}-{_slugify(statement)}"
        )

    incoming = _snapshot_fields(
        person_ref=person_ref,
        statement=statement,
        project_ref=(project_ref or "").strip(),
        context=(context or "").strip(),
        current_workaround=(current_workaround or "").strip(),
        user_segment=(user_segment or "").strip(),
        trigger_context=(trigger_context or "").strip(),
        job_to_be_done=(job_to_be_done or "").strip(),
        primary_cost=(primary_cost or "").strip(),
        source_refs=source_refs,
    )

    changed: list[str] = []
    if existing is None:
        action = "created"
        changed = sorted(incoming)
        merged = {**incoming, "source_refs": source_refs}
        snapshot = BuilderProblem(
            problem_id=new_id,
            first_seen_at=now,
            last_seen_at=now,
            status=parsed_status,
            **merged,
        )
        event = ProblemEvent(
            event_id=_new_event_id(new_id),
            problem_id=new_id,
            event_type=ProblemEventType.PROBLEM_OBSERVED,
            summary=f"发现问题: {statement}",
            detail="首次记录问题",
            source_refs=source_refs,
            from_status=None,
            to_status=parsed_status,
            current_workaround=(current_workaround or "").strip(),
        )
    else:
        old = existing.model_dump(mode="json")
        for field, value in incoming.items():
            old_value = old.get(field)
            if isinstance(old_value, list):
                old_value = sorted(set(old_value))
            if old_value != value:
                changed.append(field)
        if existing.status != parsed_status:
            changed.append("status")

        new_source_refs = sorted(set(source_refs) - set(existing.source_refs))
        if not changed and not new_source_refs:
            return {
                "action": "already_captured",
                "changed": [],
                "data": {
                    "problem": existing.model_dump(mode="json"),
                    "event": None,
                },
            }

        action = "updated"
        merged_source_refs = sorted(set(existing.source_refs) | set(source_refs))
        snapshot = existing.model_copy(
            update={
                **incoming,
                "source_refs": merged_source_refs,
                "status": parsed_status,
                "last_seen_at": now,
                "updated_at": now,
            }
        )
        event = ProblemEvent(
            event_id=_new_event_id(new_id),
            problem_id=new_id,
            event_type=ProblemEventType.NOTE,
            summary="补充问题信息",
            detail="; ".join(changed) if changed else "补充证据来源",
            source_refs=new_source_refs,
            from_status=existing.status,
            to_status=parsed_status,
            current_workaround=(current_workaround or "").strip(),
        )

    stored_snapshot = store.upsert_problem(snapshot)
    stored_event = store.add_event(event)
    return {
        "action": action,
        "changed": changed,
        "data": {
            "problem": stored_snapshot.model_dump(mode="json"),
            "event": stored_event.model_dump(mode="json"),
        },
    }


def record_event(
    store: BuilderProblemStore,
    *,
    problem_id: str,
    event_type: str = "note",
    summary: str = "",
    detail: str = "",
    source_refs: list[str] | None = None,
    to_status: str | None = None,
    from_status: str | None = None,
    current_workaround: str | None = None,
) -> dict:
    """Append one immutable trajectory event and update the current snapshot."""
    problem_id = (problem_id or "").strip()
    if not problem_id:
        raise BuilderProblemValidationError("record requires PROBLEM_ID")
    existing = store.get_problem(problem_id)
    if existing is None:
        raise BuilderProblemValidationError(f"problem {problem_id!r} not found")

    parsed_event_type = _parse_event_type(event_type)
    summary = (summary or "").strip()
    if not summary:
        summary = {
            ProblemEventType.PROBLEM_OBSERVED: "问题被再次观察到",
            ProblemEventType.ATTEMPT: "尝试了一个方案",
            ProblemEventType.TOOL_SWITCH: "更换了工具",
            ProblemEventType.STATUS_CHANGE: "问题状态变化",
            ProblemEventType.NOTE: "补充记录",
        }[parsed_event_type]

    parsed_to = _parse_status(to_status) if to_status else None
    parsed_from = _parse_status(from_status) if from_status else existing.status
    event_source_refs = sorted(set(source_refs or []))
    now = _now_utc()
    event = ProblemEvent(
        event_id=_new_event_id(problem_id),
        problem_id=problem_id,
        event_type=parsed_event_type,
        summary=summary,
        detail=(detail or "").strip(),
        source_refs=event_source_refs,
        from_status=parsed_from,
        to_status=parsed_to,
        current_workaround=(current_workaround or "").strip(),
        recorded_at=now,
    )
    stored_event = store.add_event(event)

    workaround = (
        (current_workaround or "").strip()
        if current_workaround is not None
        else existing.current_workaround
    )
    snapshot = existing.model_copy(
        update={
            "source_refs": sorted(set(existing.source_refs) | set(event_source_refs)),
            "status": parsed_to or existing.status,
            "current_workaround": workaround,
            "last_seen_at": now,
            "updated_at": now,
        }
    )
    stored_snapshot = store.upsert_problem(snapshot)
    changed = []
    if parsed_to and parsed_to != existing.status:
        changed.append("status")
    if event_source_refs and not set(event_source_refs) <= set(existing.source_refs):
        changed.append("source_refs")
    if current_workaround is not None and (current_workaround or "").strip() != existing.current_workaround:
        changed.append("current_workaround")
    return {
        "action": "recorded",
        "changed": changed,
        "data": {
            "problem": stored_snapshot.model_dump(mode="json"),
            "event": stored_event.model_dump(mode="json"),
        },
    }


def list_problems(
    store: BuilderProblemStore,
    *,
    person_ref: str | None = None,
    status: str | None = None,
) -> dict:
    """List current problem snapshots, optionally filtered."""
    parsed_status = _parse_status(status) if status else None
    problems = store.list_problems()
    if person_ref:
        person_ref = person_ref.strip()
        problems = [p for p in problems if p.person_ref == person_ref]
    if parsed_status is not None:
        problems = [p for p in problems if p.status == parsed_status]
    problems.sort(key=lambda p: (p.person_ref, p.problem_id))
    return {
        "action": "listed",
        "changed": [],
        "data": {
            "problems": [p.model_dump(mode="json") for p in problems],
            "count": len(problems),
        },
    }


def show_problem(store: BuilderProblemStore, problem_id: str) -> dict:
    """Return one problem and its append-only trajectory in event order."""
    problem_id = (problem_id or "").strip()
    problem = store.get_problem(problem_id)
    if problem is None:
        raise BuilderProblemValidationError(f"problem {problem_id!r} not found")
    events = sorted(store.list_events(problem_id), key=lambda e: e.recorded_at)
    return {
        "action": "shown",
        "changed": [],
        "data": {
            "problem": problem.model_dump(mode="json"),
            "events": [e.model_dump(mode="json") for e in events],
            "event_count": len(events),
        },
    }


def _norm(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


def _scenario_key(job_to_be_done: str, trigger_context: str) -> str:
    return f"{_norm(job_to_be_done)}|{_norm(trigger_context)}"


def _common_value(problems: list[BuilderProblem], field: str) -> str:
    values = [getattr(p, field, "") for p in problems]
    if not any(values):
        return ""
    return values[0] if all(v == values[0] for v in values) else ""


def _stringify(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _build_differences(
    problems: list[BuilderProblem], fields: tuple[str, ...]
) -> dict[str, list[dict[str, str]]]:
    differences: dict[str, list[dict[str, str]]] = {}
    for field in fields:
        entries = [
            {
                "problem_id": p.problem_id,
                "person_ref": p.person_ref,
                "value": _stringify(getattr(p, field, "")),
            }
            for p in problems
        ]
        distinct = {e["value"] for e in entries}
        if len(distinct) > 1:
            differences[field] = entries
    return differences


def _open_questions(problems: list[BuilderProblem], group_size: int) -> list[str]:
    questions: list[str] = []
    if group_size < 3:
        questions.append("共同需求假设目前只有 2 个独立人物，样本仍较小")
    for p in problems:
        if not p.source_refs:
            questions.append(f"{p.person_ref} 的问题 {p.problem_id} 缺少可核验来源")
        if not p.current_workaround:
            questions.append(f"尚未记录 {p.person_ref} 现有的绕过办法")
        if not p.primary_cost:
            questions.append(f"尚未记录 {p.person_ref} 的主要成本")
    if not any(p.status == ProblemStatus.RESOLVED for p in problems):
        questions.append("尚未有人确认该问题已解决")
    return questions


def _validation_targets(problems: list[BuilderProblem]) -> list[ValidationTarget]:
    unresolved = [p for p in problems if p.status != ProblemStatus.RESOLVED]
    order = {
        ProblemStatus.OBSERVED: 0,
        ProblemStatus.CONFIRMED: 1,
        ProblemStatus.RESOLVED: 2,
    }
    unresolved.sort(key=lambda p: (order[p.status], p.person_ref, p.problem_id))
    targets = []
    for p in unresolved:
        reason = (
            "问题已确认，可验证其工作流是否匹配最小交付"
            if p.status == ProblemStatus.CONFIRMED
            else "观察到问题，尚未确认是否为持续需求"
        )
        targets.append(
            ValidationTarget(
                problem_id=p.problem_id,
                person_ref=p.person_ref,
                project_ref=p.project_ref,
                status=p.status,
                reason=reason,
                source_refs=p.source_refs,
            )
        )
    return targets


def _minimal_deliverable(
    job_to_be_done: str,
    trigger_context: str,
    targets: list[ValidationTarget],
) -> str:
    if not targets:
        return (
            f"复现“{job_to_be_done}”在“{trigger_context}”下的失败路径，"
            "形成一页可交给验证对象的复现记录"
        )
    names = []
    for target in targets[:2]:
        label = target.person_ref
        if target.project_ref:
            label += f"({target.project_ref})"
        names.append(label)
    who = "、".join(names)
    return (
        f"向 {who} 做一次 20 分钟访谈，确认“{job_to_be_done}”在"
        f"“{trigger_context}”下是否真实发生；交付一段复现路径和 3 条验证问题"
    )


def compare_problems(store: BuilderProblemStore) -> dict:
    """Group problems by task+obstacle and produce structured comparisons."""
    problems = store.list_problems()
    grouped: dict[str, list[BuilderProblem]] = {}
    ungrouped: list[str] = []
    for p in problems:
        if not p.job_to_be_done or not p.trigger_context:
            ungrouped.append(p.problem_id)
            continue
        key = _scenario_key(p.job_to_be_done, p.trigger_context)
        grouped.setdefault(key, []).append(p)

    comparisons: list[ProblemComparison] = []
    for key, group in grouped.items():
        if len(group) < 2:
            ungrouped.extend(p.problem_id for p in group)
            continue
        group.sort(key=lambda p: (p.person_ref, p.problem_id))
        job = group[0].job_to_be_done
        trigger = group[0].trigger_context
        similarities = {
            "job_to_be_done": job,
            "trigger_context": trigger,
            "user_segment": _common_value(group, "user_segment"),
            "current_workaround": _common_value(group, "current_workaround"),
            "primary_cost": _common_value(group, "primary_cost"),
        }
        differences = _build_differences(
            group,
            (
                "user_segment",
                "project_ref",
                "context",
                "current_workaround",
                "primary_cost",
                "status",
            ),
        )
        evidence = [
            ProblemEvidenceRef(
                problem_id=p.problem_id,
                person_ref=p.person_ref,
                project_ref=p.project_ref,
                statement=p.statement,
                status=p.status,
                source_refs=p.source_refs,
            )
            for p in group
        ]
        questions = _open_questions(group, len(group))
        targets = _validation_targets(group)
        comparisons.append(
            ProblemComparison(
                scenario_key=key,
                title=f"{job} / {trigger}",
                user_segment=similarities["user_segment"],
                trigger_context=trigger,
                job_to_be_done=job,
                current_workaround=similarities["current_workaround"],
                primary_cost=similarities["primary_cost"],
                problem_ids=[p.problem_id for p in group],
                person_refs=sorted({p.person_ref for p in group}),
                project_refs=sorted({p.project_ref for p in group if p.project_ref}),
                similarities=similarities,
                differences=differences,
                evidence=evidence,
                open_questions=questions,
                validation_targets=targets,
                minimal_deliverable=_minimal_deliverable(job, trigger, targets),
            )
        )

    comparisons.sort(key=lambda c: (-len(c.person_refs), c.scenario_key))
    ungrouped = sorted(set(ungrouped))
    return {
        "action": "compared",
        "changed": [],
        "data": {
            "comparisons": [c.model_dump(mode="json") for c in comparisons],
            "ungrouped": ungrouped,
            "comparison_count": len(comparisons),
        },
    }


def build_opportunity_cards(store: BuilderProblemStore) -> dict:
    """Convert task+obstacle comparisons into verifiable opportunity cards."""
    compared = compare_problems(store)
    cards: list[ProblemOpportunityCard] = []
    for raw in compared["data"]["comparisons"]:
        comparison = ProblemComparison.model_validate(raw)
        source_refs = sorted({r for item in comparison.evidence for r in item.source_refs})
        confidence = min(
            0.9,
            0.45 + 0.15 * len(comparison.person_refs) + (0.05 if source_refs else 0.0),
        )
        same_parts = [
            f"任务: {comparison.job_to_be_done}",
            f"触发场景: {comparison.trigger_context}",
        ]
        if comparison.user_segment:
            same_parts.append(f"使用者: {comparison.user_segment}")
        if comparison.current_workaround:
            same_parts.append(f"现有办法: {comparison.current_workaround}")
        if comparison.primary_cost:
            same_parts.append(f"主要成本: {comparison.primary_cost}")

        different_parts: list[str] = []
        for field, entries in comparison.differences.items():
            for entry in entries:
                different_parts.append(
                    f"{field}: {entry['person_ref']}={entry['value']}"
                )

        cards.append(
            ProblemOpportunityCard(
                scenario_key=comparison.scenario_key,
                title=f"需要验证的需求：{comparison.job_to_be_done}",
                confidence=round(confidence, 2),
                who=comparison.evidence,
                same_parts=same_parts,
                different_parts=different_parts,
                key_unknowns=comparison.open_questions,
                validation_targets=comparison.validation_targets,
                minimal_deliverable=comparison.minimal_deliverable,
                source_refs=source_refs,
            )
        )
    cards.sort(key=lambda c: (-c.confidence, c.scenario_key))
    return {
        "action": "generated",
        "changed": [],
        "data": {
            "opportunities": [c.model_dump(mode="json") for c in cards],
            "count": len(cards),
        },
    }
