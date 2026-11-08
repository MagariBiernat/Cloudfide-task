from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_repository
from app.api.health import router
from app.features.todos.models import TodoRecord
from app.features.todos.repository import TodoRepository


@pytest.fixture
def session():
    return Mock(spec=Session)


@pytest.fixture
def health_client(session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: TodoRepository(session)
    with TestClient(app) as client:
        yield client


def test_health_reports_ok_after_probing_database(health_client, session):
    response = health_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    session.execute.assert_called_once()
    statement = session.execute.call_args.args[0]
    assert "FROM todos" in str(statement)
    assert "LIMIT" in str(statement)
    assert TodoRecord.__tablename__ == "todos"


def test_health_fails_when_database_probe_raises(session):
    session.execute.side_effect = RuntimeError("db down")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: TodoRepository(session)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/health")
    assert response.status_code == 500
