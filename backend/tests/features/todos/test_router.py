import pytest

from app.features.todos.schemas import TodoCreate, TodoUpdate


def test_list_returns_tasks_from_repository(client, repository_mock, todo):
    repository_mock.list.return_value = [todo]
    response = client.get("/api/todos")
    assert response.status_code == 200
    assert response.json() == [todo.model_dump(mode="json")]
    repository_mock.list.assert_called_once_with()


def test_create_trims_input_and_returns_created_task(client, repository_mock, todo):
    repository_mock.create.return_value = todo
    response = client.post("/api/todos", json={"title": "  Plan the sprint  ", "priority": "high"})
    assert response.status_code == 201
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.create.assert_called_once_with(
        TodoCreate(title="Plan the sprint", priority="high")
    )


@pytest.mark.parametrize("payload", [
    {"title": "   "},
    {"title": "x" * 121},
    {"title": "Task", "priority": "urgent"},
    {"title": "Task", "due_date": "2026-02-30"},
])
def test_invalid_create_never_calls_repository(client, repository_mock, payload):
    assert client.post("/api/todos", json=payload).status_code == 422
    repository_mock.create.assert_not_called()


def test_get_returns_task(client, repository_mock, todo):
    repository_mock.get.return_value = todo
    response = client.get("/api/todos/7")
    assert response.status_code == 200
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.get.assert_called_once_with(7)


def test_get_missing_task_returns_404(client, repository_mock):
    repository_mock.get.return_value = None
    response = client.get("/api/todos/7")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}


def test_update_returns_updated_task(client, repository_mock, todo):
    repository_mock.update.return_value = todo
    response = client.patch("/api/todos/7", json={"title": "  Plan the sprint ", "completed": True})
    assert response.status_code == 200
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.update.assert_called_once_with(
        7, TodoUpdate(title="Plan the sprint", completed=True)
    )


def test_update_missing_task_returns_404(client, repository_mock):
    repository_mock.update.return_value = None
    response = client.patch("/api/todos/7", json={"title": "x"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}


@pytest.mark.parametrize("payload", [
    {},
    {"title": None},
    {"completed": "yes"},
    {"unknown": 1},
    {"title": "x" * 121},
])
def test_invalid_update_never_calls_repository(client, repository_mock, payload):
    assert client.patch("/api/todos/7", json=payload).status_code == 422
    repository_mock.update.assert_not_called()


def test_delete_returns_204_without_body(client, repository_mock):
    repository_mock.delete.return_value = True
    response = client.delete("/api/todos/7")
    assert response.status_code == 204
    assert response.content == b""
    repository_mock.delete.assert_called_once_with(7)


def test_delete_missing_task_returns_404(client, repository_mock):
    repository_mock.delete.return_value = False
    response = client.delete("/api/todos/7")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
@pytest.mark.parametrize("todo_id", ["0", "-1", "abc"])
def test_non_positive_or_non_numeric_id_is_rejected(client, repository_mock, method, todo_id):
    response = getattr(client, method)(f"/api/todos/{todo_id}", **(
        {"json": {"title": "x"}} if method == "patch" else {}
    ))
    assert response.status_code == 422
    repository_mock.get.assert_not_called()
    repository_mock.update.assert_not_called()
    repository_mock.delete.assert_not_called()
