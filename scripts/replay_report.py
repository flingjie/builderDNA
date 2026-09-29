#!/usr/bin/env python3
"""P3 replay reporter — deterministic metrics + human-annotation slots.

Reads one investigation's store and computes the metrics the release gate needs:

- source_calls                — number of data actions that consumed a source call
- independent_evidence_chains — distinct independence keys among collected evidence
- counterevidence_actions     — number of ``seek_counterevidence`` actions
- unsupported_assertions      — candidate evidence_ids that reference unknown evidence
- candidate_count             — number of PainClusterCandidate records

Human-annotation slots (actionability_score, useful_annotation, blind_notes) are
left empty for the reviewer to fill; they are never computed here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigations.store import InvestigationStore


def compute_metrics(store: InvestigationStore, investigation_id: str) -> dict:
    actions = store.list_actions(investigation_id)
    evidence = store.list_evidence(investigation_id)
    candidates = store.list_candidates(investigation_id)

    source_calls = sum(1 for a in actions if a.action in ("search_discussions", "inspect_thread"))
    chains = len({e.item.independence_key for e in evidence})
    counter_actions = sum(1 for a in actions if a.action == "seek_counterevidence")

    known_ids = {e.id for e in evidence}
    unsupported = 0
    for c in candidates:
        unsupported += sum(1 for eid in c.evidence_ids if eid not in known_ids)

    return {
        "investigation_id": investigation_id,
        "source_calls": source_calls,
        "action_count": len(actions),
        "independent_evidence_chains": chains,
        "counterevidence_actions": counter_actions,
        "unsupported_assertions": unsupported,
        "candidate_count": len(candidates),
        # human-annotation slots — never computed
        "actionability_score": None,
        "useful_annotation": "",
        "blind_notes": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new", required=True, help="state dir for the new-flow run")
    parser.add_argument("--id", default="inv_1", help="investigation id")
    parser.add_argument("--out", required=True, help="output JSON report path")
    args = parser.parse_args()

    store = InvestigationStore(state_dir=args.new)
    metrics = compute_metrics(store, args.id)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
