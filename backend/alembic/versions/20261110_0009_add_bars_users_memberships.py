"""add bars, users and user-bar memberships

Revision ID: 20261110_0009
Revises: 20261104_0008
Create Date: 2026-11-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261110_0009"
down_revision: Union[str, None] = "20261104_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bars"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email = lower(trim(email))",
            name="ck_users_email_normalized",
        ),
        sa.CheckConstraint(
            "length(trim(email)) > 0",
            name="ck_users_email_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(password_hash)) > 0",
            name="ck_users_password_hash_nonempty",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "user_bar_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bar_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'manager', 'staff')",
            name="ck_user_bar_memberships_role",
        ),
        sa.ForeignKeyConstraint(
            ["bar_id"],
            ["bars.id"],
            name="fk_user_bar_memberships_bar_id_bars",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_bar_memberships_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_bar_memberships"),
        sa.UniqueConstraint(
            "user_id",
            "bar_id",
            name="uq_user_bar_memberships_user_bar",
        ),
    )
    op.create_index(
        "ix_user_bar_memberships_bar_id",
        "user_bar_memberships",
        ["bar_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_bar_memberships_bar_id",
        table_name="user_bar_memberships",
    )
    op.drop_table("user_bar_memberships")
    op.drop_table("users")
    op.drop_table("bars")
