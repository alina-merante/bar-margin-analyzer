import datetime as dt

from sqlalchemy import Boolean, DateTime, Integer, PrimaryKeyConstraint, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Bar(Base):
    __tablename__ = "bars"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_bars"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )

    memberships = relationship(
        "UserBarMembership",
        back_populates="bar",
        cascade="all, delete-orphan",
    )
