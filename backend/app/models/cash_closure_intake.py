import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CashClosureIntake(Base):
    __tablename__ = "cash_closure_intakes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_cash_closure_intakes_status",
        ),
        CheckConstraint(
            "classification IN ('AUTO_SAVE', 'SAVE_FOR_REVIEW')",
            name="ck_cash_closure_intakes_classification",
        ),
        UniqueConstraint("document_id", name="uq_cash_closure_intakes_document_id"),
        Index(
            "uq_cash_closure_intakes_bar_date_number_active",
            "bar_id",
            "date",
            "closure_number",
            unique=True,
            sqlite_where=(
                text("bar_id IS NOT NULL AND status != 'rejected'")
            ),
            postgresql_where=(
                text("bar_id IS NOT NULL AND status != 'rejected'")
            ),
        ),
        Index(
            "uq_cash_closure_intakes_legacy_date_number_active",
            "date",
            "closure_number",
            unique=True,
            sqlite_where=text(
                "bar_id IS NULL AND status != 'rejected'"
            ),
            postgresql_where=text(
                "bar_id IS NULL AND status != 'rejected'"
            ),
        ),
        Index(
            "uq_cash_closure_intakes_bar_source_sha256",
            "bar_id",
            "source_sha256",
            unique=True,
            sqlite_where=text("bar_id IS NOT NULL"),
            postgresql_where=text("bar_id IS NOT NULL"),
        ),
        Index(
            "uq_cash_closure_intakes_legacy_source_sha256",
            "source_sha256",
            unique=True,
            sqlite_where=text("bar_id IS NULL"),
            postgresql_where=text("bar_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bar_id: Mapped[int | None] = mapped_column(ForeignKey("bars.id"), nullable=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    closure_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_cash_closures.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    closure_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    card_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    ocr_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    anomalies: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )
    document = relationship("Document")
    closure = relationship("DailyCashClosure")
