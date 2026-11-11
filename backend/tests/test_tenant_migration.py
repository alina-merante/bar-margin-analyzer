from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_tenant_migration_creates_only_new_tables(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "tenant-migration.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('20261104_0008')")
        )
        connection.execute(
            text("CREATE TABLE preexisting_marker (id INTEGER PRIMARY KEY)")
        )
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO preexisting_marker VALUES (1)"))
        connection.execute(text("INSERT INTO products VALUES (7)"))

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")

    try:
        command.upgrade(config, "20261110_0009")

        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert {
            "bars",
            "users",
            "user_bar_memberships",
            "preexisting_marker",
            "products",
            "alembic_version",
        } == table_names
        assert inspector.get_indexes("user_bar_memberships") == [
            {
                "name": "ix_user_bar_memberships_bar_id",
                "column_names": ["bar_id"],
                "unique": 0,
                "dialect_options": {},
            }
        ]
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("users")
        } == {"uq_users_email"}
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("user_bar_memberships")
        } == {"uq_user_bar_memberships_user_bar"}
        assert {
            constraint["name"]
            for constraint in inspector.get_foreign_keys("user_bar_memberships")
        } == {
            "fk_user_bar_memberships_bar_id_bars",
            "fk_user_bar_memberships_user_id_users",
        }
        assert {
            constraint["name"]
            for constraint in inspector.get_check_constraints("users")
        } == {
            "ck_users_email_normalized",
            "ck_users_email_nonempty",
            "ck_users_password_hash_nonempty",
        }
        assert {
            constraint["name"]
            for constraint in inspector.get_check_constraints("user_bar_memberships")
        } == {"ck_user_bar_memberships_role"}
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT id FROM preexisting_marker")
            ).scalar_one() == 1
            assert connection.execute(text("SELECT id FROM products")).scalar_one() == 7
            assert connection.execute(text("SELECT COUNT(*) FROM bars")).scalar_one() == 0
            assert connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 0
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "20261110_0009"
            )
    finally:
        engine.dispose()


def test_tenant_migration_downgrade_drops_only_new_tables(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "tenant-downgrade.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('20261104_0008')")
        )
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO products VALUES (7)"))

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")

    try:
        command.upgrade(config, "20261110_0009")
        command.downgrade(config, "20261104_0008")

        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "products",
        }
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id FROM products")).scalar_one() == 7
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "20261104_0008"
    finally:
        engine.dispose()
