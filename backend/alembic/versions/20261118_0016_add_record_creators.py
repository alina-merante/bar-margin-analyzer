"""Track creators of invoices and documents.

Revision ID: 20261118_0016
Revises: 20261112_0015
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261118_0016"
down_revision: Union[str, None] = "20261112_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("invoices", "documents"):
        op.add_column(
            table,
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            f"fk_{table}_created_by_user_id_users",
            table,
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            f"ix_{table}_created_by_user_id",
            table,
            ["created_by_user_id"],
        )


def downgrade() -> None:
    for table in ("documents", "invoices"):
        op.drop_index(
            f"ix_{table}_created_by_user_id",
            table_name=table,
        )
        op.drop_constraint(
            f"fk_{table}_created_by_user_id_users",
            table,
            type_="foreignkey",
        )
        op.drop_column(table, "created_by_user_id")
