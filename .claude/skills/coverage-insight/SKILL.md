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

```bash
S=.claude/skills/coverage-insight/scripts/coverage.py
R=.agent-report/cov-before

# Which changed lines are not executed by any test? (PR mode)
python3 $S changed --changes .agent-context/changes.json \
  --backend $R/backend-coverage.json --frontend $R/frontend-coverage/lcov.info --frontend-root frontend

# Biggest gaps (backfill mode)
python3 $S gaps --limit 12 --backend $R/backend-coverage.json \
  --frontend $R/frontend-coverage/lcov.info --frontend-root frontend

# Totals
python3 $S summary --backend $R/backend-coverage.json --frontend $R/frontend-coverage/lcov.info --frontend-root frontend
```

## Reading the numbers

- `changed.files[].uncovered_changed_lines` — the precise lines a new test should execute.
  Empty list + `changed_executable > 0` ⇒ already covered: usually `skip`, unless the PR
  changed behaviour that existing assertions do not check (then `update`).
- `measured: false` ⇒ the file was not loaded by any test at all (0 % — strong `create` signal).
- `lines_pct` counts executable lines only; coverage.py's own "Cover" column also mixes in
  branches, so numbers can differ by a few points. Report the numbers from this script.
- Coverage is evidence, not the goal: a covered line without an assertion on its effect is
  still untested behaviour.
