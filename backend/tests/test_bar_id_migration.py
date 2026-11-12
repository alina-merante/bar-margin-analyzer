from pathlib import Path
import sys

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base
from app import models


OPERATIONAL_TABLES = (
    "products",
    "sale_lines",
    "expense_categories",
    "category_rules",
    "transactions",
    "documents",
    "daily_cash_closures",
    "invoices",
    "payments",
    "invoice_payment_links",
    "cash_closure_intakes",
)
LEGACY_BAR_ID = -1


@pytest.fixture
def migration_database(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "bar-id-migration.db"
    engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")

    try:
        metadata = MetaData()
        for source_table in Base.metadata.sorted_tables:
            source_table.to_metadata(metadata)
        for table_name in OPERATIONAL_TABLES:
            table = metadata.tables[table_name]
            bar_id = table.c.bar_id
            for index in list(table.indexes):
                references_bar_id = any(
                    column.name == "bar_id" for column in index.columns
                ) or any(
                    "bar_id" in str(index.dialect_options[dialect].get("where", ""))
                    for dialect in ("sqlite", "postgresql")
                )
                if references_bar_id:
                    table.indexes.remove(index)
            for constraint in list(table.foreign_key_constraints):
                if any(element.parent is bar_id for element in constraint.elements):
                    table.constraints.remove(constraint)
            table._columns.remove(bar_id)
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text("INSERT INTO alembic_version VALUES ('20261110_0009')")
            )
        yield config, engine
    finally:
        engine.dispose()


