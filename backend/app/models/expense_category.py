from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (
        Index(
            "uq_expense_categories_bar_name",
            "bar_id",
            "name",
            unique=True,
            postgresql_where=text("bar_id IS NOT NULL"),
            sqlite_where=text("bar_id IS NOT NULL"),
        ),
        Index(
            "uq_expense_categories_legacy_name",
            "name",
            unique=True,
            postgresql_where=text("bar_id IS NULL"),
            sqlite_where=text("bar_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    bar_id: Mapped[int | None] = mapped_column(ForeignKey("bars.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    rules = relationship("CategoryRule", back_populates="category", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="category")
