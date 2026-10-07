"""add unique constraint on daily cash closures (date, closure_number)

Revision ID: 20261016_0007
Revises: 20261015_0006
Create Date: 2026-10-16 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20261016_0007"
down_revision: Union[str, None] = "20261015_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_daily_cash_closures_date_closure_number",
        "daily_cash_closures",
        ["date", "closure_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_daily_cash_closures_date_closure_number",
        "daily_cash_closures",
        type_="unique",
    )
