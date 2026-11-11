import datetime as dt

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    active_bar_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "bars.id",
            name="fk_auth_sessions_active_bar_id_bars",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user = relationship("User", back_populates="auth_sessions")
    active_bar = relationship("Bar", foreign_keys=[active_bar_id])
