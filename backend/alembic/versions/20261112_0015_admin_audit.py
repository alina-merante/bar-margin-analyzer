"""add administrative audit and write serialization

Revision ID: 20261112_0015
Revises: 20261112_0014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261112_0015"
down_revision: Union[str, None] = "20261112_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    lock = op.create_table(
        "admin_write_lock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.CheckConstraint("id = 1", name="ck_admin_write_lock_singleton"),
    )
    op.bulk_insert(lock, [{"id": 1}])
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("bar_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM admin_audit LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while administrative audit records exist.")
    op.drop_table("admin_audit")
    op.drop_table("admin_write_lock")
