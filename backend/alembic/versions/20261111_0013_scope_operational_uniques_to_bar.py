"""scope operational uniqueness rules to each bar

Revision ID: 20261111_0013
Revises: 20261111_0012
Create Date: 2026-11-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261111_0013"
down_revision: Union[str, None] = "20261111_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_no_upgrade_conflicts(bind) -> None:
    checks = (
        (
            "products",
            "bar_id, name",
            "name IS NOT NULL",
            "products contain duplicate names within a bar or the legacy scope",
        ),
        (
            "expense_categories",
            "bar_id, name",
            "name IS NOT NULL",
            "expense categories contain duplicate names within a bar or the legacy scope",
        ),
        (
            "daily_cash_closures",
            "bar_id, date, closure_number",
            "closure_number IS NOT NULL",
            "cash closures contain duplicate date/number pairs within a bar or the legacy scope",
        ),
        (
            "cash_closure_intakes",
            "bar_id, source_sha256",
            "source_sha256 IS NOT NULL",
            "cash closure intakes contain duplicate source hashes within a bar or the legacy scope",
        ),
        (
            "cash_closure_intakes",
            "bar_id, date, closure_number",
            "date IS NOT NULL AND closure_number IS NOT NULL "
            "AND status != 'rejected'",
            "active cash closure intakes contain duplicate date/number pairs within a bar or the legacy scope",
        ),
    )
    for table, columns, predicate, message in checks:
        duplicate = bind.execute(
            sa.text(
                f"SELECT {columns}, COUNT(*) FROM {table} "
                f"WHERE {predicate} GROUP BY {columns} HAVING COUNT(*) > 1 "
                "LIMIT 1"
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError(
                f"Cannot apply migration 0013: {message}; "
                f"conflicting key: {tuple(duplicate[:-1])!r}."
            )


def _assert_no_downgrade_conflicts(bind) -> None:
    checks = (
        (
            "products",
            "name",
            "name IS NOT NULL",
            "product names are duplicated across bars",
        ),
        (
            "expense_categories",
            "name",
            "name IS NOT NULL",
            "expense category names are duplicated across bars",
        ),
        (
            "daily_cash_closures",
            "date, closure_number",
            "closure_number IS NOT NULL",
            "cash closure date/number pairs are duplicated across bars",
        ),
        (
            "cash_closure_intakes",
            "source_sha256",
            "source_sha256 IS NOT NULL",
            "cash closure source hashes are duplicated across bars",
        ),
        (
            "cash_closure_intakes",
            "date, closure_number",
            "date IS NOT NULL AND closure_number IS NOT NULL "
            "AND status != 'rejected'",
            "active cash closure intake date/number pairs are duplicated across bars",
        ),
    )
    for table, columns, predicate, message in checks:
        duplicate = bind.execute(
            sa.text(
                f"SELECT {columns}, COUNT(*) FROM {table} "
                f"WHERE {predicate} GROUP BY {columns} HAVING COUNT(*) > 1 "
                "LIMIT 1"
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError(
                f"Cannot downgrade migration 0013: {message}; "
                f"conflicting key: {tuple(duplicate[:-1])!r}."
            )


def upgrade() -> None:
    bind = op.get_bind()
    _assert_no_upgrade_conflicts(bind)

    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_expense_categories_name", table_name="expense_categories")

    with op.batch_alter_table("daily_cash_closures") as batch_op:
        batch_op.drop_constraint(
            "uq_daily_cash_closures_date_closure_number",
            type_="unique",
        )

    op.drop_index(
        "uq_cash_closure_intakes_date_number_active",
        table_name="cash_closure_intakes",
    )
    with op.batch_alter_table("cash_closure_intakes") as batch_op:
        batch_op.drop_constraint(
            "uq_cash_closure_intakes_source_sha256",
            type_="unique",
        )

    op.create_index(
        "uq_products_bar_name",
        "products",
        ["bar_id", "name"],
        unique=True,
        postgresql_where=sa.text("bar_id IS NOT NULL"),
        sqlite_where=sa.text("bar_id IS NOT NULL"),
    )
    op.create_index(
        "uq_products_legacy_name",
        "products",
        ["name"],
        unique=True,
        postgresql_where=sa.text("bar_id IS NULL"),
        sqlite_where=sa.text("bar_id IS NULL"),
    )
    op.create_index("ix_products_name", "products", ["name"], unique=False)
    op.create_index(
        "uq_expense_categories_bar_name",
        "expense_categories",
        ["bar_id", "name"],
        unique=True,
        postgresql_where=sa.text("bar_id IS NOT NULL"),
        sqlite_where=sa.text("bar_id IS NOT NULL"),
    )
    op.create_index(
        "uq_expense_categories_legacy_name",
        "expense_categories",
        ["name"],
        unique=True,
        postgresql_where=sa.text("bar_id IS NULL"),
        sqlite_where=sa.text("bar_id IS NULL"),
    )
    op.create_index(
        "ix_expense_categories_name",
        "expense_categories",
        ["name"],
        unique=False,
    )
    op.create_index(
        "uq_daily_cash_closures_bar_date_number",
        "daily_cash_closures",
        ["bar_id", "date", "closure_number"],
        unique=True,
        postgresql_where=sa.text(
            "bar_id IS NOT NULL AND closure_number IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "bar_id IS NOT NULL AND closure_number IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_daily_cash_closures_legacy_date_number",
        "daily_cash_closures",
        ["date", "closure_number"],
        unique=True,
        postgresql_where=sa.text(
            "bar_id IS NULL AND closure_number IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "bar_id IS NULL AND closure_number IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_cash_closure_intakes_bar_source_sha256",
        "cash_closure_intakes",
        ["bar_id", "source_sha256"],
        unique=True,
        postgresql_where=sa.text("bar_id IS NOT NULL"),
        sqlite_where=sa.text("bar_id IS NOT NULL"),
    )
    op.create_index(
        "uq_cash_closure_intakes_legacy_source_sha256",
        "cash_closure_intakes",
        ["source_sha256"],
        unique=True,
        postgresql_where=sa.text("bar_id IS NULL"),
        sqlite_where=sa.text("bar_id IS NULL"),
    )
    op.create_index(
        "uq_cash_closure_intakes_bar_date_number_active",
        "cash_closure_intakes",
        ["bar_id", "date", "closure_number"],
        unique=True,
        postgresql_where=sa.text(
            "bar_id IS NOT NULL AND status != 'rejected'"
        ),
        sqlite_where=sa.text(
            "bar_id IS NOT NULL AND status != 'rejected'"
        ),
    )
    op.create_index(
        "uq_cash_closure_intakes_legacy_date_number_active",
        "cash_closure_intakes",
        ["date", "closure_number"],
        unique=True,
        postgresql_where=sa.text(
            "bar_id IS NULL AND status != 'rejected'"
        ),
        sqlite_where=sa.text(
            "bar_id IS NULL AND status != 'rejected'"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    _assert_no_downgrade_conflicts(bind)

    for index_name, table in (
        ("uq_cash_closure_intakes_legacy_date_number_active", "cash_closure_intakes"),
        ("uq_cash_closure_intakes_bar_date_number_active", "cash_closure_intakes"),
        ("uq_cash_closure_intakes_legacy_source_sha256", "cash_closure_intakes"),
        ("uq_cash_closure_intakes_bar_source_sha256", "cash_closure_intakes"),
        ("uq_daily_cash_closures_legacy_date_number", "daily_cash_closures"),
        ("uq_daily_cash_closures_bar_date_number", "daily_cash_closures"),
        ("uq_expense_categories_legacy_name", "expense_categories"),
        ("uq_expense_categories_bar_name", "expense_categories"),
        ("ix_expense_categories_name", "expense_categories"),
        ("uq_products_legacy_name", "products"),
        ("uq_products_bar_name", "products"),
        ("ix_products_name", "products"),
    ):
        op.drop_index(index_name, table_name=table)

    with op.batch_alter_table("daily_cash_closures") as batch_op:
        batch_op.create_unique_constraint(
            "uq_daily_cash_closures_date_closure_number",
            ["date", "closure_number"],
        )
    with op.batch_alter_table("cash_closure_intakes") as batch_op:
        batch_op.create_unique_constraint(
            "uq_cash_closure_intakes_source_sha256",
            ["source_sha256"],
        )
        batch_op.create_index(
            "uq_cash_closure_intakes_date_number_active",
            ["date", "closure_number"],
            unique=True,
            postgresql_where=sa.text("status != 'rejected'"),
            sqlite_where=sa.text("status != 'rejected'"),
        )

    op.create_index("ix_products_name", "products", ["name"], unique=True)
    op.create_index(
        "ix_expense_categories_name",
        "expense_categories",
        ["name"],
        unique=True,
    )
