#!/usr/bin/env python3
"""PostToolUse hook: capture Claude Code tool calls to raw trace files.

Reads stdin JSON from Claude Code's PostToolUse hook event, extracts the tool
name, input, and result, and appends a timestamped event to a per-session
raw JSONL file under state/traces/.

The raw files are later consumed by the trace-classify skill, which groups tool
calls into logical steps and writes structured trace JSON for human review.
"""

import json
import os
import sys
from datetime import datetime, timezone

TRACES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        # Can't parse input — non-blocking, just continue
        print(json.dumps({"continue": True}))
        return 0

    try:
        session_id = data.get("session_id", "unknown")
        tool_name = data.get("tool_name", "")
        tool_input_raw = data.get("tool_input", {})

        # Serialize tool_input safely (it may contain non-serializable objects
        # from some hook events, though PostToolUse should be clean)
        try:
            tool_input = json.loads(json.dumps(tool_input_raw, default=str))
        except (TypeError, ValueError):
            tool_input = str(tool_input_raw)

        # Keep a generous chunk of tool_result for downstream analysis.
        # 64KB preserves full SandboxResult payloads from CLI commands
        # while bounding raw file growth for sessions with many tool calls.
        tool_result_raw = data.get("tool_result", "")
        if isinstance(tool_result_raw, str) and len(tool_result_raw) > 65536:
            tool_result = tool_result_raw[:65536] + (
                f"\n... [truncated {len(tool_result_raw) - 65536} bytes]"
            )
        else:
            tool_result = tool_result_raw

        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "input": tool_input,
            "result": tool_result,
        }

        os.makedirs(TRACES_DIR, exist_ok=True)
        raw_file = os.path.join(TRACES_DIR, f"{session_id}.raw.jsonl")
        with open(raw_file, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    except Exception:
        # Never block the main loop on a trace write failure
        pass

    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
