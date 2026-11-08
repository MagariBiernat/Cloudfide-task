import shutil

import pytest

from conftest import REPO, write


@pytest.mark.parametrize("pattern, path, expected", [
    ("src/**/*.{ts,tsx}", "src/a/b/c.tsx", True),
    ("src/**/*.{ts,tsx}", "src/c.ts", True),
    ("src/**/*.{ts,tsx}", "src/c.css", False),
    ("src/**/types.ts", "src/types.ts", True),
    ("src/**/index.ts", "src/features/todos/index.ts", True),
    ("src/design-system/**", "src/design-system/x/Button.tsx", True),
    ("src/main.tsx", "src/app/main.tsx", False),
])
def test_glob_to_regex_matches_picomatch_semantics(mods, pattern, path, expected):
    assert bool(mods["map_changes"].glob_to_regex(pattern).match(path)) is expected


def test_coverage_scope_is_read_from_the_real_project_config(mods):
    scope = mods["map_changes"].load_coverage_scope(REPO)
    assert scope.backend_in_scope("backend/app/features/todos/router.py")
    assert not scope.backend_in_scope("backend/app/features/todos/schemas.py")
    assert not scope.backend_in_scope("backend/app/main.py")
    assert not scope.backend_in_scope("backend/tests/test_x.py")
    assert scope.frontend_in_scope("frontend/src/lib/http.ts")
    assert not scope.frontend_in_scope("frontend/src/lib/queryClient.ts")
    assert not scope.frontend_in_scope("frontend/src/design-system/components/Button/Button.tsx")
    assert not scope.frontend_in_scope("frontend/src/features/todos/types.ts")


def test_missing_vite_coverage_block_fails_loudly(mods, project):
    (project / "frontend/vite.config.ts").write_text("export default {}")
    with pytest.raises(ValueError):
        mods["map_changes"].load_coverage_scope(project)


@pytest.mark.parametrize("path, stack, expected", [
    ("backend/app/features/todos/router.py", "backend", "backend/tests/features/todos/test_router.py"),
    ("backend/app/factory.py", "backend", "backend/tests/test_factory.py"),
    ("frontend/src/lib/http.ts", "frontend", "frontend/src/lib/http.test.ts"),
    ("frontend/src/features/todos/TodosPage.tsx", "frontend", "frontend/src/features/todos/TodosPage.test.tsx"),
    ("frontend/src/features/todos/hooks/useTodos.ts", "frontend", "frontend/src/features/todos/hooks/useTodos.test.tsx"),
])
def test_test_path_follows_repository_conventions(mods, path, stack, expected):
    assert mods["map_changes"].test_path_for(path, stack) == expected


@pytest.mark.parametrize("old, new, expected", [
    ("def f():\n    return 1\n", "def f():\n    # explain\n    return 1\n", "cosmetic"),
    ('def f():\n    return 1\n', 'def f():\n    """Doc."""\n    return 1\n', "cosmetic"),
    ("def f():\n    return 1\n", "def f():\n    return 2\n", "behavioral"),
])
def test_python_changes_are_classified_by_ast(mods, old, new, expected):
    assert mods["map_changes"].classify_change("backend/app/x.py", old, new) == expected


@pytest.mark.parametrize("old, new, expected", [
    ("export const a = 1\n", "// note\nexport const a = 1;\n", "cosmetic"),
    ("export const a = 'x  y'\n", "export const a = 'x y'\n", "behavioral"),
    ("export const a = 1\n", "export const a = 2\n", "behavioral"),
])
def test_typescript_changes_ignore_comments_and_whitespace_only(mods, old, new, expected):
    assert mods["map_changes"].classify_change("frontend/src/x.ts", old, new) == expected


def test_changed_head_lines_reports_inserted_and_replaced_lines(mods):
    assert mods["map_changes"].changed_head_lines("a\nb\nc\n", "a\nB\nc\nd\n") == [2, 4]


def test_pr_analysis_pre_decides_candidates_and_skips(mods, project, tmp_path):
    base = tmp_path / "base"
    shutil.copytree(project, base)
    write(base, "backend/app/features/todos/router.py", "def f():\n    return 1\n")
    write(base, "frontend/src/lib/http.ts", "export const a = 1\n")
    write(project, "backend/app/features/todos/router.py", "def f():\n    return 2\n")
    write(project, "frontend/src/lib/http.ts", "// only a comment\nexport const a = 1\n")
    write(project, "backend/app/features/todos/schemas.py", "X = 1\n")
    write(project, "frontend/src/styles.css", "body{}")
    write(project, "README.md", "# docs\n")
    write(project, ".github/workflows/x.yml", "on: push\n")

    scope = mods["map_changes"].load_coverage_scope(project)
    result = mods["map_changes"].analyse(project, base, scope)
    by_path = {t["path"]: t for t in result["targets"]}

    assert by_path["backend/app/features/todos/router.py"]["pre_decision"] == "candidate"
    assert by_path["backend/app/features/todos/router.py"]["changed_lines"] == [2]
    assert by_path["frontend/src/lib/http.ts"]["skip_reason"].startswith("cosmetic")
    assert by_path["backend/app/features/todos/schemas.py"]["skip_reason"].startswith("excluded from coverage")
    assert by_path["frontend/src/styles.css"]["role"] == "style"
    assert by_path["README.md"]["role"] == "docs"
    assert result["summary"]["sensitive_paths"] == [".github/workflows/x.yml"]
    assert result["summary"]["candidates"] == 1


def test_backfill_lists_only_source_files(mods, project):
    write(project, "backend/app/core/config.py", "X = 1\n")
    write(project, "backend/tests/test_x.py", "def test_x():\n    assert True\n")
    scope = mods["map_changes"].load_coverage_scope(project)
    result = mods["map_changes"].analyse(project, None, scope)
    assert [t["path"] for t in result["targets"]] == ["backend/app/core/config.py"]
    assert result["mode"] == "backfill"


def test_existing_sibling_test_file_wins_over_the_preferred_extension(mods):
    head = {"frontend/src/features/todos/hooks/useNotice.test.ts": "x"}
    assert mods["map_changes"].existing_test_path(
        "frontend/src/features/todos/hooks/useNotice.ts", "frontend", head
    ) == "frontend/src/features/todos/hooks/useNotice.test.ts"
