from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    bar_id: Mapped[int | None] = mapped_column(ForeignKey("bars.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    sale_lines = relationship("SaleLine", back_populates="product")
