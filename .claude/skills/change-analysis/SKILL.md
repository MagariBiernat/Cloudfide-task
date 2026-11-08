---
name: change-analysis
description: Map a pull-request diff (two directory snapshots) or the whole repository to unit-test targets for the Taskly backend and frontend. Use before deciding which files need new or updated unit tests; tells you stack, kind, coverage scope, matching test file, changed lines and whether the change is behavioural or cosmetic.
---

# Change analysis

Deterministic first step of every test-generation run. Never guess which files changed or
which test file belongs to a source file — ask the script.

## Run

```bash
# PR mode: compare snapshots (the pipeline prepares them for you)
python3 .claude/skills/change-analysis/scripts/map_changes.py \
  --base-dir .agent-context/base --head-dir . --candidates-only

# Backfill mode: every source file in coverage scope
python3 .claude/skills/change-analysis/scripts/map_changes.py --all --head-dir . --candidates-only
```

In the pipeline the result is already in `.agent-context/changes.json`; read that instead of
re-running.

## Output fields (per `targets[]`)

| field | meaning |
|---|---|
| `stack` | `backend` \| `frontend` \| `repo` \| `agent-config` |
| `role` | `source`, `test`, `story`, `style`, `config`, `docs`, `sensitive` |
| `kind` | router, repository, validator, mapper, core, dependency, component, hook, api, util, page, … |
| `in_coverage_scope` | read live from `backend/pyproject.toml` `[tool.coverage.run]` and `frontend/vite.config.ts` `coverage.include/exclude` |
| `change_class` | `added`, `deleted`, `behavioral`, `cosmetic` (AST-equal Python / comment-and-whitespace-only TS) |
| `changed_lines` | 1-based head lines inserted or replaced |
| `test_path` / `test_exists` / `test_changed` | conventional test file, whether it exists, whether the PR touched it |
| `pre_decision` | `candidate` or `skip` + `skip_reason` |

## Mapping conventions

- `backend/app/<pkg>/<module>.py` → `backend/tests/<pkg>/test_<module>.py`
  (every test directory is a package: add `__init__.py` when creating a new one).
- `frontend/src/<path>/X.ts(x)` → `frontend/src/<path>/X.test.ts(x)` (co-located); `.tsx` for components and for `hooks/` (they need a JSX provider wrapper). An existing sibling `.ts`/`.tsx` test wins.

## Interpreting results

- `pre_decision: skip` is final for files outside coverage scope, deleted files, non-source
  files and cosmetic changes — record them in the report with the given reason.
- `candidate` means *may* need tests. Your decision (create/update/skip) also depends on
  whether the changed lines are already covered (`coverage-insight` skill).
- `summary.sensitive_paths` non-empty means the PR touches agent or CI configuration; the
  pipeline handles this — do not inspect or modify those files.
