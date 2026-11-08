#!/usr/bin/env python3
"""Run backend (pytest) or frontend (vitest) unit tests deterministically.

Stdlib-only. Guarantees:
  * a scrubbed environment: secrets (ANTHROPIC_*, GITHUB_*, *TOKEN*, *KEY*,
    *SECRET*, *PASSWORD*) never reach test code, which may come from an
    untrusted pull request;
  * only locally installed binaries are used (no `npx` downloads);
  * a hard timeout per run;
  * normalised JSON output: {status, runs:[{passed, failed, ..., failures}]}.

Extra modes:
  --repeat N         run N times; mixed outcomes => status "flaky"
  --shuffle          randomise test order (vitest --sequence.shuffle)
  --coverage         collect coverage (backend: coverage.json, frontend: lcov)
  --against-base DIR --swap a,b   temporarily replace source files with their
                     base-branch versions (from DIR) and report whether the
                     tests FAIL there ("fails_on_base"): a test that also
                     passes on the old code does not exercise the change.

Usage:
  run_tests.py backend  --root . tests/features/todos/test_router.py
  run_tests.py frontend --root . src/lib/http.test.ts --repeat 3 --shuffle
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TERM", "CI", "TZ", "USER")
SECRET_PATTERN = re.compile(r"(ANTHROPIC|GITHUB|GH_|TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|AWS_|AZURE_|GOOGLE_)", re.I)
MAX_MESSAGE = 1500


def scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_KEYS and not SECRET_PATTERN.search(k)}
    env.setdefault("TZ", "UTC")
    env["CI"] = "true"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    if extra:
        env.update(extra)
    return env


def resolve_python(root: Path) -> str:
    candidates = [
        os.environ.get("TASKLY_PYTHON"),
        str(root / "backend/.venv/bin/python"),
        str(Path(__file__).resolve().parents[4] / "backend/.venv/bin/python"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return sys.executable


def truncate(text: str | None) -> str:
    text = (text or "").strip()
    return text if len(text) <= MAX_MESSAGE else text[:MAX_MESSAGE] + "…[truncated]"


# --------------------------------------------------------------------------- backend

def run_backend(root: Path, files: list[str], coverage: bool, timeout: int, out_dir: Path) -> dict:
    backend = root / "backend"
    junit = out_dir / "pytest-junit.xml"
    cmd = [resolve_python(root), "-m", "pytest", "-c", "pyproject.toml", "-q", "-p", "no:cacheprovider",
           f"--junitxml={junit}", "-o", "junit_family=xunit2"]
    if coverage:
        cmd += ["--cov=app", f"--cov-report=json:{out_dir / 'backend-coverage.json'}",
                f"--cov-report=xml:{out_dir / 'backend-coverage.xml'}", "--cov-report=term"]
    cmd += [f.removeprefix("backend/") for f in files]
    proc, duration, timed_out = _exec(cmd, backend, timeout)
    result = _parse_junit(junit) if junit.exists() else _empty()
    return _finish(result, proc, duration, timed_out, cmd)


def _parse_junit(path: Path) -> dict:
    tree = ET.parse(path)
    result = _empty()
    for case in tree.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        failure = case.find("failure")
        error = case.find("error")
        if case.find("skipped") is not None:
            result["skipped"] += 1
        elif failure is not None or error is not None:
            node = failure if failure is not None else error
            result["failed" if failure is not None else "errors"] += 1
            result["failures"].append({"test": name, "message": truncate(node.get("message") or node.text)})
        else:
            result["passed"] += 1
    return result


# --------------------------------------------------------------------------- frontend

def run_frontend(root: Path, files: list[str], coverage: bool, shuffle: bool, timeout: int, out_dir: Path) -> dict:
    frontend = root / "frontend"
    vitest = frontend / "node_modules/.bin/vitest"
    if not vitest.exists():
        return {**_empty(), "status": "error", "errors": 1,
                "failures": [{"test": "<setup>", "message": f"{vitest} missing — run `npm ci` first"}]}
    report = out_dir / "vitest-report.json"
    cmd = [str(vitest), "run", "--reporter=json", f"--outputFile={report}", "--reporter=dot"]
    if shuffle:
        cmd.append("--sequence.shuffle")
    if coverage:
        cmd += ["--coverage", f"--coverage.reportsDirectory={out_dir / 'frontend-coverage'}"]
    cmd += [f.removeprefix("frontend/") for f in files]
    proc, duration, timed_out = _exec(cmd, frontend, timeout)
    result = _parse_vitest(report) if report.exists() else _empty()
    if not report.exists() and proc is not None and proc.returncode != 0:
        result["errors"] += 1
        result["failures"].append({"test": "<vitest>", "message": truncate((proc.stdout + proc.stderr)[-MAX_MESSAGE:])})
    return _finish(result, proc, duration, timed_out, cmd)


def _parse_vitest(path: Path) -> dict:
    data = json.loads(path.read_text())
    result = _empty()
    for suite in data.get("testResults", []):
        if suite.get("status") == "failed" and not suite.get("assertionResults"):
            result["errors"] += 1
            result["failures"].append({"test": suite.get("name", "<suite>"), "message": truncate(suite.get("message"))})
        for a in suite.get("assertionResults", []):
            status = a.get("status")
            if status == "passed":
                result["passed"] += 1
            elif status in ("skipped", "pending", "todo"):
                result["skipped"] += 1
            else:
                result["failed"] += 1
                result["failures"].append({
                    "test": f"{Path(suite.get('name', '')).name}::{a.get('fullName') or a.get('title')}",
                    "message": truncate("\n".join(a.get("failureMessages") or [])),
                })
    return result


# --------------------------------------------------------------------------- shared

def _empty() -> dict:
    return {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "failures": []}


def _exec(cmd: list[str], cwd: Path, timeout: int):
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=scrubbed_env(), capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
        return proc, time.monotonic() - start, False
    except subprocess.TimeoutExpired:
        return None, time.monotonic() - start, True


def _finish(result: dict, proc, duration: float, timed_out: bool, cmd: list[str]) -> dict:
    result["duration_s"] = round(duration, 2)
    result["command"] = " ".join(cmd)
    if timed_out:
        result["exit_code"] = None
        result["errors"] += 1
        result["failures"].append({"test": "<timeout>", "message": "test run exceeded the timeout"})
    else:
        result["exit_code"] = proc.returncode
        result["output_tail"] = truncate(proc.stdout[-MAX_MESSAGE:] + proc.stderr[-500:])
        if proc.returncode != 0 and not (result["failed"] or result["errors"]):
            # e.g. collection error, coverage threshold, crash before report
            result["errors"] += 1
            result["failures"].append({"test": "<run>", "message": result["output_tail"]})
    total = result["passed"] + result["failed"] + result["errors"]
    result["status"] = "error" if timed_out or total == 0 else "passed" if result["exit_code"] == 0 else "failed"
    return result


def run_once(args, files: list[str], out_dir: Path) -> dict:
    if args.stack == "backend":
        return run_backend(args.root, files, args.coverage, args.timeout, out_dir)
    return run_frontend(args.root, files, args.coverage, args.shuffle, args.timeout, out_dir)


def against_base(args, files: list[str], out_dir: Path) -> dict:
    """Swap given source files for their base versions, run, always restore."""
    swaps = [s for s in (args.swap or "").split(",") if s]
    if not swaps:
        raise SystemExit("--against-base requires --swap path1,path2")
    backup = Path(tempfile.mkdtemp(prefix="base-swap-"))
    restored: list[tuple[Path, Path | None]] = []
    try:
        for rel in swaps:
            target = args.root / rel
            saved = None
            if target.exists():
                saved = backup / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            restored.append((target, saved))
            base_file = args.against_base / rel
            if base_file.exists():
                shutil.copy2(base_file, target)
            elif target.exists():
                target.unlink()  # file is new in the PR: it does not exist on base
        result = run_once(args, files, out_dir)
    finally:
        for target, saved in restored:
            if saved is not None:
                shutil.copy2(saved, target)
            elif target.exists():
                target.unlink()
        shutil.rmtree(backup, ignore_errors=True)
    result["fails_on_base"] = result["status"] != "passed"
    result["swapped"] = swaps
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stack", choices=["backend", "frontend"])
    parser.add_argument("files", nargs="*", help="test files (repo-relative or stack-relative); empty = full suite")
    parser.add_argument("--root", type=Path, default=Path("."), help="project root (contains backend/ and frontend/)")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--timeout", type=int, default=300, help="seconds per run")
    parser.add_argument("--against-base", type=Path, help="directory with the base-branch snapshot")
    parser.add_argument("--swap", help="comma-separated source paths to swap with base versions")
    parser.add_argument("--out-dir", type=Path, help="where reports go (default: temp dir)")
    parser.add_argument("--output", type=Path, help="write JSON result here (default: stdout)")
    args = parser.parse_intermixed_args(argv)
    args.root = args.root.resolve()

    out_dir = (args.out_dir or Path(tempfile.mkdtemp(prefix="tests-"))).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.against_base:
        summary = against_base(args, args.files, out_dir)
        summary.update(stack=args.stack, files=args.files)
    else:
        runs = [run_once(args, args.files, out_dir) for _ in range(max(1, args.repeat))]
        statuses = {r["status"] for r in runs}
        status = statuses.pop() if len(statuses) == 1 else "flaky"
        summary = {"stack": args.stack, "files": args.files, "status": status, "repeat": len(runs), "runs": runs}

    summary["reports_dir"] = str(out_dir)
    payload = json.dumps(summary, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    print(payload if not args.output else json.dumps({"status": summary["status"], "output": str(args.output)}))
    return 0 if summary["status"] == "passed" or (args.against_base and summary.get("fails_on_base")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