def insert_historical_rows(engine):
    statements = (
        "INSERT INTO products (id, name) VALUES (101, 'Coffee')",
        "INSERT INTO sale_lines (id, date, product_id, qty, total) "
        "VALUES (201, '2026-11-01', 101, 2.50, 5.25)",
        "INSERT INTO expense_categories (id, name) VALUES (301, 'Supplies')",
        "INSERT INTO category_rules (id, keyword, category_id) "
        "VALUES (401, 'beans', 301)",
        "INSERT INTO documents "
        "(id, month, original_filename, stored_filename, section, document_type, "
        "category, result, file_url, preview_url, status, created_at) "
        "VALUES (501, '2026-11', 'bank.csv', 'stored.csv', 'finance', 'bank', "
        "'bank_statement', 'parsed', '/files/bank.csv', '/previews/bank.png', "
        "'Elaborato', '2026-11-01 10:00:00')",
        "INSERT INTO documents "
        "(id, month, original_filename, stored_filename, section, document_type, "
        "category, result, file_url, preview_url, status, created_at) "
        "VALUES (502, '2026-11', 'closure.png', 'stored.png', 'cash', 'image', "
        "'cash_closure', 'parsed', '/files/closure.png', '/previews/closure.png', "
        "'Elaborato', '2026-11-02 10:00:00')",
        "INSERT INTO transactions "
        "(id, date, description, amount, counterparty, document_id, category_id) "
        "VALUES (601, '2026-11-01', 'Coffee supplies', 25.75, 'Supplier', 501, 301)",
        "INSERT INTO transactions "
        "(id, date, description, amount, counterparty, document_id, category_id) "
        "VALUES (602, '2026-11-02', 'Uncategorized', -4.25, 'Other', NULL, NULL)",
        "INSERT INTO invoices "
        "(id, supplier, invoice_number, issue_date, due_date, total, vat, status, file_url) "
        "VALUES (701, 'Supplier', 'INV-1', '2026-11-01', '2026-11-30', "
        "19.99, 1.99, 'pending', NULL)",
        "INSERT INTO payments "
        "(id, date, amount, method, counterparty, reference, transaction_id) "
        "VALUES (801, '2026-11-02', 25.75, 'bank_transfer', 'Supplier', 'REF-1', 601)",
        "INSERT INTO payments "
        "(id, date, amount, method, counterparty, reference, transaction_id) "
        "VALUES (802, '2026-11-03', 7.50, 'cash', 'Other', 'REF-2', NULL)",
        "INSERT INTO invoice_payment_links (id, invoice_id, payment_id) "
        "VALUES (901, 701, 801)",
        "INSERT INTO daily_cash_closures "
        "(id, date, closure_number, total_amount, cash_amount, card_amount, "
        "receipts_count, document_id, created_at) "
        "VALUES (1001, '2026-11-02', 'C-1', 20.50, NULL, 20.50, NULL, 502, "
        "'2026-11-02 11:00:00')",
        "INSERT INTO daily_cash_closures "
        "(id, date, closure_number, total_amount, cash_amount, card_amount, "
        "receipts_count, document_id, created_at) "
        "VALUES (1002, '2026-11-03', NULL, 0, 0, 0, NULL, NULL, "
        "'2026-11-03 11:00:00')",
        "INSERT INTO cash_closure_intakes "
        "(id, document_id, closure_id, source_sha256, classification, status, date, "
        "closure_number, total_amount, cash_amount, card_amount, ocr_values, anomalies, "
        "created_at, updated_at) "
        "VALUES (1101, 502, 1001, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
        "'AUTO_SAVE', 'approved', NULL, NULL, NULL, NULL, NULL, '{}', '[]', "
        "'2026-11-02 10:30:00', '2026-11-02 10:30:00')",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def table_rows(connection, table):
    return [
        dict(row._mapping)
        for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY id"))
    ]


def schema_snapshot(inspector, table):
    columns = [
        (
            column["name"],
            str(column["type"]),
            column["nullable"],
            column["default"],
            column.get("autoincrement"),
        )
        for column in inspector.get_columns(table)
    ]
    primary_key = inspector.get_pk_constraint(table)
    unique_constraints = sorted(
        (
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in inspector.get_unique_constraints(table)
        ),
        key=repr,
    )
    check_constraints = sorted(
        (
            (constraint["name"], constraint["sqltext"])
            for constraint in inspector.get_check_constraints(table)
        ),
        key=repr,
    )
    foreign_keys = sorted(
        (
            (
                constraint["name"],
                tuple(constraint["constrained_columns"]),
                constraint["referred_table"],
                tuple(constraint["referred_columns"]),
                tuple(sorted(constraint["options"].items())),
            )
            for constraint in inspector.get_foreign_keys(table)
        ),
        key=repr,
    )
    indexes = sorted(
        (
            (
                index["name"],
                tuple(index["column_names"]),
                index["unique"],
                tuple(
                    sorted(
                        (key, str(value))
                        for key, value in index["dialect_options"].items()
                    )
                ),
            )
            for index in inspector.get_indexes(table)
        ),
        key=repr,
    )
    return columns, primary_key, unique_constraints, check_constraints, foreign_keys, indexes


def test_upgrade_backfills_without_changing_existing_data_or_constraints(
    migration_database,
):
    config, engine = migration_database
    insert_historical_rows(engine)

    with engine.connect() as connection:
        original_rows = {
            table: table_rows(connection, table) for table in OPERATIONAL_TABLES
        }
    inspector = inspect(engine)
    original_schema = {
        table: schema_snapshot(inspector, table) for table in OPERATIONAL_TABLES
    }

    command.upgrade(config, "20261111_0010")

    inspector = inspect(engine)
    for table in OPERATIONAL_TABLES:
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert columns["bar_id"]["nullable"] is True
        after_schema = schema_snapshot(inspector, table)
        before_columns, before_pk, before_unique, before_checks, before_fks, before_indexes = (
            original_schema[table]
        )
        after_columns, after_pk, after_unique, after_checks, after_fks, after_indexes = (
            after_schema
        )
        assert [column for column in after_columns if column[0] != "bar_id"] == before_columns
        assert after_pk == before_pk
        assert after_unique == before_unique
        assert after_checks == before_checks
        assert [fk for fk in after_fks if fk[1] != ("bar_id",)] == before_fks
        assert after_indexes == before_indexes
        assert any(
            foreign_key[1:4] == (("bar_id",), "bars", ("id",))
            for foreign_key in after_fks
        )

    with engine.connect() as connection:
        for table in OPERATIONAL_TABLES:
            updated_rows = table_rows(connection, table)
            assert [
                {key: value for key, value in row.items() if key != "bar_id"}
                for row in updated_rows
            ] == original_rows[table]
            assert {row["bar_id"] for row in updated_rows} == {LEGACY_BAR_ID}
        assert connection.execute(
            text("SELECT name FROM bars WHERE id = :bar_id"),
            {"bar_id": LEGACY_BAR_ID},
        ).scalar_one() == "Bar Legacy"


def test_upgrade_on_empty_operational_database_does_not_create_legacy_bar(
    migration_database,
):
    config, engine = migration_database
    command.upgrade(config, "20261111_0010")

    inspector = inspect(engine)
    for table in OPERATIONAL_TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert "bar_id" in columns
        assert {
            tuple(foreign_key["constrained_columns"]): (
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspector.get_foreign_keys(table)
        }[("bar_id",)] == ("bars", ("id",))

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM bars")).scalar_one() == 0


def test_upgrade_rejects_an_existing_bar_using_the_reserved_legacy_id(
    migration_database,
):
    config, engine = migration_database
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO bars (id, name) VALUES (:id, 'Unrelated Bar')"),
            {"id": LEGACY_BAR_ID},
        )
    insert_historical_rows(engine)

    with pytest.raises(RuntimeError, match="reserved legacy bar id"):
        command.upgrade(config, "20261111_0010")

    inspector = inspect(engine)
    assert all(
        "bar_id" not in {column["name"] for column in inspector.get_columns(table)}
        for table in OPERATIONAL_TABLES
    )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT name FROM bars WHERE id = :id"), {"id": LEGACY_BAR_ID}
        ).scalar_one() == "Unrelated Bar"
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20261110_0009"


