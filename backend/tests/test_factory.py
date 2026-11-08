import asyncio
from unittest.mock import Mock, patch

from app.factory import create_app


def _paths(app):
    return set(app.openapi()["paths"])


def test_create_app_stores_resolved_database_url_and_metadata():
    app = create_app("sqlite://")
    assert app.state.database_url == "sqlite://"
    assert app.title == "Taskly API"
    assert app.version == "1.0.0"


def test_create_app_mounts_health_and_todos_routes():
    paths = _paths(create_app("sqlite://"))
    assert {"/api/health", "/api/todos", "/api/todos/{todo_id}"} <= paths


def test_create_app_does_not_open_database_until_lifespan_runs():
    app = create_app("sqlite://")
    assert not hasattr(app.state, "session_factory")


def test_create_app_lifespan_builds_session_factory_from_configured_url():
    app = create_app("sqlite://")
    engine = Mock()

    async def run():
        async with app.router.lifespan_context(app):
            return app.state.session_factory

    with patch("app.core.lifespan.create_database_engine", return_value=engine) as create, \
         patch("app.core.lifespan.initialize"), \
         patch("app.core.lifespan.create_session_factory", return_value="factory"):
        assert asyncio.run(run()) == "factory"
    create.assert_called_once_with("sqlite://")
    engine.dispose.assert_called_once_with()


def test_create_app_delegates_url_resolution():
    with patch("app.factory.resolve_database_url", return_value="resolved://") as resolve:
        app = create_app("explicit://")
    resolve.assert_called_once_with("explicit://")
    assert app.state.database_url == "resolved://"
