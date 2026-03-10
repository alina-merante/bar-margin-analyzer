"""create products and sale_lines tables

Revision ID: 20261010_0001
Revises:
Create Date: 2026-10-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20261010_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"], unique=False)
    op.create_index(op.f("ix_products_name"), "products", ["name"], unique=True)

    op.create_table(
        "sale_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sale_lines_date"), "sale_lines", ["date"], unique=False)
    op.create_index(op.f("ix_sale_lines_id"), "sale_lines", ["id"], unique=False)
    op.create_index(op.f("ix_sale_lines_product_id"), "sale_lines", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sale_lines_product_id"), table_name="sale_lines")
    op.drop_index(op.f("ix_sale_lines_id"), table_name="sale_lines")
    op.drop_index(op.f("ix_sale_lines_date"), table_name="sale_lines")
    op.drop_table("sale_lines")

    op.drop_index(op.f("ix_products_name"), table_name="products")
    op.drop_index(op.f("ix_products_id"), table_name="products")
    op.drop_table("products")
