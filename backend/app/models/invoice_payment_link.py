from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InvoicePaymentLink(Base):
    __tablename__ = "invoice_payment_links"
    __table_args__ = (UniqueConstraint("invoice_id", "payment_id", name="uq_invoice_payment_link"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)

    invoice = relationship("Invoice", back_populates="payment_links")
    payment = relationship("Payment", back_populates="invoice_links")
