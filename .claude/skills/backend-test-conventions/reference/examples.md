# Backend examples (from the existing suite)

## Router: outcome + interaction

```python
def test_create_trims_input_and_returns_created_task(client, repository_mock, todo):
    repository_mock.create.return_value = todo
    response = client.post("/api/todos", json={"title": "  Plan the sprint  ", "priority": "high"})
    assert response.status_code == 201
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.create.assert_called_once_with(
        TodoCreate(title="Plan the sprint", priority="high")
    )
```

## Router: invalid input table

```python
@pytest.mark.parametrize("payload", [
    {"title": "   "},
    {"title": "x" * 121},
    {"title": "Task", "priority": "urgent"},
    {"title": "Task", "due_date": "2026-02-30"},
])
def test_invalid_create_never_calls_repository(client, repository_mock, payload):
    assert client.post("/api/todos", json=payload).status_code == 422
    repository_mock.create.assert_not_called()
```

## Repository: mocked session + SQL comparison

```python
def test_list_maps_models_and_orders_tasks_newest_first(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.scalars.return_value = [model_factory(todo_values)]
    assert TodoRepository(session).list() == [todo]
    statement = session.scalars.call_args.args[0]
    expected = select(TodoRecord).order_by(TodoRecord.created_at.desc(), TodoRecord.id.desc())
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY todos.created_at DESC, todos.id DESC" in compiled
```

## Dependency generator

```python
def test_session_creation_failure_propagates_from_repository_dependency():
    session_factory = Mock(side_effect=RuntimeError("Session unavailable"))
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))
    request = Request({"type": "http", "app": app})
    dependency = get_repository(request)
    with pytest.raises(RuntimeError, match="Session unavailable"):
        next(dependency)
    session_factory.assert_called_once_with()
```

## Lifespan (pattern, not yet in the suite)

```python
def test_lifespan_disposes_engine_even_when_initialisation_fails(monkeypatch):
    engine = Mock()
    monkeypatch.setattr("app.core.lifespan.create_database_engine", lambda url: engine)
    monkeypatch.setattr("app.core.lifespan.initialize", Mock(side_effect=RuntimeError("boom")))
    app = SimpleNamespace(state=SimpleNamespace(database_url="sqlite://"))

    async def run():
        async with lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(run())
    engine.dispose.assert_called_once_with()
```
