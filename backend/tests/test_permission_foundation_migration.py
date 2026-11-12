import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from app.permissions import DelegablePermission


def test_permission_foundation_upgrade_and_downgrade(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "foundation.db"
    engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", str(engine.url))

    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            ))
            connection.execute(text("INSERT INTO alembic_version VALUES ('20261104_0008')"))
        command.upgrade(config, "20261110_0009")
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = '20261111_0013'"))
            connection.execute(text(
                "CREATE TABLE auth_sessions (id INTEGER PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id))"
            ))
            connection.execute(text("INSERT INTO bars (id, name) VALUES (-1, 'Bar Legacy'), (2, 'Altro')"))
            connection.execute(text(
                "INSERT INTO users (id, email, password_hash) VALUES "
                "(1, 'owner@example.test', 'hash'), (2, 'staff@example.test', 'hash')"
            ))
            connection.execute(text(
                "INSERT INTO user_bar_memberships (id, user_id, bar_id, role) VALUES "
                "(1, 1, -1, 'owner'), (2, 2, -1, 'manager'), (3, 2, 2, 'staff')"
            ))
            connection.execute(text("INSERT INTO auth_sessions VALUES (1, 1)"))
        command.upgrade(config, "20261112_0014")
        with engine.begin() as connection:
            assert connection.execute(text(
                "SELECT id, is_global_admin FROM users ORDER BY id"
            )).all() == [(1, 0), (2, 0)]
            assert connection.execute(text(
                "SELECT id, user_id, bar_id, role FROM user_bar_memberships ORDER BY id"
            )).all() == [(1, 1, -1, "owner"), (2, 2, -1, "manager"), (3, 2, 2, "staff")]
            assert connection.execute(text("SELECT COUNT(*) FROM membership_permissions")).scalar_one() == 0
            connection.execute(text(
                "INSERT INTO users (id, email, password_hash) VALUES (3, 'new@example.test', 'hash')"
            ))
            assert connection.execute(text(
                "SELECT is_global_admin FROM users WHERE id = 3"
            )).scalar_one() == 0
            for permission in DelegablePermission:
                connection.execute(text(
                    "INSERT INTO membership_permissions (membership_id, permission) VALUES (2, :code)"
                ), {"code": permission.value})
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO membership_permissions (membership_id, permission) "
                    "VALUES (2, 'cash_closures.approve')"
                ))

        with pytest.raises(RuntimeError, match="membership permissions"):
            command.downgrade(config, "20261111_0013")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM membership_permissions"))
            connection.execute(text("UPDATE users SET is_global_admin = :value WHERE id = 1"), {"value": True})
        with pytest.raises(RuntimeError, match="global administrators"):
            command.downgrade(config, "20261111_0013")
        with engine.begin() as connection:
            connection.execute(text("UPDATE users SET is_global_admin = :value WHERE id = 1"), {"value": False})

        command.downgrade(config, "20261111_0013")
        assert "membership_permissions" not in inspect(engine).get_table_names()
        assert "is_global_admin" not in {c["name"] for c in inspect(engine).get_columns("users")}
        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM user_bar_memberships")).scalar_one() == 3
            assert connection.execute(text("SELECT id FROM bars WHERE id = -1")).scalar_one() == -1
            assert connection.execute(text("SELECT user_id FROM auth_sessions")).scalar_one() == 1
        command.upgrade(config, "20261112_0014")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT SUM(is_global_admin) FROM users")).scalar_one() == 0
    finally:
        engine.dispose()


def test_permission_foundation_on_temporary_postgresql(monkeypatch):
    database_url = os.getenv("TEST_PERMISSION_POSTGRESQL_URL")
    if not database_url:
        pytest.skip("TEST_PERMISSION_POSTGRESQL_URL is not configured.")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "20261111_0013")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO bars (id, name) VALUES (1, 'Test')"))
            connection.execute(text(
                "INSERT INTO users (id, email, password_hash) VALUES (1, 'owner@example.test', 'hash')"
            ))
            connection.execute(text(
                "INSERT INTO user_bar_memberships (id, user_id, bar_id, role) VALUES (1, 1, 1, 'owner')"
            ))
        command.upgrade(config, "20261112_0014")
        with engine.begin() as connection:
            assert connection.execute(text("SELECT is_global_admin FROM users WHERE id = 1")).scalar_one() is False
            assert connection.execute(text("SELECT COUNT(*) FROM membership_permissions")).scalar_one() == 0
            for permission in DelegablePermission:
                connection.execute(text(
                    "INSERT INTO membership_permissions (membership_id, permission) VALUES (1, :code)"
                ), {"code": permission.value})
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO membership_permissions (membership_id, permission) "
                    "VALUES (1, 'cash_closures.approve')"
                ))
        with pytest.raises(RuntimeError, match="membership permissions"):
            command.downgrade(config, "20261111_0013")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM membership_permissions"))
        command.downgrade(config, "20261111_0013")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT role FROM user_bar_memberships WHERE id = 1")).scalar_one() == "owner"
        command.upgrade(config, "20261112_0014")
    finally:
        engine.dispose()
