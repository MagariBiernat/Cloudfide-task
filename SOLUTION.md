# SOLUTION — Unit-test agent and agentic PR workflow

A Claude Code agent (`test-orchestrator`) with two writer subagents and six reusable skills
creates or updates unit tests for a pull request (or backfills the whole repo). A deterministic
pipeline, which trusts nothing the model says, gates, re-runs and publishes the result to the PR.

## Main technical decisions

| Decision | Rationale |
|---|---|
| **Claude Code headless** (`claude -p --agent test-orchestrator`), pinned CLI version | Native support for custom agents, subagents, skills, hooks and permission rules; one runtime locally and in CI. |
| **Orchestrator + 2 writers** (`backend-test-writer`, `frontend-test-writer`) | The orchestrator decides (create / update / skip / flag_suspected_bug); writers only write tests for their stack, in parallel, with stack-specific conventions loaded. |
| **Skills = instructions + deterministic scripts** | Anything that must be correct and repeatable (diff mapping, running tests, coverage, report validation) is a script. The model only makes judgement calls, and the pipeline calls the same scripts. |
| **Agent output is a patch, not a commit** | The agent works in a disposable copy (`.agent-out/workspace`). `make_patch.py` diffs it against head, and that patch is the only thing that leaves the agent job. |
| **Security gate outside the agent** (`gate.py`) | Rejects anything outside test paths, config changes, deletes/renames/symlinks, skip/focus markers, pytest hooks or result manipulation, new nested `conftest.py`, network hosts, process execution, secret access, credential-like literals, and size-limit breaches. Permissions and hooks inside the agent are defence in depth only. |
| **Independent verification without secrets** | A separate job applies the gated patch and runs the checks itself (detailed in the next row), without trusting the agent's report. |
| **Verify checks, in order** | `prettier --write` + `tsc` (frontend), each new test file run N× (shuffled for vitest), fails-on-base (the test must fail when the changed sources are swapped back to base), full suites before/after with coverage. Failing or flaky files are dropped; the rest stays. |
| **Split trust in the workflow** | `detect` (no code, no secrets) → `agent` (PR code + API key, `contents: read`, produces a patch) → `verify` (PR code, **no secrets**) → `publish` (write token, never executes PR code). |
| **Changed existing assertions are never auto-committed** | If the patch removes lines from an existing test file, publishing falls back to suggest-only with a warning, because weakening assertions could hide a regression. |

## Where the agent and skills live and how they are used

```
.claude/
  agents/test-orchestrator.md       custom agent: policy, decision rules, untrusted-data rules
  agents/backend-test-writer.md     pytest writer (skill: backend-test-conventions)
  agents/frontend-test-writer.md    Vitest + RTL writer (skill: frontend-test-conventions)
  skills/change-analysis/           map_changes.py: diff/whole repo -> targets, test path, kind, changed lines
  skills/coverage-insight/          coverage.py: uncovered changed lines, gaps, totals (coverage.py JSON / lcov)
  skills/test-runner/               run_tests.py: scrubbed env, timeout, JSON, --repeat/--shuffle, --against-base
  skills/test-report/               report.schema.json, validate_report.py, render_markdown.py (PR comment)
  skills/backend-test-conventions/  fixtures + patterns for routers, repository, validators, config, lifespan
  skills/frontend-test-conventions/ RTL/React Query helpers + patterns
  hooks/guard_paths.py              PreToolUse hook: writes only to test paths and .agent-report/
  agent-settings.json               tool allowlist (only the skill scripts are runnable), deny rules
.github/agent-scripts/pipeline.py   prepare -> agent -> gate -> verify -> report (same code locally and in CI)
.github/agent-scripts/gate.py       security gate;  make_patch.py  workspace -> patch
.github/workflows/unit-test-agent.yml  PR workflow;  ci.yml  regular tests + tests of the agent scripts
```

Run flow:

1. `prepare` snapshots base and head with `git archive`, so the repo is never touched.
   - It runs `change-analysis` and builds the workspace: head + the **trusted** `.claude/` from the base branch.
   - It decides whether the agent should run at all: no candidates, a too-large diff, or a PR that touches agent/CI config all skip it.
2. `agent`: the orchestrator does the analysis and the writing.
   - It reads `.agent-context/changes.json` and measures coverage (`test-runner`, `coverage-insight`).
   - It decides per file and delegates writing to the writers.
   - It re-runs the tests itself, then writes and validates `.agent-report/report.json` (`test-report`).
   - Credentials in its output are redacted before upload.
3. `gate` produces `agent.patch` and checks it with `gate.py`.
4. `verify` runs the independent checks described above (no model involved).
5. `report` / `publish` publishes the result in the PR (details under "Running the PR workflow").

