import pytest

from app.core.config import resolve_database_url

PG_VARS = {
    "POSTGRES_USER": "taskly",
    "POSTGRES_PASSWORD": "p@ssword",
    "POSTGRES_HOST": "db.local",
    "DB_PORT": "5433",
    "POSTGRES_DB": "tasks",
}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setattr("app.core.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for name in PG_VARS:
        monkeypatch.delenv(name, raising=False)


def test_explicit_argument_wins_over_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env.db")
    assert resolve_database_url("sqlite:///arg.db") == "sqlite:///arg.db"


def test_database_url_environment_variable_is_used_when_no_argument(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env.db")
    assert resolve_database_url() == "sqlite:///env.db"


def test_url_is_built_from_postgres_variables(monkeypatch):
    for name, value in PG_VARS.items():
        monkeypatch.setenv(name, value)
    url = resolve_database_url()
    assert url == "postgresql+psycopg://taskly:p%40ssword@db.local:5433/tasks"


def test_missing_postgres_variable_raises_key_error(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "taskly")
    with pytest.raises(KeyError):
        resolve_database_url()


def test_dotenv_is_loaded_without_override(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.core.config.load_dotenv", lambda *a, **k: calls.append((a, k))
    )
    resolve_database_url("sqlite://")
    assert len(calls) == 1
    assert calls[0][0][0].name == ".env"
    assert calls[0][1] == {"override": False}
