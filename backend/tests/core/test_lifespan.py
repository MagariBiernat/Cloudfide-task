import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.core.lifespan import lifespan


def _app():
    return SimpleNamespace(state=SimpleNamespace(database_url="sqlite://"))


def test_lifespan_initializes_database_and_exposes_session_factory_then_disposes():
    app = _app()
    engine = Mock()
    factory = Mock()
    seen = {}

    async def run():
        async with lifespan(app):
            seen["factory"] = app.state.session_factory
            engine.dispose.assert_not_called()

    with patch("app.core.lifespan.create_database_engine", return_value=engine) as create, \
         patch("app.core.lifespan.initialize") as init, \
         patch("app.core.lifespan.create_session_factory", return_value=factory) as make_factory:
        asyncio.run(run())

    create.assert_called_once_with("sqlite://")
    init.assert_called_once_with(engine)
    make_factory.assert_called_once_with(engine)
    assert seen["factory"] is factory
    engine.dispose.assert_called_once_with()


def test_lifespan_disposes_engine_when_initialize_fails():
    app = _app()
    engine = Mock()

    async def run():
        async with lifespan(app):
            pass

    with patch("app.core.lifespan.create_database_engine", return_value=engine), \
         patch("app.core.lifespan.initialize", side_effect=RuntimeError("init failed")), \
         patch("app.core.lifespan.create_session_factory") as make_factory:
        with pytest.raises(RuntimeError, match="init failed"):
            asyncio.run(run())

    make_factory.assert_not_called()
    assert not hasattr(app.state, "session_factory")
    engine.dispose.assert_called_once_with()
