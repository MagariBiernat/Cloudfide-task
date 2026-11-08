---
name: test-report
description: Write and validate the unit-test agent's machine-readable report (.agent-report/report.json) — one entry per analysed file with the decision, reason, tests added and verification result. Use at the end of every orchestrator run; the pipeline renders it into the pull-request comment.
---

# Test report

The report is the contract between the agent and the pipeline. The pipeline **re-verifies**
everything (gate, re-run, flakiness, fails-on-base, coverage) and shows both your claims and
its own measurements, so report honestly — mismatches are highlighted to reviewers.

## Schema (`schema/report.schema.json`)

```json
{
  "mode": "pr",
  "summary": "One or two sentences for humans.",
  "files": [
    {
      "source": "backend/app/features/todos/router.py",
      "stack": "backend",
      "decision": "update",
      "reason": "New DELETE /completed endpoint; changed lines 41-47 uncovered.",
      "test_files": ["backend/tests/features/todos/test_router.py"],
      "tests_added": ["test_clear_completed_returns_deleted_count"],
      "verification": {"status": "passed", "runs": 2, "fails_on_base": true, "weak": false},
      "coverage": {"changed_lines_before": 0.0, "changed_lines_after": 100.0}
    },
    {
      "source": "README.md", "stack": "repo", "decision": "skip",
      "reason": "Documentation only.", "test_files": [], "tests_added": [],
      "verification": {"status": "not_run"}
    }
  ],
  "suspected_bugs": [
    {"source": "…", "description": "…", "evidence": "expected X, got Y"}
  ],
  "skills_used": ["change-analysis", "coverage-insight", "test-runner", "backend-test-conventions", "test-report"],
  "warnings": []
}
```

- `decision`: `create` | `update` | `skip` | `flag_suspected_bug`.
- `verification.status`: `passed` | `failed` | `flaky` | `not_run`. Every `create`/`update` must
  be `passed`, otherwise remove the tests and use `skip` (with the reason) or `flag_suspected_bug`.
- Include **every** file from `changes.json` targets (PR mode) so reviewers see skip decisions too.
- `reason` is mandatory and specific (which behaviour, which lines) — not "added tests".

## Validate before finishing

```bash
python3 .claude/skills/test-report/scripts/validate_report.py .agent-report/report.json --changes .agent-context/changes.json
```

Exit code 0 = valid. Fix every reported error.

## Rendering (pipeline side)

`scripts/render_markdown.py` merges the report with the pipeline's own verification results
into the sticky PR comment and the job summary. You never call it yourself.
