import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    category = relationship("ExpenseCategory", back_populates="transactions")
