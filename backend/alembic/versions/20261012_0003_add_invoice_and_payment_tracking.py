"""add invoices, payments and invoice payment links

Revision ID: 20261012_0003
Revises: 20261011_0002
Create Date: 2026-10-12 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20261012_0003"
down_revision: Union[str, None] = "20261011_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

invoice_status = sa.Enum("pending", "paid", name="invoice_status", native_enum=False)
payment_method = sa.Enum("bank_transfer", "check", "cash", "card", name="payment_method", native_enum=False)

def upgrade() -> None:

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier", sa.String(length=255), nullable=False),
        sa.Column("invoice_number", sa.String(length=255), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("vat", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", invoice_status, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invoices_id"), "invoices", ["id"], unique=False)
    op.create_index(op.f("ix_invoices_supplier"), "invoices", ["supplier"], unique=False)
    op.create_index(op.f("ix_invoices_invoice_number"), "invoices", ["invoice_number"], unique=False)
    op.create_index(op.f("ix_invoices_issue_date"), "invoices", ["issue_date"], unique=False)
    op.create_index(op.f("ix_invoices_due_date"), "invoices", ["due_date"], unique=False)
    op.create_index(op.f("ix_invoices_status"), "invoices", ["status"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("counterparty", sa.String(length=255), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_id"), "payments", ["id"], unique=False)
    op.create_index(op.f("ix_payments_date"), "payments", ["date"], unique=False)
    op.create_index(op.f("ix_payments_method"), "payments", ["method"], unique=False)
    op.create_index(op.f("ix_payments_counterparty"), "payments", ["counterparty"], unique=False)

    op.create_table(
        "invoice_payment_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id", "payment_id", name="uq_invoice_payment_link"),
    )
    op.create_index(op.f("ix_invoice_payment_links_id"), "invoice_payment_links", ["id"], unique=False)
    op.create_index(op.f("ix_invoice_payment_links_invoice_id"), "invoice_payment_links", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_invoice_payment_links_payment_id"), "invoice_payment_links", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoice_payment_links_payment_id"), table_name="invoice_payment_links")
    op.drop_index(op.f("ix_invoice_payment_links_invoice_id"), table_name="invoice_payment_links")
    op.drop_index(op.f("ix_invoice_payment_links_id"), table_name="invoice_payment_links")
    op.drop_table("invoice_payment_links")

    op.drop_index(op.f("ix_payments_counterparty"), table_name="payments")
    op.drop_index(op.f("ix_payments_method"), table_name="payments")
    op.drop_index(op.f("ix_payments_date"), table_name="payments")
    op.drop_index(op.f("ix_payments_id"), table_name="payments")
    op.drop_table("payments")

    op.drop_index(op.f("ix_invoices_status"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_due_date"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_issue_date"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_invoice_number"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_supplier"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_id"), table_name="invoices")
    op.drop_table("invoices")

