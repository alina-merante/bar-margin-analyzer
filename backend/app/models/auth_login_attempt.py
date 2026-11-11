import datetime as dt

from sqlalchemy import DateTime, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuthLoginAttempt(Base):
    __tablename__ = "auth_login_attempts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_auth_login_attempts"),
        Index(
            "ix_auth_login_attempts_email_time",
            "email_key",
            "attempted_at",
        ),
        Index(
            "ix_auth_login_attempts_source_time",
            "source_key",
            "attempted_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attempted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
