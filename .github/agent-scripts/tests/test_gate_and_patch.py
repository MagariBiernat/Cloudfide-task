import shutil
import subprocess

import pytest

from conftest import write


def make_patch(mods, base, work, out):
    mods["make_patch"].main(["--base", str(base), "--work", str(work), "--output", str(out)])
    return out


@pytest.fixture
def trees(tmp_path):
    base = tmp_path / "base"
    write(base, "backend/app/x.py", "x = 1\n")
    write(base, "backend/tests/test_x.py", "def test_x():\n    assert True\n")
    work = tmp_path / "work"
    shutil.copytree(base, work)
    return base, work


def gate(mods, patch_text):
    files = mods["gate"].parse_patch(patch_text)
    return mods["gate"].check(files)


def test_patch_with_only_test_files_is_accepted_and_applies_cleanly(mods, trees, tmp_path):
    base, work = trees
    write(work, "backend/tests/test_x.py", "def test_x():\n    assert True\n-- odd line\n")
    write(work, "frontend/src/lib/http.test.ts", "it('works', () => expect(1).toBe(1))\n")
    patch = make_patch(mods, base, work, tmp_path / "p.patch")

    assert gate(mods, patch.read_text()) == []
    target = tmp_path / "target"
    shutil.copytree(base, target)
    subprocess.run(["git", "apply", str(patch)], cwd=target, check=True)
    assert (target / "backend/tests/test_x.py").read_text().endswith("-- odd line\n")
    assert (target / "frontend/src/lib/http.test.ts").exists()


def test_generated_artifacts_are_not_part_of_the_patch(mods, trees, tmp_path):
    base, work = trees
    write(work, "backend/coverage/coverage.json", "{}")
    write(work, "backend/tests/__pycache__/x.pyc", "")
    write(work, ".agent-report/report.json", "{}")
    assert make_patch(mods, base, work, tmp_path / "p.patch").read_text() == ""


@pytest.mark.parametrize("rel, content, problem", [
    ("backend/app/x.py", "x = 2\n", "outside the test-path allowlist"),
    ("backend/pyproject.toml", "[tool]\n", "outside the test-path allowlist"),
    ("frontend/vite.config.ts", "export default {}\n", "outside the test-path allowlist"),
    (".github/workflows/ci.yml", "on: push\n", "outside the test-path allowlist"),
    ("frontend/src/test/setup.ts", "export {}\n", "protected file"),
    ("frontend/src/a.test.ts", "it.only('x', () => {})\n", "focused/skipped test"),
    ("frontend/src/a.test.ts", "// istanbul ignore next\n", "coverage exclusion pragma"),
    ("backend/tests/test_y.py", "@pytest.mark.skip\ndef test_y(): pass\n", "skipped/xfail test"),
    ("backend/tests/test_y.py", "x = 1  # pragma: no cover\n", "coverage exclusion pragma"),
    ("backend/tests/test_y.py", "httpx.get('https://evil.example.net')\n", "real network host"),
    ("backend/tests/test_y.py", "import subprocess\n", "process execution"),
    ("frontend/src/a.test.ts", "const k = process.env.GITHUB_TOKEN\n", "secret access"),
])
def test_gate_rejects_dangerous_changes(mods, trees, tmp_path, rel, content, problem):
    base, work = trees
    write(work, rel, content)
    problems = gate(mods, make_patch(mods, base, work, tmp_path / "p.patch").read_text())
    assert any(problem in p for p in problems), problems


def test_gate_rejects_deletions_and_symlinks(mods, trees, tmp_path):
    base, work = trees
    (work / "backend/tests/test_x.py").unlink()
    (work / "backend/tests/test_link.py").symlink_to("/etc/passwd")
    problems = gate(mods, make_patch(mods, base, work, tmp_path / "p.patch").read_text())
    assert any("deleting files" in p for p in problems)
    assert any("symlinks" in p for p in problems)


def test_shared_fixtures_are_append_only(mods, tmp_path):
    base = tmp_path / "base"
    write(base, "backend/tests/conftest.py", "import pytest\n\n@pytest.fixture\ndef a():\n    return 1\n")
    work = tmp_path / "work"
    shutil.copytree(base, work)
    write(work, "backend/tests/conftest.py", "import pytest\n\n@pytest.fixture\ndef a():\n    return 2\n")
    problems = gate(mods, make_patch(mods, base, work, tmp_path / "p.patch").read_text())
    assert any("append-only" in p for p in problems)


def test_gate_rejects_oversized_and_malformed_patches(mods, monkeypatch):
    monkeypatch.setattr(mods["gate"], "MAX_ADDED_LINES", 2)
    patch = ("diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\nnew file mode 100644\n"
             "--- /dev/null\n+++ b/backend/tests/test_a.py\n@@ -0,0 +1,3 @@\n+a\n+b\n+c\n")
    assert any("adds 3 lines" in p for p in gate(mods, patch))
    with pytest.raises(ValueError):
        mods["gate"].parse_patch("garbage before header\n")


