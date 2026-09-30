"""add bank transaction reconciliation constraints

Revision ID: 20261014_0005
Revises: 20261013_0004
Create Date: 2026-10-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0005"
down_revision: Union[str, None] = "20261013_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("transaction_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_payments_transaction_id_transactions",
        "payments",
        "transactions",
        ["transaction_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_payments_transaction_id",
        "payments",
        ["transaction_id"],
    )
    op.create_unique_constraint(
        "uq_invoice_payment_links_payment_id",
        "invoice_payment_links",
        ["payment_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_invoice_payment_links_payment_id",
        "invoice_payment_links",
        type_="unique",
    )
    op.drop_constraint("uq_payments_transaction_id", "payments", type_="unique")
    op.drop_constraint(
        "fk_payments_transaction_id_transactions",
        "payments",
        type_="foreignkey",
    )
    op.drop_column("payments", "transaction_id")
