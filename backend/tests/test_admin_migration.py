import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def migration_config(url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def exercise_migration(engine, config):
    command.upgrade(config, "20261112_0015")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT id FROM admin_write_lock")).scalar_one() == 1
        connection.execute(text("INSERT INTO admin_audit (actor_id, action, changes) VALUES (1, 'user.update', '{}')"))
    with pytest.raises(RuntimeError, match="audit records"):
        command.downgrade(config, "20261112_0014")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM admin_audit"))
    command.downgrade(config, "20261112_0014")
    assert "admin_audit" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT email FROM users WHERE id = 1")).scalar_one() == "owner@example.test"
    command.upgrade(config, "20261112_0015")


def test_admin_migration_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    config = migration_config(str(engine.url))
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('20261112_0014')"))
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(320))"))
            connection.execute(text("INSERT INTO users VALUES (1, 'owner@example.test')"))
        exercise_migration(engine, config)
    finally:
        engine.dispose()


def test_admin_migration_postgresql(monkeypatch):
    url = os.getenv("TEST_ADMIN_MIGRATION_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_ADMIN_MIGRATION_POSTGRESQL_URL is not configured.")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    engine = create_engine(url)
    config = migration_config(url)
    try:
        command.upgrade(config, "20261112_0014")
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (id, email, password_hash) VALUES (1, 'owner@example.test', 'hash')"
            ))
        exercise_migration(engine, config)
    finally:
        engine.dispose()
