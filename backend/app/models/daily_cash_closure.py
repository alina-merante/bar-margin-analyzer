import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyCashClosure(Base):
    __tablename__ = "daily_cash_closures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    closure_number: Mapped[str | None] = mapped_column(String(80), nullable=True)

    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cash_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    card_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    receipts_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False,
    )