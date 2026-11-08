---
name: test-runner
description: Run Taskly backend (pytest) or frontend (vitest) unit tests deterministically with a scrubbed environment and JSON results; supports repeat/shuffle flakiness checks, coverage collection and the fails-on-base check that proves a test exercises the change. Use whenever you need to execute tests — never call pytest, vitest, npm or npx directly.
---

# Test runner

One entry point for executing tests. It strips secrets from the environment (tests may come
from an untrusted PR), uses only locally installed binaries, enforces a timeout and returns
normalised JSON.

```bash
R=.claude/skills/test-runner/scripts/run_tests.py

# Specific files (paths repo-relative or stack-relative)
python3 $R backend  --root . backend/tests/features/todos/test_router.py
python3 $R frontend --root . frontend/src/lib/http.test.ts

# Whole suite with coverage
python3 $R backend --root . --coverage --out-dir .agent-report/cov

# Flakiness: N runs, random order (vitest); mixed results => status "flaky"
python3 $R frontend --root . frontend/src/lib/http.test.ts --repeat 3 --shuffle

# Fails-on-base: swap the changed sources for their base versions, run, restore
python3 $R backend --root . backend/tests/features/todos/test_router.py \
  --against-base .agent-context/base --swap backend/app/features/todos/router.py
```

## Result

```json
{"status": "passed|failed|flaky|error", "runs": [{"passed": 5, "failed": 0, "errors": 0,
 "skipped": 0, "failures": [{"test": "...", "message": "..."}], "duration_s": 3.1}]}
```

With `--against-base`: `fails_on_base: true` means the tests fail on the old code — good, they
pin down the new behaviour. `false` means they would also pass without the change ("weak").

## Rules

- Read `failures[].message` before changing anything; fix the test, never the code under test.
- `status: error` with `<run>`/`<vitest>` usually means an import/collection error in a test file.
- Never install dependencies; if `node_modules` or the venv is missing, report it and stop.
- Keep runs targeted (specific files) while iterating; run the full suite once at the end.
