from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    bar_id: Mapped[int | None] = mapped_column(ForeignKey("bars.id"), nullable=True)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("expense_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )

    category = relationship("ExpenseCategory", back_populates="rules")
