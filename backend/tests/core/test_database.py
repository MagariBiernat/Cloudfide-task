from sqlalchemy import create_engine, inspect

from app.core.database import (
    create_database_engine,
    create_session_factory,
    initialize,
)
from app.features.todos.models import Base


def test_engine_uses_the_postgresql_psycopg_driver():
    url = "postgresql+psycopg://taskly:taskly@localhost:5432/taskly"
    engine = create_database_engine(url)
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        assert engine.url.database == "taskly"
    finally:
        engine.dispose()


def test_engine_enables_pool_pre_ping():
    engine = create_database_engine(
        "postgresql+psycopg://taskly:taskly@localhost:5432/taskly"
    )
    try:
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()


def test_session_factory_binds_sessions_to_the_engine_without_expiring_on_commit():
    engine = create_engine("sqlite://")
    try:
        factory = create_session_factory(engine)
        assert factory.kw["bind"] is engine
        assert factory.kw["expire_on_commit"] is False
        with factory() as session:
            assert session.bind is engine
            assert session.expire_on_commit is False
    finally:
        engine.dispose()


def test_initialize_creates_the_tables_from_the_metadata():
    engine = create_engine("sqlite://")
    try:
        expected = set(Base.metadata.tables)
        assert expected
        assert inspect(engine).get_table_names() == []

        initialize(engine)

        assert expected <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_initialize_is_idempotent():
    engine = create_engine("sqlite://")
    try:
        initialize(engine)
        first = set(inspect(engine).get_table_names())

        initialize(engine)

        assert set(inspect(engine).get_table_names()) == first
    finally:
        engine.dispose()
