#!/usr/bin/env python3
"""Map changed files to unit-test targets.

Deterministic, stdlib-only. Compares two directory snapshots (base / head) or
scans a single tree (--all) and emits JSON describing, per file:

  stack, role, kind, status, in_coverage_scope, test_path, test_exists,
  changed_lines, change_class and a pre-decision (candidate / skip + reason).

Coverage scope is read at runtime from the project's own configuration
(backend/pyproject.toml [tool.coverage.run] and frontend/vite.config.ts
coverage.include/exclude) so it can never drift from what CI measures.

Usage:
  map_changes.py --base-dir .agent-out/base --head-dir .agent-out/head
  map_changes.py --all --head-dir .
"""

from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "coverage",
    "dist", "storybook-static", ".agent-out", "htmlcov", ".agent-context", ".agent-report",
}
SENSITIVE_PREFIXES = (".claude/", ".github/", "CLAUDE.md", ".mcp.json")
DOC_SUFFIXES = (".md", ".txt", ".rst")
FRONTEND_SRC_SUFFIXES = (".ts", ".tsx")


# --------------------------------------------------------------------------- config

def _expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end():]
    return [p for option in match.group(1).split(",") for p in _expand_braces(head + option + tail)]


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a picomatch-style glob (**, *, ?, {a,b}) to a regex."""
    alternatives = []
    for expanded in _expand_braces(pattern):
        out, i = "", 0
        while i < len(expanded):
            if expanded.startswith("**/", i):
                out += r"(?:.*/)?"
                i += 3
            elif expanded.startswith("**", i):
                out += r".*"
                i += 2
            elif expanded[i] == "*":
                out += r"[^/]*"
                i += 1
            elif expanded[i] == "?":
                out += r"[^/]"
                i += 1
            else:
                out += re.escape(expanded[i])
                i += 1
        alternatives.append(out)
    return re.compile(r"^(?:" + "|".join(alternatives) + r")$")


@dataclass
class CoverageScope:
    backend_sources: list[str]
    backend_omit: list[str]
    frontend_include: list[str]
    frontend_exclude: list[str]

    def backend_in_scope(self, path: str) -> bool:
        # coverage.py: source=["app"] relative to backend/, omit = fnmatch on abs path
        rel = path.removeprefix("backend/")
        if not any(rel == s or rel.startswith(s.rstrip("/") + "/") for s in self.backend_sources):
            return False
        probe = "/" + path
        return not any(fnmatch.fnmatch(probe, pattern) for pattern in self.backend_omit)

    def frontend_in_scope(self, path: str) -> bool:
        rel = path.removeprefix("frontend/")
        included = any(glob_to_regex(p).match(rel) for p in self.frontend_include)
        excluded = any(glob_to_regex(p).match(rel) for p in self.frontend_exclude)
        return included and not excluded


def _extract_string_array(source: str, key: str) -> list[str]:
    match = re.search(rf"\b{key}\s*:\s*\[(.*?)\]", source, re.S)
    if not match:
        raise ValueError(f"cannot find '{key}: [...]' in vite config coverage block")
    return re.findall(r"""['"]([^'"]+)['"]""", match.group(1))


def load_coverage_scope(root: Path) -> CoverageScope:
    import tomllib

    pyproject = tomllib.loads((root / "backend/pyproject.toml").read_text())
    run_cfg = pyproject.get("tool", {}).get("coverage", {}).get("run", {})
    vite = (root / "frontend/vite.config.ts").read_text()
    coverage_block = vite[vite.index("coverage") :] if "coverage" in vite else ""
    if not coverage_block:
        raise ValueError("frontend/vite.config.ts has no coverage block")
    return CoverageScope(
        backend_sources=list(run_cfg.get("source", ["app"])),
        backend_omit=list(run_cfg.get("omit", [])),
        frontend_include=_extract_string_array(coverage_block, "include"),
        frontend_exclude=_extract_string_array(coverage_block, "exclude"),
    )


# --------------------------------------------------------------------------- classification

def classify_stack_role(path: str) -> tuple[str, str]:
    if path.startswith(SENSITIVE_PREFIXES):
        return "agent-config", "sensitive"
    if path.startswith("backend/"):
        if path.startswith("backend/tests/"):
            return "backend", "test"
        if path.startswith("backend/app/") and path.endswith(".py"):
            return "backend", "source"
        return "backend", "config"
    if path.startswith("frontend/"):
        name = path.rsplit("/", 1)[-1]
        if re.search(r"\.test\.tsx?$", name) or path.startswith("frontend/src/test/"):
            return "frontend", "test"
        if re.search(r"\.stories\.tsx?$", name):
            return "frontend", "story"
        if path.startswith("frontend/src/") and name.endswith(FRONTEND_SRC_SUFFIXES):
            return "frontend", "source"
        if path.startswith("frontend/src/") and name.endswith(".css"):
            return "frontend", "style"
        return "frontend", "config"
    if path.endswith(DOC_SUFFIXES):
        return "repo", "docs"
    return "repo", "config"


BACKEND_KINDS = {
    "router": "router", "repository": "repository", "validators": "validator",
    "mappers": "mapper", "schemas": "schema", "models": "model", "config": "config",
    "database": "core", "lifespan": "core", "factory": "core", "dependencies": "dependency",
    "health": "router", "main": "entrypoint",
}


def classify_kind(path: str, stack: str) -> str:
    stem = Path(path).stem
    if stack == "backend":
        return BACKEND_KINDS.get(stem, "module")
    if stack == "frontend":
        if "/design-system/" in path:
            return "design-system"
        if "/hooks/" in path or re.match(r"use[A-Z]", stem):
            return "hook"
        if "/api/" in path:
            return "api"
        if "/utils/" in path or "/lib/" in path:
            return "util"
        if stem.endswith("Page"):
            return "page"
        if path.endswith(".tsx"):
            return "component"
        return "module"
    return "other"


def test_path_for(path: str, stack: str) -> str | None:
    if stack == "backend" and path.startswith("backend/app/"):
        rel = Path(path.removeprefix("backend/app/"))
        return str(Path("backend/tests") / rel.parent / f"test_{rel.name}")
    if stack == "frontend" and path.startswith("frontend/src/"):
        p = Path(path)
        return str(p.with_name(f"{p.stem}.test{p.suffix}"))
    return None


# --------------------------------------------------------------------------- diffing

def changed_head_lines(old: str, new: str) -> list[int]:
    """1-based line numbers in `new` that were inserted or replaced."""
    matcher = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    lines: list[int] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            lines.extend(range(j1 + 1, j2 + 1))
    return lines


def _python_signature(source: str) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    # Drop docstrings: they do not change behaviour.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:]
    return ast.dump(tree, include_attributes=False)


_TS_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_TS_STRING = re.compile(r"""(['"`])(?:\\.|(?!\1).)*\1""", re.S)


def _ts_signature(source: str) -> str:
    """Heuristic: strip comments and all whitespace outside string literals."""
    strings: list[str] = []

    def keep(match: re.Match[str]) -> str:
        strings.append(match.group(0))
        return f"\x00{len(strings) - 1}\x00"

    protected = _TS_STRING.sub(keep, source)
    stripped = re.sub(r"\s+", "", _TS_COMMENT.sub("", protected))
    stripped = stripped.replace(";", "").replace(",)", ")").replace(",]", "]").replace(",}", "}")
    return re.sub(r"\x00(\d+)\x00", lambda m: strings[int(m.group(1))], stripped)


def classify_change(path: str, old: str | None, new: str | None) -> str:
    if old is None:
        return "added"
    if new is None:
        return "deleted"
    if path.endswith(".py"):
        a, b = _python_signature(old), _python_signature(new)
        if a is not None and a == b:
            return "cosmetic"
    elif path.endswith(FRONTEND_SRC_SUFFIXES):
        if _ts_signature(old) == _ts_signature(new):
            return "cosmetic"
    return "behavioral"


# --------------------------------------------------------------------------- model

@dataclass
class Target:
    path: str
    status: str                      # added | modified | deleted | unchanged
    stack: str
    role: str                        # source | test | story | style | config | docs | sensitive
    kind: str
    in_coverage_scope: bool
    change_class: str                # added | deleted | behavioral | cosmetic | n/a
    changed_lines: list[int] = field(default_factory=list)
    test_path: str | None = None
    test_exists: bool = False
    test_changed: bool = False
    pre_decision: str = "skip"       # candidate | skip
    skip_reason: str | None = None


def pre_decide(t: Target) -> None:
    if t.role != "source":
        t.pre_decision, t.skip_reason = "skip", f"not production source (role={t.role})"
    elif t.status == "deleted":
        t.pre_decision, t.skip_reason = "skip", "file deleted"
    elif not t.in_coverage_scope:
        t.pre_decision, t.skip_reason = "skip", "excluded from coverage by project config"
    elif t.change_class == "cosmetic":
        t.pre_decision, t.skip_reason = "skip", "cosmetic change only (comments/formatting/docstrings)"
    else:
        t.pre_decision, t.skip_reason = "candidate", None


def iter_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for p in root.rglob("*"):
        if p.is_dir() or p.is_symlink():
            continue
        rel = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        files[rel.as_posix()] = p
    return files


def read_text(p: Path | None) -> str | None:
    if p is None:
        return None
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def analyse(head_dir: Path, base_dir: Path | None, scope: CoverageScope) -> dict:
    head_files = iter_files(head_dir)
    base_files = iter_files(base_dir) if base_dir else {}
    full_scan = base_dir is None

    if full_scan:
        paths = sorted(head_files)
    else:
        paths = sorted(
            p for p in set(head_files) | set(base_files)
            if read_text(head_files.get(p)) != read_text(base_files.get(p))
            or (p in head_files) != (p in base_files)
        )

    changed_set = set(paths) if not full_scan else set()
    targets: list[Target] = []
    for path in paths:
        stack, role = classify_stack_role(path)
        old = None if full_scan else read_text(base_files.get(path))
        new = read_text(head_files.get(path))
        if full_scan:
            status, change_class, lines = "unchanged", "n/a", []
        else:
            status = "added" if old is None else "deleted" if new is None else "modified"
            change_class = classify_change(path, old, new)
            lines = changed_head_lines(old or "", new) if new is not None else []
        in_scope = (
            scope.backend_in_scope(path) if stack == "backend" and role == "source"
            else scope.frontend_in_scope(path) if stack == "frontend" and role == "source"
            else False
        )
        test_path = test_path_for(path, stack) if role == "source" else None
        t = Target(
            path=path, status=status, stack=stack, role=role,
            kind=classify_kind(path, stack), in_coverage_scope=in_scope,
            change_class=change_class, changed_lines=lines, test_path=test_path,
            test_exists=bool(test_path and test_path in head_files),
            test_changed=bool(test_path and test_path in changed_set),
        )
        pre_decide(t)
        targets.append(t)

    if full_scan:
        targets = [t for t in targets if t.role == "source"]

    candidates = [t for t in targets if t.pre_decision == "candidate"]
    return {
        "mode": "backfill" if full_scan else "pr",
        "summary": {
            "changed_files": len(paths) if not full_scan else 0,
            "candidates": len(candidates),
            "backend_candidates": sum(t.stack == "backend" for t in candidates),
            "frontend_candidates": sum(t.stack == "frontend" for t in candidates),
            "sensitive_paths": [t.path for t in targets if t.role == "sensitive"],
            "changed_source_lines": sum(len(t.changed_lines) for t in targets if t.role == "source"),
        },
        "coverage_scope": asdict(scope),
        "targets": [asdict(t) for t in targets],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--head-dir", type=Path, required=True, help="snapshot of the PR head (or repo root)")
    parser.add_argument("--base-dir", type=Path, help="snapshot of the base branch")
    parser.add_argument("--all", action="store_true", help="scan every source file (backfill mode)")
    parser.add_argument("--candidates-only", action="store_true")
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)

    if not args.all and args.base_dir is None:
        parser.error("either --base-dir or --all is required")

    scope = load_coverage_scope(args.head_dir)
    result = analyse(args.head_dir, None if args.all else args.base_dir, scope)
    if args.candidates_only:
        result["targets"] = [t for t in result["targets"] if t["pre_decision"] == "candidate"]

    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
