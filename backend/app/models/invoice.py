import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import Date, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InvoiceStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    supplier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status"),
        nullable=False,
        default=InvoiceStatus.pending,
        index=True,
    )

    payment_links = relationship("InvoicePaymentLink", back_populates="invoice", cascade="all, delete-orphan")
