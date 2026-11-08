from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from app.api.dependencies import get_repository
from app.features.todos.repository import TodoRepository


def test_session_creation_failure_propagates_from_repository_dependency():
    session_factory = Mock(side_effect=RuntimeError("Session unavailable"))
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))
    request = Request({"type": "http", "app": app})
    dependency = get_repository(request)
    with pytest.raises(RuntimeError, match="Session unavailable"):
        next(dependency)
    session_factory.assert_called_once_with()


def _request(session):
    app = SimpleNamespace(state=SimpleNamespace(session_factory=Mock(return_value=session)))
    return Request({"type": "http", "app": app})


def test_dependency_yields_repository_bound_to_session_and_closes_it():
    session = Mock()
    dependency = get_repository(_request(session))
    repository = next(dependency)
    assert isinstance(repository, TodoRepository)
    assert repository.session is session
    session.close.assert_not_called()
    dependency.close()
    session.close.assert_called_once_with()
    session.rollback.assert_not_called()


def test_dependency_rolls_back_closes_and_reraises_on_error():
    session = Mock()
    dependency = get_repository(_request(session))
    next(dependency)
    with pytest.raises(ValueError, match="boom"):
        dependency.throw(ValueError("boom"))
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()
