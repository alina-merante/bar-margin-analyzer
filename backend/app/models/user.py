import datetime as dt

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_users"),
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "email = lower(trim(email))",
            name="ck_users_email_normalized",
        ),
        CheckConstraint(
            "length(trim(email)) > 0",
            name="ck_users_email_nonempty",
        ),
        CheckConstraint(
            "length(trim(password_hash)) > 0",
            name="ck_users_password_hash_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )
    is_global_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    memberships = relationship(
        "UserBarMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    auth_sessions = relationship(
        "AuthSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @validates("email")
    def normalize_email(self, _key: str, value: str) -> str:
        return value.strip().lower()
