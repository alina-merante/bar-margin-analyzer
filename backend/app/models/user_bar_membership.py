import datetime as dt
import enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MembershipRole(str, enum.Enum):
    owner = "owner"
    manager = "manager"
    staff = "staff"


class UserBarMembership(Base):
    __tablename__ = "user_bar_memberships"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_user_bar_memberships"),
        UniqueConstraint("user_id", "bar_id", name="uq_user_bar_memberships_user_bar"),
        CheckConstraint(
            "role IN ('owner', 'manager', 'staff')",
            name="ck_user_bar_memberships_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_user_bar_memberships_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    bar_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bars.id", name="fk_user_bar_memberships_bar_id_bars", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(
            MembershipRole,
            name="membership_role",
            native_enum=False,
            create_constraint=False,
            length=16,
        ),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="memberships")
    bar = relationship("Bar", back_populates="memberships")
