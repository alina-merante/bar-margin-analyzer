from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    bar_id: Mapped[int | None] = mapped_column(ForeignKey("bars.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    rules = relationship("CategoryRule", back_populates="category", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="category")
