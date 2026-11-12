from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base
from app.permissions import DelegablePermission


class MembershipPermission(Base):
    __tablename__ = "membership_permissions"
    __table_args__ = (
        UniqueConstraint("membership_id", "permission", name="uq_membership_permissions_code"),
        CheckConstraint(
            "permission IN ("
            + ", ".join(f"'{permission.value}'" for permission in DelegablePermission)
            + ")",
            name="ck_membership_permissions_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    membership_id: Mapped[int] = mapped_column(
        ForeignKey("user_bar_memberships.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission: Mapped[str] = mapped_column(String(64), nullable=False)

    membership = relationship("UserBarMembership", back_populates="permissions")

    @validates("permission")
    def validate_permission(self, _key: str, value: str) -> str:
        return DelegablePermission(value).value
