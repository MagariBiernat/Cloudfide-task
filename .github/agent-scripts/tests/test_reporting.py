import json
import os
import subprocess
import sys

import pytest

from conftest import GUARD_HOOK, write

LCOV = """TN:
SF:{root}/src/lib/http.ts
DA:1,1
DA:2,0
DA:3,0
BRF:2
BRH:1
end_of_record
"""


def test_lcov_paths_are_made_repo_relative_and_lines_counted(mods, tmp_path):
    frontend = tmp_path / "frontend"
    lcov = write(tmp_path, "lcov.info", LCOV.format(root=frontend))
    files = mods["coverage_tool"].load_lcov(lcov, frontend)
    assert files["frontend/src/lib/http.ts"]["missing"] == [2, 3]
    totals = mods["coverage_tool"].summarise(files)["totals"]
    assert totals["lines_pct"] == pytest.approx(33.33)
    assert totals["branches_pct"] == 50.0


def test_changed_coverage_reports_uncovered_changed_lines(mods, tmp_path):
    files = {"backend/app/x.py": {"executable": [1, 2, 3, 5], "missing": [3, 5],
                                  "branches_total": 0, "branches_covered": 0}}
    changes = {"targets": [
        {"path": "backend/app/x.py", "pre_decision": "candidate", "changed_lines": [2, 3, 4]},
        {"path": "backend/app/y.py", "pre_decision": "candidate", "changed_lines": [1]},
        {"path": "README.md", "pre_decision": "skip", "changed_lines": [1]},
    ]}
    result = mods["coverage_tool"].changed_coverage(files, changes)
    x, y = result["files"]
    assert x["uncovered_changed_lines"] == [3] and x["pct"] == 50.0
    assert y["measured"] is False
    assert result["totals"] == {"changed_executable": 2, "changed_covered": 1, "pct": 50.0}


def test_coverage_delta_handles_missing_stack(mods):
    base = {"backend": {"totals": {"lines_pct": 40.0, "branches_pct": 30.0}}}
    head = {"backend": {"totals": {"lines_pct": 95.5, "branches_pct": 90.0}}}
    d = mods["coverage_tool"].delta(base, head)
    assert d["backend"]["lines_pct"]["delta"] == 55.5
    assert d["frontend"]["lines_pct"]["delta"] is None


def valid_report(**overrides):
    report = {
        "mode": "pr", "summary": "Added router tests.", "skills_used": ["test-runner"], "warnings": [],
        "files": [{
            "source": "backend/app/features/todos/router.py", "stack": "backend", "decision": "update",
            "reason": "New endpoint lines 40-47 uncovered.",
            "test_files": ["backend/tests/features/todos/test_router.py"], "tests_added": ["test_a"],
            "verification": {"status": "passed", "runs": 2, "fails_on_base": True},
        }],
    }
    report.update(overrides)
    return report


def test_valid_report_passes_schema_and_rules(mods):
    v = mods["validate_report"]
    schema = json.loads(v.SCHEMA_PATH.read_text())
    assert v.validate_schema(valid_report(), schema) == []
    assert v.validate_rules(valid_report(), None) == []


def test_report_rules_reject_unverified_or_misplaced_tests(mods):
    v = mods["validate_report"]
    report = valid_report()
    report["files"][0]["verification"]["status"] = "failed"
    report["files"][0]["test_files"] = ["backend/app/features/todos/router.py"]
    errors = v.validate_rules(report, None)
    assert any("must have verification.status=passed" in e for e in errors)
    assert any("is not a test path" in e for e in errors)


def test_report_must_cover_every_changed_file_in_pr_mode(mods):
    changes = {"targets": [{"path": "README.md", "role": "docs"},
                           {"path": "backend/app/features/todos/router.py", "role": "source"}]}
    errors = mods["validate_report"].validate_rules(valid_report(), changes)
    assert errors == ["$.files: missing decision for changed file README.md"]


def test_schema_rejects_unknown_fields_and_decisions(mods):
    v = mods["validate_report"]
    schema = json.loads(v.SCHEMA_PATH.read_text())
    report = valid_report(extra=1)
    report["files"][0]["decision"] = "rewrite_source"
    errors = v.validate_schema(report, schema)
    assert any("unexpected property 'extra'" in e for e in errors)
    assert any("rewrite_source" in e for e in errors)


def test_rendered_comment_neutralises_untrusted_agent_text(mods, tmp_path):
    out = tmp_path
    write(out, "pr.json", json.dumps({"mode": "pr", "base_sha": "a" * 40, "head_sha": "b" * 40}))
    write(out, "decision.json", json.dumps({"run_agent": True, "reason": "x", "stacks": ["backend"]}))
    write(out, "changes.json", json.dumps({"targets": [
        {"path": "backend/app/x.py", "pre_decision": "candidate", "skip_reason": None},
        {"path": "README.md", "pre_decision": "skip", "skip_reason": "not production source"},
    ]}))
    write(out, "agent-status.json", json.dumps({"ran": True, "duration_s": 10, "cost_usd": 0.5}))
    write(out, "gate.json", json.dumps({"accepted": True, "problems": []}))
    write(out, "verify.json", json.dumps({"status": "passed", "test_files": {}, "suites": {}, "dropped": []}))
    write(out, "report.json", json.dumps(valid_report(
        summary="<img src=x onerror=alert(1)> ping @org/admins",
        files=[{**valid_report()["files"][0], "source": "backend/app/x.py", "reason": "a | b"}])))
    body = mods["render_markdown"].render(out, "commit", None)
    assert "<img" not in body and "&lt;img" in body
    assert "@org" not in body and "@​org" in body
    assert "a \\| b" in body
    assert body.startswith(mods["render_markdown"].MARKER)
    assert "1 file(s) skipped" in body
    assert "committed to this branch" in body


def run_hook(project, file_path):
    event = {"tool_name": "Write", "tool_input": {"file_path": file_path}, "cwd": str(project)}
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run([sys.executable, str(GUARD_HOOK)], input=json.dumps(event),
                          capture_output=True, text=True, env=env)


@pytest.mark.parametrize("rel, allowed", [
    ("backend/tests/features/todos/test_router.py", True),
    ("frontend/src/lib/http.test.ts", True),
    ("frontend/src/test/renderWithClient.tsx", True),
    (".agent-report/report.json", True),
    ("backend/app/features/todos/router.py", False),
    ("frontend/src/lib/http.ts", False),
    ("frontend/src/test/setup.ts", False),
    (".claude/agent-settings.json", False),
    ("../outside.py", False),
])
def test_guard_hook_only_allows_test_paths(tmp_path, rel, allowed):
    proc = run_hook(tmp_path, str(tmp_path / rel))
    assert (proc.returncode == 0) is allowed, proc.stderr


def test_test_runner_environment_never_contains_secrets(mods, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    env = mods["run_tests"].scrubbed_env()
    assert not any(k in env for k in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY"))
    assert env["CI"] == "true" and "PATH" in env


def test_pipeline_filters_patch_by_file(mods, tmp_path):
    patch = write(tmp_path, "a.patch",
                  "diff --git a/x.test.ts b/x.test.ts\n+a\ndiff --git a/y.test.ts b/y.test.ts\n+b\n")
    out = tmp_path / "f.patch"
    mods["pipeline"].filter_patch(patch, out, {"y.test.ts"})
    assert out.read_text() == "diff --git a/y.test.ts b/y.test.ts\n+b\n"
