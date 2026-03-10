"""add transactions, expense categories and category rules

Revision ID: 20261011_0002
Revises: 20261010_0001
Create Date: 2026-10-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20261011_0002"
down_revision: Union[str, None] = "20261010_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_expense_categories_id"), "expense_categories", ["id"], unique=False)
    op.create_index(op.f("ix_expense_categories_name"), "expense_categories", ["name"], unique=True)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("counterparty", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["expense_categories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transactions_category_id"), "transactions", ["category_id"], unique=False)
    op.create_index(op.f("ix_transactions_counterparty"), "transactions", ["counterparty"], unique=False)
    op.create_index(op.f("ix_transactions_date"), "transactions", ["date"], unique=False)
    op.create_index(op.f("ix_transactions_id"), "transactions", ["id"], unique=False)

    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["expense_categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_category_rules_category_id"), "category_rules", ["category_id"], unique=False)
    op.create_index(op.f("ix_category_rules_id"), "category_rules", ["id"], unique=False)
    op.create_index(op.f("ix_category_rules_keyword"), "category_rules", ["keyword"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_category_rules_keyword"), table_name="category_rules")
    op.drop_index(op.f("ix_category_rules_id"), table_name="category_rules")
    op.drop_index(op.f("ix_category_rules_category_id"), table_name="category_rules")
    op.drop_table("category_rules")

    op.drop_index(op.f("ix_transactions_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_date"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_counterparty"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_category_id"), table_name="transactions")
    op.drop_table("transactions")

    op.drop_index(op.f("ix_expense_categories_name"), table_name="expense_categories")
    op.drop_index(op.f("ix_expense_categories_id"), table_name="expense_categories")
    op.drop_table("expense_categories")
