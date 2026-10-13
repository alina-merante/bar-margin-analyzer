from decimal import Decimal

from app.models.invoice import InvoiceStatus


def get_invoice_payment_status(
    status: InvoiceStatus,
    total: Decimal,
    linked_amount: Decimal,
) -> InvoiceStatus:
    if status == InvoiceStatus.paid and linked_amount > 0 and linked_amount >= total:
        return InvoiceStatus.paid
    return InvoiceStatus.pending
