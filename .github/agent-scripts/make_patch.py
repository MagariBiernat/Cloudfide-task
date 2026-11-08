#!/usr/bin/env python3
"""Build a git-format patch from two directory trees (pristine vs workspace).

Works without a git repository (uses `git diff --no-index` per file), so the
agent can run in a throwaway copy and its output is just data: a patch that is
gated, tested and only then applied by a separate, trusted step.

Generated artefacts (caches, coverage, node_modules, venvs) are ignored.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "coverage", "dist",
    "storybook-static", ".agent-out", "htmlcov", ".vite", ".claude", ".agent-context", ".agent-report",
}
IGNORED_SUFFIXES = (".pyc",)
IGNORED_NAMES = {".coverage", "coverage.xml", "coverage.json", "lcov.info", ".DS_Store"}


def tree(root: Path) -> set[str]:
    out = set()
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts) or p.is_dir():
            continue
        if p.name.endswith(IGNORED_SUFFIXES) or p.name in IGNORED_NAMES or p.name.startswith(".coverage."):
            continue
        out.add(rel.as_posix())
    return out


def file_diff(base: Path, work: Path, rel: str) -> str:
    a = base / rel
    b = work / rel
    left = str(a) if a.exists() else "/dev/null"
    right = str(b) if b.exists() or b.is_symlink() else "/dev/null"
    proc = subprocess.run(
        ["git", "diff", "--no-index", "--binary", "--no-color", "--no-ext-diff", "--full-index", left, right],
        capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr)
    if not proc.stdout:
        return ""
    # Rewrite absolute paths to repo-relative a/<rel> b/<rel>.
    lines, in_header = [], True
    for line in proc.stdout.splitlines():
        if line.startswith("@@"):
            in_header = False
        elif in_header and line.startswith("new file mode 1007"):
            # Executable bits are filesystem noise (e.g. WSL on NTFS reports 0777); tests never need them.
            line = "new file mode 100644"
        elif in_header and line.startswith(("old mode 1006", "old mode 1007", "new mode 1006", "new mode 1007")):
            continue
        elif in_header and line.startswith("diff --git "):
            line = f"diff --git a/{rel} b/{rel}"
        elif in_header and line.startswith("--- ") and line != "--- /dev/null":
            line = f"--- a/{rel}"
        elif in_header and line.startswith("+++ ") and line != "+++ /dev/null":
            line = f"+++ b/{rel}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="pristine tree")
    parser.add_argument("--work", type=Path, required=True, help="tree modified by the agent")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    paths = sorted(tree(args.base) | tree(args.work))
    chunks = []
    for rel in paths:
        a, b = args.base / rel, args.work / rel
        if a.exists() and b.exists() and not b.is_symlink() and a.read_bytes() == b.read_bytes():
            continue
        chunk = file_diff(args.base.resolve(), args.work.resolve(), rel)
        if chunk:
            chunks.append(chunk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(chunks))
    print(f"{len(chunks)} file(s) changed -> {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