## Running the PR workflow

Prerequisites (GitHub repository settings):

- **Settings → Environments → `test-agent`**, secret **`ANTHROPIC_API_KEY`** and **required reviewers**. This repository has them enabled, so every agent run waits for a maintainer's approval before the key is exposed.
  No deployment-branch policy is set: the agent job runs on the PR ref.
  Optional variables: `UTA_MODEL`, `UTA_MAX_BUDGET_USD` (default 5).
- **Settings → Actions → Workflow permissions → "Allow GitHub Actions to create and approve pull requests"**, needed only for backfill PRs. Without it the branch is pushed and the job summary links to it.
- Labels (optional): `test-agent:run`, `test-agent:skip`, `test-agent:suggest-only`:
  - `test-agent:run` allows a PR that changes agent/CI config, and re-triggers the workflow;
  - `test-agent:skip` opts the PR out;
  - `test-agent:suggest-only` posts the patch instead of committing it.

Triggers:

- **Automatic:** `pull_request` (opened / synchronize / reopened / ready_for_review / labeled) touching `backend/app`, `backend/tests` or `frontend/src`.
- **Fork PRs:** never run automatically. After review, a maintainer runs **Actions → unit-test-agent → Run workflow** with `pr_number` + `head_sha`.
- **Backfill:** the same dialog with `mode=backfill` opens a PR with tests for the whole repo.

Results in the PR:

- a sticky comment: per-file decision, verification, fails-on-base, coverage before/after, suspected bugs, gate findings;
- the job summary;
- a commit status `unit-test-agent` on the PR head;
- a bot commit with the verified tests, plus status `unit-test-agent/verify`, after which `ci.yml` is dispatched on it;
- for forks or suggest-only: the patch inside the comment, to apply with `git apply`.

Locally (same pipeline, publishing is a dry run):

```sh
make env                      # creates .env (chmod 600); fill ANTHROPIC_API_KEY
make pipeline                 # PR mode: origin/main..HEAD   (BASE=main HEAD=WORKTREE for uncommitted work)
make backfill                 # whole repo
make test-agent-scripts       # tests of the pipeline/skill scripts
# -> .agent-out/pr-comment.md, .agent-out/final.patch (git apply .agent-out/final.patch)
```

`pipeline.py` itself reads `.env`, or the file named by `UTA_ENV_FILE`. Credentials reach only the `claude`
process, never `npm ci`, `pip` or the tests. A non-empty shell variable wins over the file.

## Example run

### Backfill (`make backfill`, mode=backfill, Python 3.12 / Node 25)

| | |
|---|---|
| Agent | `test-orchestrator`, 16 turns, 283 s, **$1.46**, `report.json` validated |
| Skills used | `change-analysis` (33 candidates), `coverage-insight` (gaps), `test-runner`, `test-report`, plus `backend-/frontend-test-conventions` loaded by the writers |
| Decisions | **15 targets**: 7 create, 8 update. **18 skip** with a reason each (already 100 % covered, trivial wiring, or out of budget). No suspected bugs. |
| Gate | accepted, 15 files; `modified_existing_tests`: `TodosPage.test.tsx`, `TodoList.test.tsx` (child mocks replaced) → suggest-only |
| Verify | 13 files passed 3 repeated runs. **2 dropped by `tsc`**: `useCreateTodoMutation.test.tsx` and `todos.test.ts` pass in vitest but have type errors (`TodoInput` requires `completed`). |
| Backend | 21 → **64 tests**, lines **44.1 % → 98.6 %**, branches 30 % → 100 % |
| Frontend | 18 → **53 tests**, lines **47.7 % → 76.8 %**, branches 43.8 % → 60.6 % |

The agent's own summary claimed 88.7 % frontend coverage. The pipeline measured 76.8 %, because two files were
dropped after the agent finished. That gap is why the published numbers come from `verify`, never from the
report.

A second backfill (13 turns, 193 s, $1.11) targeted the remaining gaps: 9 more frontend files and `core/database.py`, all created or extended without touching existing assertions. All 10 files passed. Coverage: backend **98.6 % → 100 %** (68 tests), frontend **76.8 % → 98.7 %** (98 tests).

The first backfill ran locally, so there was no PR for the gate's suggest-only verdict to land in. I reviewed the patch by hand before committing it straight to `main`, including the two existing test files whose child mocks were replaced. That is the same human-review step the workflow enforces for PRs.

An earlier run on Python 3.14 is also instructive:

