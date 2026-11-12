"""add global administrator and membership permission foundations

Revision ID: 20261112_0014
Revises: 20261111_0013
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261112_0014"
down_revision: Union[str, None] = "20261111_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Migration history must remain independent of future catalog changes.
PERMISSIONS = (
    "invoices.view_own", "invoices.view_all", "invoices.upload", "invoices.create",
    "invoices.edit", "invoices.review", "invoices.approve", "invoices.delete",
    "cash_closures.view_own", "cash_closures.view_all", "cash_closures.upload",
    "cash_closures.edit", "cash_closures.review", "cash_closures.delete",
    "documents.view_own", "documents.view_all", "documents.upload", "documents.edit",
    "documents.review", "documents.delete",
    "revenue.view", "costs.view", "payments.view", "payments.create", "payments.edit",
    "payments.delete", "profit.view", "margins.view", "analytics.view",
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_global_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "membership_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("permission", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["user_bar_memberships.id"], ondelete="CASCADE",
            name="fk_membership_permissions_membership_id",
        ),
        sa.UniqueConstraint("membership_id", "permission", name="uq_membership_permissions_code"),
        sa.CheckConstraint(
            "permission IN (" + ", ".join(f"'{value}'" for value in PERMISSIONS) + ")",
            name="ck_membership_permissions_code",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM membership_permissions LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while membership permissions exist.")
    if bind.execute(sa.text("SELECT 1 FROM users WHERE is_global_admin = :value LIMIT 1"),
                    {"value": True}).first():
        raise RuntimeError("Cannot downgrade while global administrators exist.")
    op.drop_table("membership_permissions")
    op.drop_column("users", "is_global_admin")
