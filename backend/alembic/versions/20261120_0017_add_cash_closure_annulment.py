"""Add cash closure annulment metadata.

Revision ID: 20261120_0017
Revises: 20261118_0016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261120_0017"
down_revision: Union[str, None] = "20261118_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_cash_closures",
        sa.Column("annulled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "daily_cash_closures",
        sa.Column("annulled_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "daily_cash_closures",
        sa.Column("annulment_reason", sa.String(1000), nullable=True),
    )
    with op.batch_alter_table("daily_cash_closures") as batch_op:
        batch_op.create_foreign_key(
            "fk_daily_cash_closures_annulled_by_user_id_users",
            "users",
            ["annulled_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("cash_closure_intakes") as batch_op:
        batch_op.drop_constraint(
            "ck_cash_closure_intakes_status", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_cash_closure_intakes_status",
            "status IN ('pending', 'approved', 'rejected', 'annulled')",
        )


def downgrade() -> None:
    connection = op.get_bind()
    has_annulled = connection.execute(
        sa.text(
            "SELECT 1 FROM cash_closure_intakes "
            "WHERE status = 'annulled' LIMIT 1"
        )
    ).first()
    has_audit = connection.execute(
        sa.text(
            "SELECT 1 FROM daily_cash_closures "
            "WHERE annulled_at IS NOT NULL LIMIT 1"
        )
    ).first()

    if has_annulled or has_audit:
        raise RuntimeError(
            "Cannot downgrade while annulled cash closures exist."
        )

    with op.batch_alter_table("cash_closure_intakes") as batch_op:
        batch_op.drop_constraint(
            "ck_cash_closure_intakes_status", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_cash_closure_intakes_status",
            "status IN ('pending', 'approved', 'rejected')",
        )

    with op.batch_alter_table("daily_cash_closures") as batch_op:
        batch_op.drop_constraint(
            "fk_daily_cash_closures_annulled_by_user_id_users",
            type_="foreignkey",
        )
    op.drop_column("daily_cash_closures", "annulment_reason")
    op.drop_column("daily_cash_closures", "annulled_by_user_id")
    op.drop_column("daily_cash_closures", "annulled_at")
