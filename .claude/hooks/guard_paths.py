#!/usr/bin/env python3
"""PreToolUse hook: block file writes outside the unit-test allowlist.

Defence in depth for the unit-test agent. The authoritative control is the
patch gate (.github/agent-scripts/gate.py) that runs outside the agent; this
hook gives the agent immediate, explainable feedback instead of a rejected
patch at the end of the run.

Protocol: JSON on stdin ({tool_name, tool_input, ...}); exit 2 + stderr blocks.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ALLOWED = [
    re.compile(r"^backend/tests/(?:[\w-]+/)*[\w-]+\.py$"),
    re.compile(r"^frontend/src/(?:[\w.-]+/)*[\w.-]+\.test\.tsx?$"),
    re.compile(r"^frontend/src/test/(?:[\w-]+/)*[\w.-]+\.tsx?$"),
    re.compile(r"^\.agent-report/[\w.-]+$"),
]
PROTECTED = {"frontend/src/test/setup.ts"}


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("guard_paths: invalid hook input", file=sys.stderr)
        return 2

    tool_input = event.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not raw:
        return 0

    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    target = Path(raw)
    target = (target if target.is_absolute() else project / target).resolve()
    try:
        rel = target.relative_to(project).as_posix()
    except ValueError:
        print(f"Blocked: {raw} is outside the project directory.", file=sys.stderr)
        return 2

    if rel in PROTECTED:
        print(f"Blocked: {rel} is the global test setup and must not be changed by the agent.", file=sys.stderr)
        return 2
    if not any(rx.match(rel) for rx in ALLOWED):
        print(
            f"Blocked: {rel} is not a unit-test file. The agent may only write "
            "backend/tests/**/*.py, frontend/src/**/*.test.ts(x), frontend/src/test/** "
            "and .agent-report/*. Never modify production code or configuration; "
            "if the code looks wrong, report it as flag_suspected_bug instead.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
