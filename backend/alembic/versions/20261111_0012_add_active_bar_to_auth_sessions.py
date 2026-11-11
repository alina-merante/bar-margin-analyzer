"""store the selected bar on each authentication session

Revision ID: 20261111_0012
Revises: 20261111_0011
Create Date: 2026-11-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261111_0012"
down_revision: Union[str, None] = "20261111_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.add_column(sa.Column("active_bar_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_auth_sessions_active_bar_id_bars",
            "bars",
            ["active_bar_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.drop_constraint(
            "fk_auth_sessions_active_bar_id_bars",
            type_="foreignkey",
        )
        batch_op.drop_column("active_bar_id")
