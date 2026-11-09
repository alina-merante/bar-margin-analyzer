from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def create_pre_revision_database(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "cash-closure-migration.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('20261016_0007')")
        )
        connection.execute(text("CREATE TABLE documents (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE daily_cash_closures ("
                "id INTEGER PRIMARY KEY, date DATE NOT NULL, "
                "closure_number VARCHAR(80), total_amount NUMERIC(12,2) NOT NULL, "
                "cash_amount NUMERIC(12,2) NOT NULL, card_amount NUMERIC(12,2) NOT NULL, "
                "receipts_count INTEGER, document_id INTEGER REFERENCES documents(id), "
                "created_at DATETIME NOT NULL, "
                "CONSTRAINT uq_daily_cash_closures_date_closure_number "
                "UNIQUE (date, closure_number))"
            )
        )
        connection.execute(text("INSERT INTO documents (id) VALUES (1)"))
        connection.execute(
            text(
                "INSERT INTO daily_cash_closures "
                "VALUES (1, '2026-10-01', 'old', 10, 4, 6, NULL, 1, CURRENT_TIMESTAMP)"
            )
        )

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    return config, engine


def upgrade(config):
    command.upgrade(config, "head")


def test_upgrade_preserves_existing_closure_values(tmp_path, monkeypatch):
    config, engine = create_pre_revision_database(tmp_path, monkeypatch)
    try:
        upgrade(config)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT total_amount, cash_amount, card_amount "
                    "FROM daily_cash_closures WHERE id = 1"
                )
            ).one()
            assert tuple(map(float, row)) == (10.0, 4.0, 6.0)
        columns = inspect(engine).get_columns("daily_cash_closures")
        nullable = {column["name"]: column["nullable"] for column in columns}
        assert nullable["cash_amount"] is True
        assert nullable["card_amount"] is True
        assert "cash_closure_intakes" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_downgrade_refuses_to_delete_intake_rows(tmp_path, monkeypatch):
    config, engine = create_pre_revision_database(tmp_path, monkeypatch)
    try:
        upgrade(config)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO cash_closure_intakes "
                    "(document_id, source_sha256, classification, status, ocr_values, "
                    "anomalies, created_at, updated_at) "
                    "VALUES (1, :hash, 'SAVE_FOR_REVIEW', 'pending', '{}', '[]', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"hash": "a" * 64},
            )
        with pytest.raises(RuntimeError, match="intakes contain data"):
            command.downgrade(config, "20261016_0007")
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT COUNT(*) FROM cash_closure_intakes")
            ).scalar_one() == 1
    finally:
        engine.dispose()


def test_downgrade_refuses_to_coerce_null_payment_amounts(tmp_path, monkeypatch):
    config, engine = create_pre_revision_database(tmp_path, monkeypatch)
    try:
        upgrade(config)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE daily_cash_closures SET cash_amount = NULL WHERE id = 1")
            )
        with pytest.raises(RuntimeError, match="NULL payment amounts"):
            command.downgrade(config, "20261016_0007")
        assert "cash_closure_intakes" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_clean_downgrade_restores_non_nullable_payment_amounts(tmp_path, monkeypatch):
    config, engine = create_pre_revision_database(tmp_path, monkeypatch)
    try:
        upgrade(config)
        command.downgrade(config, "20261016_0007")
        nullable = {
            column["name"]: column["nullable"]
            for column in inspect(engine).get_columns("daily_cash_closures")
        }
        assert nullable["cash_amount"] is False
        assert nullable["card_amount"] is False
        assert "cash_closure_intakes" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