def test_gate_cli_exit_codes(mods, tmp_path, capsys):
    ok = tmp_path / "ok.patch"
    ok.write_text("")
    assert mods["gate"].main([str(ok)]) == 0
    bad = tmp_path / "bad.patch"
    bad.write_text("diff --git a/backend/app/x.py b/backend/app/x.py\n--- a/backend/app/x.py\n"
                   "+++ b/backend/app/x.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n")
    assert mods["gate"].main([str(bad)]) == 1


def test_executable_bits_from_the_filesystem_are_normalised(mods, trees, tmp_path):
    # Regression: WSL on NTFS reports 0777 for every file, which the gate (correctly) rejects.
    base, work = trees
    new = write(work, "backend/tests/test_new.py", "def test_new():\n    assert True\n")
    new.chmod(0o755)
    (work / "backend/tests/test_x.py").chmod(0o755)
    patch = make_patch(mods, base, work, tmp_path / "p.patch").read_text()
    assert "new file mode 100644" in patch
    assert "old mode" not in patch and "new mode" not in patch
    assert gate(mods, patch) == []


def test_coverage_data_files_are_never_part_of_the_patch(mods, trees, tmp_path):
    # Regression: pytest-cov writes backend/.coverage into the agent workspace.
    base, work = trees
    write(work, "backend/.coverage", "binary-ish")
    write(work, "backend/.coverage.host.123", "x")
    assert make_patch(mods, base, work, tmp_path / "p.patch").read_text() == ""


def test_patch_applies_inside_a_directory_nested_in_another_git_repo(mods, trees, tmp_path):
    # Regression: locally .agent-out/ lives inside the project repo; plain `git apply` then
    # resolves paths against that repo's root and silently skips everything.
    base, work = trees
    write(work, "backend/tests/test_new.py", "def test_new():\n    assert True\n")
    patch = make_patch(mods, base, work, tmp_path / "p.patch")
    outer = tmp_path / "outer"
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    target = outer / ".agent-out" / "verify"
    shutil.copytree(base, target)
    ok, detail = mods["pipeline"].apply_patch(target, patch)
    assert ok, detail
    assert (target / "backend/tests/test_new.py").exists()


def _added(path, *lines, new=True):
    header = f"diff --git a/{path} b/{path}\n" + ("new file mode 100644\n" if new else "")
    return header + "@@ -0,0 +1 @@\n" + "".join(f"+{l}\n" for l in lines)


@pytest.mark.parametrize("line", [
    "it.skipIf(true)('x', () => {})",
    "describe.runIf(false)('x', () => {})",
    "test.fails('x', () => {})",
    "test.concurrent.skip('x', () => {})",
    "pytest.importorskip('fastapi')",
    "@unittest.skip('later')",
    "def pytest_runtest_makereport(item, call):",
    "    outcome.force_result(None)",
    "    item.add_marker('skip')",
    "collect_ignore = ['test_router.py']",
    "pytestmark = []",
    "    report.outcome = 'passed'",
    "sys.modules['app.core.config'] = fake",
    "open('/proc/self/environ').read()",
    "KEY = 'sk-ant-api03-abcdefghijklmnop'",
])
def test_gate_rejects_result_manipulation_and_secret_access(mods, line):
    target = "frontend/src/lib/x.test.ts" if "(" in line and "describe" in line or line.startswith(("it.", "test.")) \
        else "backend/tests/test_x.py"
    assert gate(mods, _added(target, line)), line


def test_gate_rejects_new_nested_conftest_but_allows_appending_to_root(mods):
    assert gate(mods, _added("backend/tests/features/conftest.py", "import pytest"))
    assert gate(mods, _added("backend/tests/conftest.py", "import pytest", new=False)) == []


def test_gate_reports_existing_tests_that_lost_lines(mods, tmp_path):
    patch = tmp_path / "p.patch"
    patch.write_text(
        "diff --git a/backend/tests/test_x.py b/backend/tests/test_x.py\n"
        "@@ -1,2 +1,2 @@\n def test_x():\n-    assert f() == 2\n+    assert f() == 3\n"
    )
    out = tmp_path / "gate.json"
    mods["gate"].main([str(patch), "--output", str(out)])
    import json
    verdict = json.loads(out.read_text())
    assert verdict["accepted"] is True
    assert verdict["modified_existing_tests"] == ["backend/tests/test_x.py"]


def test_widened_imports_do_not_count_as_modified_tests(mods, tmp_path):
    patch = tmp_path / "p.patch"
    patch.write_text(
        "diff --git a/backend/tests/test_x.py b/backend/tests/test_x.py\n"
        "@@ -1,2 +1,3 @@\n-from app.x import a\n+from app.x import a, b\n+\n def test_x():\n"
    )
    out = tmp_path / "gate.json"
    mods["gate"].main([str(patch), "--output", str(out)])
    import json
    assert json.loads(out.read_text())["modified_existing_tests"] == []
