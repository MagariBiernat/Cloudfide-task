#!/usr/bin/env python3
"""Security gate for agent-produced patches.

This is the *real* enforcement point. Agent-side permissions (tool allowlists,
hooks) are defence in depth; this deterministic check runs outside the agent,
from the trusted base revision, before a patch is tested, committed or posted.

A patch is rejected when it:
  * touches any path outside the test allowlist;
  * deletes, renames, chmods or symlinks files, or contains binary data;
  * modifies test/coverage configuration (pytest.ini, pyproject, vite config,
    package manifests, setup files) — prevents gaming coverage or thresholds;
  * adds focus/skip/ignore markers (.only, .skip, xfail, pragma: no cover,
    istanbul/v8/c8 ignore) or network calls to real hosts;
  * exceeds size limits.

Exit code 0 = accepted, 1 = rejected. JSON verdict on stdout / --output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_PATHS = [
    re.compile(r"^backend/tests/(?:[\w-]+/)*(?:test_[\w-]+|conftest|__init__|[\w-]*fixtures?[\w-]*|mocks)\.py$"),
    re.compile(r"^frontend/src/(?:[\w.-]+/)*[\w.-]+\.test\.tsx?$"),
    re.compile(r"^frontend/src/test/(?:[\w-]+/)*[\w.-]+\.tsx?$"),
]
# Global test setup could silence failures or stub assertions away.
PROTECTED_FILES = {"frontend/src/test/setup.ts"}
APPEND_ONLY = {"backend/tests/conftest.py", "backend/tests/mocks.py"}
FORBIDDEN_ADDED = [
    (re.compile(r"\b(?:it|test|describe)\.(?:only|skip|todo)\s*\("), "focused/skipped test"),
    (re.compile(r"\b(?:fit|fdescribe|xit|xdescribe)\s*\("), "focused/skipped test"),
    (re.compile(r"pytest\.mark\.(?:skip|skipif|xfail)|pytest\.(?:skip|xfail)\s*\("), "skipped/xfail test"),
    (re.compile(r"pragma:\s*no\s*cover"), "coverage exclusion pragma"),
    (re.compile(r"(?:istanbul|v8|c8)\s+ignore"), "coverage exclusion pragma"),
    (re.compile(r"""https?://(?!localhost|127\.0\.0\.1|testserver|example\.(?:com|org))[\w.-]+""", re.I), "real network host"),
    (re.compile(r"\b(?:subprocess|os\.system|child_process|execSync)\b"), "process execution in tests"),
    (re.compile(r"\bANTHROPIC_|\bGITHUB_TOKEN\b|process\.env\.[A-Z_]*(?:TOKEN|KEY|SECRET)"), "secret access"),
]
MAX_FILES = 25
MAX_ADDED_LINES = 3000


@dataclass
class FilePatch:
    path: str
    old_path: str | None = None
    new_file: bool = False
    deleted: bool = False
    renamed: bool = False
    mode_change: bool = False
    symlink: bool = False
    binary: bool = False
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def parse_patch(text: str) -> list[FilePatch]:
    files: list[FilePatch] = []
    cur: FilePatch | None = None
    in_header = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            in_header = True
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if not m:
                raise ValueError(f"unparseable diff header: {line!r}")
            cur = FilePatch(path=m.group(2), old_path=m.group(1))
            files.append(cur)
            continue
        if cur is None:
            if line.strip():
                raise ValueError("content before first 'diff --git' header")
            continue
        if line.startswith("@@"):
            in_header = False
            continue
        if not in_header:
            if line.startswith("+"):
                cur.added.append(line[1:])
            elif line.startswith("-"):
                cur.removed.append(line[1:])
            continue
        if line.startswith("new file mode"):
            cur.new_file = True
            cur.symlink |= line.endswith("120000")
            cur.mode_change |= not line.endswith("100644")
        elif line.startswith("deleted file mode"):
            cur.deleted = True
        elif line.startswith(("rename from", "rename to", "copy from", "copy to", "similarity index")):
            cur.renamed = True
        elif line.startswith(("old mode", "new mode")):
            cur.mode_change = True
            cur.symlink |= line.endswith("120000")
        elif line.startswith(("Binary files", "GIT binary patch")):
            cur.binary = True
    return files


def check(files: list[FilePatch]) -> list[str]:
    problems: list[str] = []
    if len(files) > MAX_FILES:
        problems.append(f"patch touches {len(files)} files (limit {MAX_FILES})")
    total_added = sum(len(f.added) for f in files)
    if total_added > MAX_ADDED_LINES:
        problems.append(f"patch adds {total_added} lines (limit {MAX_ADDED_LINES})")
    for f in files:
        p = f.path
        if ".." in Path(p).parts or p.startswith("/"):
            problems.append(f"{p}: path traversal")
            continue
        if f.old_path and f.old_path != p:
            problems.append(f"{p}: rename/copy not allowed")
        if not any(rx.match(p) for rx in ALLOWED_PATHS):
            problems.append(f"{p}: outside the test-path allowlist")
        if f.deleted:
            problems.append(f"{p}: deleting files is not allowed")
        if f.renamed:
            problems.append(f"{p}: rename/copy not allowed")
        if f.symlink:
            problems.append(f"{p}: symlinks are not allowed")
        if f.mode_change and not f.symlink:
            problems.append(f"{p}: file mode changes are not allowed")
        if f.binary:
            problems.append(f"{p}: binary content is not allowed")
        if p in PROTECTED_FILES:
            problems.append(f"{p}: protected file")
        if p in APPEND_ONLY and f.removed:
            problems.append(f"{p}: shared fixtures are append-only (lines removed)")
        for line in f.added:
            for rx, reason in FORBIDDEN_ADDED:
                if rx.search(line):
                    problems.append(f"{p}: {reason}: {line.strip()[:120]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("patch", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    text = args.patch.read_text() if args.patch.exists() else ""
    try:
        files = parse_patch(text)
        problems = check(files)
    except ValueError as exc:
        files, problems = [], [f"malformed patch: {exc}"]

    verdict = {
        "accepted": not problems,
        "empty": not files and not problems,
        "files": [{"path": f.path, "new_file": f.new_file, "added": len(f.added), "removed": len(f.removed)}
                  for f in files],
        "problems": problems,
    }
    payload = json.dumps(verdict, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    print(payload)
    return 0 if verdict["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