- The existing backend tests fail on 3.14 (`create_autospec` + lazy annotations).
- The agent tried to "fix" that by rewriting the shared `backend/tests/mocks.py`.
- The gate rejected the whole patch (shared fixtures are append-only) and the local run exited non-zero.
- The fix was environmental: the Makefile now builds the host venv with Python 3.12, the same as CI.

### Pull request: [#1 Add clear completed tasks action](https://github.com/MagariBiernat/Cloudfide-task/pull/1)

**The feature.** A `DELETE /api/todos/completed` endpoint (repository + router + schema), an API function, a `useClearCompletedMutation` hook and a header button. It was pushed **without tests**, and it broke 10 existing `TodosPage` tests (the new hook was not mocked).

**The run** ([workflow run](https://github.com/MagariBiernat/Cloudfide-task/actions/runs/42536088442)):

1. `detect` → `agent`, which waited for environment approval → `verify` → `publish`.
2. The agent ran for 172 s, 11 turns, $0.90.

| File | Decision | Verification (pipeline) |
|---|---|---|
| `repository.py` | update | 12 passed ×3, fails on base ✔ |
| `router.py` | update | 29 passed ×3, fails on base ✔ |
| `TodosPage.tsx` | update: mocks the new hook, adds the clear flow | 15 passed ×3, fails on base ✔ |
| `api/todos.ts` | update | 3 passed ×3, fails on base ✔ |
| `TodosHeader.tsx` | update | 5 passed ×3, fails on base ✔ |
| `useClearCompletedMutation.ts` | **create** | 4 passed ×3, fails on base ✔ |
| `schemas.py`, `queryKeys.ts` | skip: outside coverage scope | – |

| Stack | Suite before → after | Lines | Changed lines covered |
|---|---|---|---|
| backend | 64 → 70 passed | 96.0 % → 98.7 % | 55.6 % → 100 % |
| frontend | ❌ 43 passed (10 failing) → ✅ 67 passed | 62.6 % → 78.9 % | 31.2 % → 100 % |

**The result.** The gate flagged `TodosPage.test.tsx` as a changed existing test file: the only removed line is the signature of the `TodosHeader` mock. So the result was published as **suggest-only**: the sticky comment carries the verified patch, and no bot commit was made.

I reviewed the patch and applied it on the branch as a separate commit, after which CI on the PR turned green. A PR that changes no existing test gets the bot commit and the `unit-test-agent/verify` status instead.

## Assumptions

- Only **unit tests** are in scope:
  - backend: pytest with in-memory SQLite and the existing fixtures, no PostgreSQL;
  - frontend: Vitest + React Testing Library with jsdom.
- Coverage scope is read from the project's own config (`backend/pyproject.toml`, `frontend/vite.config.ts`). Files excluded there (schemas, models, types, stories) are not targets.
- The base branch is trusted. The PR branch, its title/body and its code are untrusted data.
- The model may be wrong. Correctness is established by the pipeline, not by the agent's report.

## Limitations

- **The `agent` job runs PR code with the API key in the process environment.** No network sandbox is enabled. On Linux, test code could read the `claude` process environment.
  - Mitigations: forks don't run automatically, test subprocesses get a scrubbed env, reads outside the workspace are denied, the gate rejects credential-like literals, and outputs are redacted.
  - Same-repo PRs can also edit the workflow file itself, so the `test-agent` environment protection is what really guards the secret.
  - Leak detection checks plain, reversed, hex and base64 forms of the key in the patch and in every uploaded output. A rejected or leaking patch is emptied before upload. A key split into pieces or encoded some other way is not detected. Only isolation closes that gap, not filtering.
- **fails-on-base is file-level, and it swaps every changed source of the stack at once.** It is a strong signal, not a per-test mutation score.
- **Backend flakiness is checked by repetition only, without random ordering.**
- **Pure deletions in a diff have no "changed lines"** to aim coverage at.
- **The skills hard-code the Taskly layout** (`backend/app`, `frontend/src`).
- **`max_targets` and the budget bound one run.** Backfilling a larger repo takes several runs.

## Production version: what I would change

- **Isolation:** run the agent and the tests in a network-isolated container (or the Claude Code sandbox) with egress only to the Anthropic API. Run the tests under a separate UID, with `out/` read-only to them.
- **Secret flow:** split the workflow into an unprivileged `pull_request` part and a privileged `workflow_run` part, so the workflow file itself always comes from the default branch.
- **Verification depth:** per-test fails-on-base and mutation testing (mutmut / Stryker) on the changed lines, plus shuffled backend runs (`pytest-randomly`).
- **Evidence:** a check run with annotations instead of a commit status, and a history of cost and decision quality per run.
- **Reuse:** a config file for stack roots and test-path templates, so the skills work in other repositories without code changes.
