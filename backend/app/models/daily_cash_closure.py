import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyCashClosure(Base):
    __tablename__ = "daily_cash_closures"
    __table_args__ = (
        Index(
            "uq_daily_cash_closures_bar_date_number",
            "bar_id",
            "date",
            "closure_number",
            unique=True,
            postgresql_where=text(
                "bar_id IS NOT NULL AND closure_number IS NOT NULL"
            ),
            sqlite_where=text("bar_id IS NOT NULL AND closure_number IS NOT NULL"),
        ),
        Index(
            "uq_daily_cash_closures_legacy_date_number",
            "date",
            "closure_number",
            unique=True,
            postgresql_where=text(
                "bar_id IS NULL AND closure_number IS NOT NULL"
            ),
            sqlite_where=text("bar_id IS NULL AND closure_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bar_id: Mapped[int | None] = mapped_column(ForeignKey("bars.id"), nullable=True)

    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    closure_number: Mapped[str | None] = mapped_column(String(80), nullable=True)

    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    card_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

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