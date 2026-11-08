import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = {
    "map_changes": REPO / ".claude/skills/change-analysis/scripts/map_changes.py",
    "coverage_tool": REPO / ".claude/skills/coverage-insight/scripts/coverage.py",
    "run_tests": REPO / ".claude/skills/test-runner/scripts/run_tests.py",
    "validate_report": REPO / ".claude/skills/test-report/scripts/validate_report.py",
    "render_markdown": REPO / ".claude/skills/test-report/scripts/render_markdown.py",
    "gate": REPO / ".github/agent-scripts/gate.py",
    "make_patch": REPO / ".github/agent-scripts/make_patch.py",
    "pipeline": REPO / ".github/agent-scripts/pipeline.py",
}
GUARD_HOOK = REPO / ".claude/hooks/guard_paths.py"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"uta_{name}", SCRIPTS[name])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def mods():
    return {name: load(name) for name in SCRIPTS}


@pytest.fixture
def project(tmp_path):
    """Minimal project tree with the real coverage configuration."""
    root = tmp_path / "head"
    (root / "backend").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "backend/pyproject.toml").write_text((REPO / "backend/pyproject.toml").read_text())
    (root / "frontend/vite.config.ts").write_text((REPO / "frontend/vite.config.ts").read_text())
    return root


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
