#!/usr/bin/env python3
"""Normalise coverage reports and answer the questions the agent needs.

Stdlib-only. Inputs:
  backend:  coverage.py JSON  (pytest --cov-report=json)
  frontend: lcov.info         (vitest --coverage, reporter "lcov")

Sub-commands:
  summary   totals + per-file line coverage and missing lines
  changed   coverage of the *changed* lines from map_changes.py output
  gaps      ranked backfill targets (most uncovered lines first)
  delta     compare two `summary` outputs (base vs head)

Paths are always reported repo-relative (backend/app/..., frontend/src/...).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_backend(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text())
    files = {}
    for name, info in data.get("files", {}).items():
        rel = "backend/" + name.lstrip("./") if not name.startswith("backend/") else name
        executable = set(info.get("executed_lines", [])) | set(info.get("missing_lines", []))
        summary = info.get("summary", {})
        files[rel] = {
            "executable": sorted(executable),
            "missing": sorted(info.get("missing_lines", [])),
            "branches_total": summary.get("num_branches", 0),
            "branches_covered": summary.get("covered_branches", 0),
        }
    return files


def load_lcov(path: Path, frontend_root: Path | None = None) -> dict[str, dict]:
    files: dict[str, dict] = {}
    current: dict | None = None
    name = ""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            source = line[3:]
            p = Path(source)
            if p.is_absolute() and frontend_root is not None:
                try:
                    source = p.resolve().relative_to(frontend_root.resolve()).as_posix()
                except ValueError:
                    source = p.as_posix()
            idx = source.find("src/")
            name = "frontend/" + (source[idx:] if idx >= 0 else source)
            current = {"executable": [], "missing": [], "branches_total": 0, "branches_covered": 0}
        elif current is None:
            continue
        elif line.startswith("DA:"):
            lineno, hits = line[3:].split(",")[:2]
            current["executable"].append(int(lineno))
            if int(hits) == 0:
                current["missing"].append(int(lineno))
        elif line.startswith("BRF:"):
            current["branches_total"] = int(line[4:])
        elif line.startswith("BRH:"):
            current["branches_covered"] = int(line[4:])
        elif line == "end_of_record":
            files[name] = current
            current = None
    return files


def pct(covered: int, total: int) -> float | None:
    return round(100.0 * covered / total, 2) if total else None


def summarise(files: dict[str, dict]) -> dict:
    lines_total = sum(len(f["executable"]) for f in files.values())
    lines_missing = sum(len(f["missing"]) for f in files.values())
    br_total = sum(f["branches_total"] for f in files.values())
    br_cov = sum(f["branches_covered"] for f in files.values())
    return {
        "totals": {
            "lines_total": lines_total,
            "lines_covered": lines_total - lines_missing,
            "lines_pct": pct(lines_total - lines_missing, lines_total),
            "branches_total": br_total,
            "branches_covered": br_cov,
            "branches_pct": pct(br_cov, br_total),
        },
        "files": {
            name: {
                "lines_pct": pct(len(f["executable"]) - len(f["missing"]), len(f["executable"])),
                "missing": f["missing"],
            }
            for name, f in sorted(files.items())
        },
    }


def load_all(args) -> dict[str, dict]:
    files: dict[str, dict] = {}
    if args.backend and args.backend.exists():
        files.update(load_backend(args.backend))
    if args.frontend and args.frontend.exists():
        files.update(load_lcov(args.frontend, args.frontend_root))
    return files


def changed_coverage(files: dict[str, dict], changes: dict) -> dict:
    result = {"files": [], "totals": {}}
    total_exec = total_cov = 0
    for t in changes.get("targets", []):
        if t.get("pre_decision") != "candidate":
            continue
        cov = files.get(t["path"])
        changed = set(t.get("changed_lines", []))
        if cov is None:
            result["files"].append({"path": t["path"], "measured": False, "changed_executable": None,
                                    "uncovered_changed_lines": None, "pct": None})
            continue
        executable = changed & set(cov["executable"])
        uncovered = sorted(executable & set(cov["missing"]))
        total_exec += len(executable)
        total_cov += len(executable) - len(uncovered)
        result["files"].append({
            "path": t["path"], "measured": True, "changed_executable": len(executable),
            "uncovered_changed_lines": uncovered, "pct": pct(len(executable) - len(uncovered), len(executable)),
        })
    result["totals"] = {"changed_executable": total_exec, "changed_covered": total_cov,
                        "pct": pct(total_cov, total_exec)}
    return result


def gaps(files: dict[str, dict], limit: int) -> list[dict]:
    ranked = sorted(
        ({"path": n, "missing_lines": len(f["missing"]),
          "lines_pct": pct(len(f["executable"]) - len(f["missing"]), len(f["executable"]))}
         for n, f in files.items() if f["missing"]),
        key=lambda g: (-g["missing_lines"], g["path"]),
    )
    return ranked[:limit]


def delta(base: dict, head: dict) -> dict:
    out = {}
    for stack in ("backend", "frontend"):
        b, h = base.get(stack, {}).get("totals", {}), head.get(stack, {}).get("totals", {})
        entry = {}
        for key in ("lines_pct", "branches_pct"):
            bv, hv = b.get(key), h.get(key)
            entry[key] = {"base": bv, "head": hv,
                          "delta": round(hv - bv, 2) if bv is not None and hv is not None else None}
        out[stack] = entry
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("summary", "changed", "gaps"):
        p = sub.add_parser(name)
        p.add_argument("--backend", type=Path, help="coverage.py JSON")
        p.add_argument("--frontend", type=Path, help="lcov.info")
        p.add_argument("--frontend-root", type=Path, help="frontend dir, to relativise absolute lcov paths")
        if name == "changed":
            p.add_argument("--changes", type=Path, required=True, help="map_changes.py JSON")
        if name == "gaps":
            p.add_argument("--limit", type=int, default=15)
    d = sub.add_parser("delta")
    d.add_argument("--base", type=Path, required=True)
    d.add_argument("--head", type=Path, required=True)
    for p in list(sub.choices.values()):
        p.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "summary":
        result = {}
        if args.backend and args.backend.exists():
            result["backend"] = summarise(load_backend(args.backend))
        if args.frontend and args.frontend.exists():
            result["frontend"] = summarise(load_lcov(args.frontend, args.frontend_root))
    elif args.cmd == "changed":
        result = changed_coverage(load_all(args), json.loads(args.changes.read_text()))
    elif args.cmd == "gaps":
        result = {"gaps": gaps(load_all(args), args.limit)}
    else:
        result = delta(json.loads(args.base.read_text()), json.loads(args.head.read_text()))

    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
