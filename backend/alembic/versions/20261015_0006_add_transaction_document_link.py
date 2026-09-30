"""link bank transactions to their source document

Revision ID: 20261015_0006
Revises: 20261014_0005
Create Date: 2026-10-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261015_0006"
down_revision: Union[str, None] = "20261014_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("document_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_transactions_document_id_documents",
        "transactions",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_transactions_document_id"),
        "transactions",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_document_id"), table_name="transactions")
    op.drop_constraint(
        "fk_transactions_document_id_documents",
        "transactions",
        type_="foreignkey",
    )
    op.drop_column("transactions", "document_id")