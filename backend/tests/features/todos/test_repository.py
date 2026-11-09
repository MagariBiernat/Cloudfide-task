from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.features.todos.models import TodoRecord
from app.features.todos.repository import TodoRepository
from app.features.todos.schemas import Priority, TodoCreate, TodoUpdate


def test_list_maps_models_and_orders_tasks_newest_first(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.scalars.return_value = [model_factory(todo_values)]
    assert TodoRepository(session).list() == [todo]
    statement = session.scalars.call_args.args[0]
    expected = select(TodoRecord).order_by(TodoRecord.created_at.desc(), TodoRecord.id.desc())
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY todos.created_at DESC, todos.id DESC" in compiled


def test_get_returns_none_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).get(404) is None
    session.get.assert_called_once_with(TodoRecord, 404)


def test_get_returns_mapped_task_for_existing_record(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.get.return_value = model_factory(todo_values)
    assert TodoRepository(session).get(7) == todo
    session.get.assert_called_once_with(TodoRecord, 7)


def test_create_persists_record_with_timestamps_and_returns_refreshed_task(todo_values):
    session = Mock(spec=Session)
    fixed_now = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)
    added = []
    session.add.side_effect = added.append

    def assign_id(record):
        record.id = 11

    session.refresh.side_effect = assign_id
    with patch("app.features.todos.repository.datetime") as dt:
        dt.now.return_value = fixed_now
        result = TodoRepository(session).create(TodoCreate(title="Write tests", priority="low"))
    dt.now.assert_called_once_with(timezone.utc)
    record = added[0]
    assert (record.title, record.priority, record.completed) == ("Write tests", Priority.low, False)
    assert record.created_at == fixed_now
    assert record.updated_at == fixed_now
    assert result.id == 11
    assert result.title == "Write tests"
    assert [c[0] for c in session.mock_calls] == ["add", "commit", "refresh"]
    session.refresh.assert_called_once_with(record)


def test_update_returns_none_and_does_not_commit_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).update(404, TodoUpdate(title="New")) is None
    session.get.assert_called_once_with(TodoRecord, 404)
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


def test_update_applies_only_provided_fields_and_bumps_updated_at(model_factory, todo_values):
    session = Mock(spec=Session)
    record = model_factory(todo_values)
    session.get.return_value = record
    fixed_now = datetime(2026, 10, 3, 9, tzinfo=timezone.utc)
    with patch("app.features.todos.repository.datetime") as dt:
        dt.now.return_value = fixed_now
        result = TodoRepository(session).update(7, TodoUpdate(title="Renamed", completed=True))
    assert record.title == "Renamed"
    assert record.completed is True
    assert record.description == "First scenario"
    assert record.priority == "high"
    assert record.created_at == todo_values["created_at"]
    assert record.updated_at == fixed_now
    assert result.title == "Renamed"
    assert result.completed is True
    assert [c[0] for c in session.mock_calls] == ["get", "commit", "refresh"]
    session.refresh.assert_called_once_with(record)


def test_update_can_clear_due_date_with_explicit_null(model_factory, todo_values):
    session = Mock(spec=Session)
    record = model_factory({**todo_values, "due_date": date(2026, 12, 1)})
    session.get.return_value = record
    result = TodoRepository(session).update(7, TodoUpdate(due_date=None))
    assert record.due_date is None
    assert result.due_date is None


def test_delete_returns_false_and_does_not_commit_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).delete(404) is False
    session.get.assert_called_once_with(TodoRecord, 404)
    session.delete.assert_not_called()
    session.commit.assert_not_called()


def test_delete_removes_record_then_commits(model_factory, todo_values):
    session = Mock(spec=Session)
    record = model_factory(todo_values)
    session.get.return_value = record
    assert TodoRepository(session).delete(7) is True
    session.delete.assert_called_once_with(record)
    assert [c[0] for c in session.mock_calls] == ["get", "delete", "commit"]


def test_delete_completed_deletes_completed_rows_commits_and_returns_rowcount():
    session = Mock(spec=Session)
    session.execute.return_value.rowcount = 3
    assert TodoRepository(session).delete_completed() == 3
    statement = session.execute.call_args.args[0]
    expected = delete(TodoRecord).where(TodoRecord.completed.is_(True))
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "DELETE FROM todos WHERE todos.completed IS true" in compiled
    session.commit.assert_called_once_with()


def test_delete_completed_returns_zero_when_nothing_completed():
    session = Mock(spec=Session)
    session.execute.return_value.rowcount = 0
    assert TodoRepository(session).delete_completed() == 0
    session.execute.assert_called_once()
    session.commit.assert_called_once_with()
    session.delete.assert_not_called()


def test_delete_completed_executes_before_commit():
    session = Mock(spec=Session)
    session.execute.return_value.rowcount = 1
    TodoRepository(session).delete_completed()
    names = [c[0] for c in session.mock_calls if c[0] in ("execute", "commit")]
    assert names == ["execute", "commit"]
