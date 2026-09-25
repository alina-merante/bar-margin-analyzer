"""add documents and daily cash closures

Revision ID: 20261013_0004
Revises: 20261012_0003
Create Date: 2026-10-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261013_0004"
down_revision: Union[str, None] = "20261012_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("file_url", sa.String(), nullable=True))

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("section", sa.String(length=50), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("preview_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)

    op.create_table(
        "daily_cash_closures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("closure_number", sa.String(length=80), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("cash_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("card_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("receipts_count", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_daily_cash_closures_id"), "daily_cash_closures", ["id"], unique=False)
    op.create_index(op.f("ix_daily_cash_closures_date"), "daily_cash_closures", ["date"], unique=False)
    op.create_index(
        op.f("ix_daily_cash_closures_document_id"),
        "daily_cash_closures",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_daily_cash_closures_document_id"), table_name="daily_cash_closures")
    op.drop_index(op.f("ix_daily_cash_closures_date"), table_name="daily_cash_closures")
    op.drop_index(op.f("ix_daily_cash_closures_id"), table_name="daily_cash_closures")
    op.drop_table("daily_cash_closures")

    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")

    op.drop_column("invoices", "file_url")
