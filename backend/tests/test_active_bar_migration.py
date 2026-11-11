import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def test_migration_0012_adds_nullable_active_bar_foreign_key(tmp_path, monkeypatch):
    database = tmp_path / "active-bar-migration.db"
    engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE users ("
                    "id INTEGER NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE bars ("
                    "id INTEGER NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE auth_sessions ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                    "token_hash VARCHAR(64) NOT NULL UNIQUE, "
                    "csrf_token_hash VARCHAR(64) NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "expires_at DATETIME NOT NULL, "
                    "revoked_at DATETIME)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE alembic_version ("
                    "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text("INSERT INTO alembic_version VALUES ('20261111_0011')")
            )

        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        command.upgrade(config, "20261111_0012")

        inspector = inspect(engine)
        active_bar_column = next(
            column
            for column in inspector.get_columns("auth_sessions")
            if column["name"] == "active_bar_id"
        )
        assert active_bar_column["nullable"] is True
        active_bar_foreign_key = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys("auth_sessions")
            if foreign_key["name"] == "fk_auth_sessions_active_bar_id_bars"
        )
        assert active_bar_foreign_key["constrained_columns"] == ["active_bar_id"]
        assert active_bar_foreign_key["referred_table"] == "bars"
        assert active_bar_foreign_key["referred_columns"] == ["id"]
        assert active_bar_foreign_key["options"]["ondelete"] == "SET NULL"

        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id) VALUES (1)"))
            connection.execute(text("INSERT INTO bars (id) VALUES (9)"))
            connection.execute(
                text(
                    "INSERT INTO auth_sessions "
                    "(id, user_id, active_bar_id, token_hash, csrf_token_hash, "
                    "created_at, expires_at) "
                    "VALUES (1, 1, 9, 't' || replace(hex(randomblob(32)), ' ', ''), "
                    "'csrf', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(text("DELETE FROM bars WHERE id = 9"))
            assert connection.execute(
                text("SELECT active_bar_id FROM auth_sessions WHERE id = 1")
            ).scalar_one() is None
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "20261111_0012"
    finally:
        engine.dispose()


def test_migration_0012_downgrade_removes_only_session_bar_reference(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "active-bar-downgrade.db"
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE bars (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE auth_sessions ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                    "token_hash VARCHAR(64) NOT NULL UNIQUE, "
                    "csrf_token_hash VARCHAR(64) NOT NULL, "
                    "created_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, "
                    "revoked_at DATETIME)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE alembic_version ("
                    "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text("INSERT INTO alembic_version VALUES ('20261111_0011')")
            )

        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        command.upgrade(config, "20261111_0012")
        command.downgrade(config, "20261111_0011")

        inspector = inspect(engine)
        assert "active_bar_id" not in {
            column["name"] for column in inspector.get_columns("auth_sessions")
        }
        assert {
            column["name"] for column in inspector.get_columns("auth_sessions")
        } == {
            "id",
            "user_id",
            "token_hash",
            "csrf_token_hash",
            "created_at",
            "expires_at",
            "revoked_at",
        }
    finally:
        engine.dispose()
