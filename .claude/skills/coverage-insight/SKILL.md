---
name: coverage-insight
description: Read Taskly coverage reports (pytest coverage.py JSON, vitest lcov) and answer which changed lines are uncovered, which files are the biggest coverage gaps, and how coverage moved between base and head. Use to decide whether tests are needed and to prove the effect of new tests.
---

# Coverage insight

## 1. Produce reports

Use the `test-runner` skill with `--coverage` and `--out-dir`:

```bash
python3 .claude/skills/test-runner/scripts/run_tests.py backend  --root . --coverage --out-dir .agent-report/cov-before
python3 .claude/skills/test-runner/scripts/run_tests.py frontend --root . --coverage --out-dir .agent-report/cov-before
```

Reports: `<out>/backend-coverage.json` and `<out>/frontend-coverage/lcov.info`.

## 2. Ask questions

One literal command per line (no shell variables or `\` continuations — only the literal
`python3 .claude/skills/...` prefix is allowed to run):

```bash
# Which changed lines are not executed by any test? (PR mode)
python3 .claude/skills/coverage-insight/scripts/coverage.py changed --changes .agent-context/changes.json --backend .agent-report/cov-before/backend-coverage.json --frontend .agent-report/cov-before/frontend-coverage/lcov.info --frontend-root frontend

# Biggest gaps (backfill mode)
python3 .claude/skills/coverage-insight/scripts/coverage.py gaps --limit 12 --backend .agent-report/cov-before/backend-coverage.json --frontend .agent-report/cov-before/frontend-coverage/lcov.info --frontend-root frontend

# Totals
python3 .claude/skills/coverage-insight/scripts/coverage.py summary --backend .agent-report/cov-before/backend-coverage.json --frontend .agent-report/cov-before/frontend-coverage/lcov.info --frontend-root frontend
```

## Reading the numbers

- `changed.files[].uncovered_changed_lines` — the precise lines a new test should execute.
  Empty list + `changed_executable > 0` ⇒ already covered: usually `skip`, unless the PR
  changed behaviour that existing assertions do not check (then `update`).
- `measured: false` ⇒ the file was not loaded by any test at all (0 % — strong `create` signal),
  provided the report itself exists. No report file at all means the run failed — fix that first.
- `lines_pct` counts executable lines only; coverage.py's own "Cover" column also mixes in
  branches, so numbers can differ by a few points. Report the numbers from this script.
- Coverage is evidence, not the goal: a covered line without an assertion on its effect is
  still untested behaviour.