def test_foreign_keys_reject_unknown_bar_ids(migration_database):
    config, engine = migration_database
    command.upgrade(config, "20261111_0010")

    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO products (id, bar_id, name) "
                    "VALUES (999, 987654, 'Invalid tenant')"
                )
            )


def test_downgrade_preserves_rows_and_does_not_delete_legacy_bar(
    migration_database,
):
    config, engine = migration_database
    insert_historical_rows(engine)
    command.upgrade(config, "20261111_0010")

    with engine.connect() as connection:
        original_rows = {
            table: table_rows(connection, table) for table in OPERATIONAL_TABLES
        }

    command.downgrade(config, "20261110_0009")

    inspector = inspect(engine)
    for table in OPERATIONAL_TABLES:
        assert "bar_id" not in {
            column["name"] for column in inspector.get_columns(table)
        }
    with engine.connect() as connection:
        for table in OPERATIONAL_TABLES:
            assert table_rows(connection, table) == [
                {key: value for key, value in row.items() if key != "bar_id"}
                for row in original_rows[table]
            ]
        assert connection.execute(
            text("SELECT name FROM bars WHERE id = :bar_id"),
            {"bar_id": LEGACY_BAR_ID},
        ).scalar_one() == "Bar Legacy"


def test_downgrade_refuses_multi_bar_data_before_changing_schema(
    migration_database,
):
    config, engine = migration_database
    insert_historical_rows(engine)
    command.upgrade(config, "20261111_0010")

    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO bars (id, name) VALUES (22, 'Second Bar')")
        )
        connection.execute(
            text("UPDATE products SET bar_id = 22 WHERE id = 101")
        )

    with pytest.raises(RuntimeError, match="non-legacy bar ids"):
        command.downgrade(config, "20261110_0009")

    inspector = inspect(engine)
    assert all(
        "bar_id" in {column["name"] for column in inspector.get_columns(table)}
        for table in OPERATIONAL_TABLES
    )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT bar_id FROM products WHERE id = 101")
        ).scalar_one() == 22
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20261111_0010"


def test_models_declare_nullable_foreign_keys_to_bars():
    assert models.Bar.__tablename__ == "bars"
    for table in OPERATIONAL_TABLES:
        column = Base.metadata.tables[table].c.bar_id
        assert column.nullable is True
        assert {foreign_key.target_fullname for foreign_key in column.foreign_keys} == {
            "bars.id"
        }
