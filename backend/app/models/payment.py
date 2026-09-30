import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaymentMethod(str, enum.Enum):
    bank_transfer = "bank_transfer"
    check = "check"
    cash = "cash"
    card = "card"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("transaction_id", name="uq_payments_transaction_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name="payment_method"), nullable=False, index=True)
    counterparty: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(255), nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=True
    )

    invoice_links = relationship("InvoicePaymentLink", back_populates="payment", cascade="all, delete-orphan")
    transaction = relationship("Transaction", back_populates="payment")
