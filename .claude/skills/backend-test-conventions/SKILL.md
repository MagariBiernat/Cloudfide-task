---
name: backend-test-conventions
description: Conventions, fixtures and proven patterns for writing pytest unit tests for the Taskly FastAPI backend (routers, repository, validators, dependencies, config, lifespan, factory). Use whenever you create or update tests under backend/tests.
---

# Backend unit-test conventions (pytest)

Distilled from the existing suite in `backend/tests`. Match it — reviewers should not be able
to tell generated tests from hand-written ones. Examples: [reference/examples.md](reference/examples.md).

## Layout and style

- Mirror the package: `backend/app/features/todos/router.py` → `backend/tests/features/todos/test_router.py`.
  New test directories need an empty `__init__.py`.
- Plain functions, no classes: `def test_<behaviour_as_a_sentence>(...)`.
- `@pytest.mark.parametrize` for tables of invalid inputs.
- Assert both the outcome **and** the interaction (`assert_called_once_with`, `assert_not_called`).
- No real database, no network, no sleeps, no `skip`/`xfail`/`pragma: no cover`.

## Fixtures (`backend/tests/conftest.py`, `backend/tests/mocks.py`)

| fixture | what it gives you |
|---|---|
| `repository_mock` | `create_autospec(TodoRepository, instance=True)`, `list` returns `[]` |
| `client` | `TestClient` with **only the todos router** mounted and `get_repository` overridden |
| `todo_values` | dict of a valid stored task (id 7, UTC timestamps) |
| `todo` | `Todo` schema built from `todo_values` |
| `model_factory` | `lambda values: TodoRecord(**values)` |

Shared fixtures may be **added** (append to conftest), never changed or removed.

## Patterns by kind

- **Router** — use `client` + `repository_mock`. Check status code, JSON body
  (`todo.model_dump(mode="json")`), and the repository call. 404 paths: repository returns
  `None`/`False`. Validation (422): repository must not be called. Path rule `todo_id > 0`.
- **Repository** — `session = Mock(spec=Session)`; drive `session.get/scalars` return values;
  assert `add/commit/refresh/delete` calls and order (`session.mock_calls` or a `Mock()` parent
  with `attach_mock`). Compare SQL with `statement.compare(expected)`; compile with
  `postgresql.dialect()` for ORDER BY / WHERE text. For timestamps patch
  `app.features.todos.repository.datetime` or compare against a captured `before` value.
- **Dependencies** — build `Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(session_factory=...))})`,
  drive the generator with `next()`, `gen.close()`, `gen.throw(exc)`; assert `rollback()`/`close()`.
- **Health router** — mount `app.api.health.router` on a fresh `FastAPI()` and override
  `get_repository` (like `client`), assert `{"status": "ok"}` and `session.execute` called.
- **Config** — `resolve_database_url` calls `load_dotenv` on the real repo `.env`: always
  `monkeypatch.setattr("app.core.config.load_dotenv", lambda *a, **k: None)` and set/unset
  variables with `monkeypatch.setenv/delenv`.
- **Database** — engine behaviour may use `create_engine("sqlite://")` (in-memory, no network).
- **Lifespan** — patch `create_database_engine`, `initialize`, `create_session_factory` in
  `app.core.lifespan`; run with `asyncio.run(...)` around `async with lifespan(app):`
  (no pytest-asyncio installed). Assert `engine.dispose()` also runs when `initialize` raises.
- **Factory** — `create_app("sqlite://")` without entering the lifespan (do not use
  `with TestClient(app)`); inspect `app.routes` paths and `app.state.database_url`.
- **Schemas** (excluded from coverage, still behaviour) — `extra="forbid"`, `strict=True` on
  `completed`, whitespace stripping, length limits: test through the router or `model_validate`.

## Running

```bash
python3 .claude/skills/test-runner/scripts/run_tests.py backend --root . backend/tests/<file>.py
```
