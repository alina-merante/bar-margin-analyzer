"""add server-side authentication sessions and login rate limits

Revision ID: 20261111_0011
Revises: 20261111_0010
Create Date: 2026-11-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261111_0011"
down_revision: Union[str, None] = "20261111_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    op.create_table(
        "auth_login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email_key", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_auth_login_attempts"),
    )
    op.create_index(
        "ix_auth_login_attempts_email_time",
        "auth_login_attempts",
        ["email_key", "attempted_at"],
    )
    op.create_index(
        "ix_auth_login_attempts_source_time",
        "auth_login_attempts",
        ["source_key", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_login_attempts_source_time", table_name="auth_login_attempts")
    op.drop_index("ix_auth_login_attempts_email_time", table_name="auth_login_attempts")
    op.drop_table("auth_login_attempts")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
