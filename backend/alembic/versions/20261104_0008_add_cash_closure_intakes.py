"""add cash closure intake and nullable payment breakdown

Revision ID: 20261104_0008
Revises: 20261016_0007
Create Date: 2026-11-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261104_0008"
down_revision: Union[str, None] = "20261016_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("daily_cash_closures") as batch_op:
        batch_op.alter_column(
            "cash_amount",
            existing_type=sa.Numeric(12, 2),
            nullable=True,
        )
        batch_op.alter_column(
            "card_amount",
            existing_type=sa.Numeric(12, 2),
            nullable=True,
        )

    op.create_table(
        "cash_closure_intakes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("closure_id", sa.Integer(), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("classification", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("closure_number", sa.String(length=80), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("cash_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("card_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("ocr_values", sa.JSON(), nullable=False),
        sa.Column("anomalies", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_cash_closure_intakes_status",
        ),
        sa.CheckConstraint(
            "classification IN ('AUTO_SAVE', 'SAVE_FOR_REVIEW')",
            name="ck_cash_closure_intakes_classification",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_cash_closure_intakes_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["closure_id"],
            ["daily_cash_closures.id"],
            name="fk_cash_closure_intakes_closure_id_daily_cash_closures",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_cash_closure_intakes_document_id"),
        sa.UniqueConstraint("source_sha256", name="uq_cash_closure_intakes_source_sha256"),
        sa.UniqueConstraint("closure_id", name="uq_cash_closure_intakes_closure_id"),
    )
    op.create_index(
        "ix_cash_closure_intakes_status",
        "cash_closure_intakes",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_cash_closure_intakes_date",
        "cash_closure_intakes",
        ["date"],
        unique=False,
    )
    op.create_index(
        "uq_cash_closure_intakes_date_number_active",
        "cash_closure_intakes",
        ["date", "closure_number"],
        unique=True,
        sqlite_where=sa.text("status != 'rejected'"),
        postgresql_where=sa.text("status != 'rejected'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    intake_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM cash_closure_intakes")
    ).scalar_one()
    if intake_count:
        raise RuntimeError(
            "Cannot downgrade: cash closure intakes contain data that would be lost."
        )

    null_payment_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM daily_cash_closures "
            "WHERE cash_amount IS NULL OR card_amount IS NULL"
        )
    ).scalar_one()
    if null_payment_count:
        raise RuntimeError(
            "Cannot downgrade: NULL payment amounts cannot be converted without data loss."
        )

    op.drop_index("uq_cash_closure_intakes_date_number_active", table_name="cash_closure_intakes")
    op.drop_index("ix_cash_closure_intakes_date", table_name="cash_closure_intakes")
    op.drop_index("ix_cash_closure_intakes_status", table_name="cash_closure_intakes")
    op.drop_table("cash_closure_intakes")

    with op.batch_alter_table("daily_cash_closures") as batch_op:
        batch_op.alter_column(
            "cash_amount",
            existing_type=sa.Numeric(12, 2),
            nullable=False,
        )
        batch_op.alter_column(
            "card_amount",
            existing_type=sa.Numeric(12, 2),
            nullable=False,
        )
