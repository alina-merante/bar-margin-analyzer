"""add nullable bar_id to operational tables

Revision ID: 20261111_0010
Revises: 20261110_0009
Create Date: 2026-11-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261111_0010"
down_revision: Union[str, None] = "20261110_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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
LEGACY_BAR_NAME = "Bar Legacy"


def _has_operational_data(bind) -> bool:
    return any(
        bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None
        for table in OPERATIONAL_TABLES
    )


def _ensure_legacy_bar(bind) -> None:
    existing_name = bind.execute(
        sa.text("SELECT name FROM bars WHERE id = :bar_id"),
        {"bar_id": LEGACY_BAR_ID},
    ).scalar_one_or_none()
    if existing_name is not None:
        if existing_name != LEGACY_BAR_NAME:
            raise RuntimeError(
                f"Cannot use reserved legacy bar id {LEGACY_BAR_ID}: "
                f"it belongs to {existing_name!r}, not {LEGACY_BAR_NAME!r}."
            )
        return

    bind.execute(
        sa.text("INSERT INTO bars (id, name) VALUES (:bar_id, :name)"),
        {"bar_id": LEGACY_BAR_ID, "name": LEGACY_BAR_NAME},
    )


def upgrade() -> None:
    bind = op.get_bind()
    has_operational_data = _has_operational_data(bind)

    if has_operational_data:
        existing_name = bind.execute(
            sa.text("SELECT name FROM bars WHERE id = :bar_id"),
            {"bar_id": LEGACY_BAR_ID},
        ).scalar_one_or_none()
        if existing_name is not None and existing_name != LEGACY_BAR_NAME:
            raise RuntimeError(
                f"Cannot use reserved legacy bar id {LEGACY_BAR_ID}: "
                f"it belongs to {existing_name!r}, not {LEGACY_BAR_NAME!r}."
            )

    for table in OPERATIONAL_TABLES:
        constraint_name = f"fk_{table}_bar_id_bars"
        if bind.dialect.name == "sqlite":
            op.execute(
                f"ALTER TABLE {table} ADD COLUMN bar_id INTEGER "
                f"CONSTRAINT {constraint_name} REFERENCES bars (id)"
            )
        else:
            op.add_column(table, sa.Column("bar_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                constraint_name,
                table,
                "bars",
                ["bar_id"],
                ["id"],
            )

    if not has_operational_data:
        return

    _ensure_legacy_bar(bind)
    for table in OPERATIONAL_TABLES:
        conflicting_count = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE bar_id IS NOT NULL AND bar_id != :legacy_bar_id"
            ),
            {"legacy_bar_id": LEGACY_BAR_ID},
        ).scalar_one()
        if conflicting_count:
            raise RuntimeError(
                f"Cannot backfill {table}: {conflicting_count} rows are already "
                f"assigned to bars other than the legacy bar id {LEGACY_BAR_ID}."
            )
        bind.execute(
            sa.text(
                f"UPDATE {table} SET bar_id = :legacy_bar_id WHERE bar_id IS NULL"
            ),
            {"legacy_bar_id": LEGACY_BAR_ID},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in OPERATIONAL_TABLES:
        conflicting_bar_ids = bind.execute(
            sa.text(
                f"SELECT DISTINCT bar_id FROM {table} "
                "WHERE bar_id IS NOT NULL AND bar_id != :legacy_bar_id"
            ),
            {"legacy_bar_id": LEGACY_BAR_ID},
        ).scalars().all()
        if conflicting_bar_ids:
            raise RuntimeError(
                f"Cannot downgrade: {table} contains rows assigned to "
                f"non-legacy bar ids {sorted(conflicting_bar_ids)}."
            )

    for table in reversed(OPERATIONAL_TABLES):
        constraint_name = f"fk_{table}_bar_id_bars"
        if bind.dialect.name == "sqlite":
            op.execute(f"ALTER TABLE {table} DROP COLUMN bar_id")
        else:
            op.drop_constraint(constraint_name, table, type_="foreignkey")
            op.drop_column(table, "bar_id")
