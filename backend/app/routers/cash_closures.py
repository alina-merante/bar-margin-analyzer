import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_session_csrf
from app.bar_context import BarContext, BarPermission, require_bar_permission
from app.database import get_db
from app.models import AuthSession
from app.models.cash_closure_intake import CashClosureIntake
from app.models.daily_cash_closure import DailyCashClosure
from app.models.document import Document

router = APIRouter(prefix="/cash-closures", tags=["cash-closures"])
review_context = require_bar_permission(BarPermission.REVIEW_OCR)


class CashClosureCorrection(BaseModel):
    date: dt.date | None = None
    closure_number: str | None = None
    total_amount: Decimal | None = None
    cash_amount: Decimal | None = None
    card_amount: Decimal | None = None


def intake_to_dict(intake: CashClosureIntake) -> dict:
    document = intake.document
    unallocated_amount = unallocated_payment_amount(
        intake.total_amount,
        intake.cash_amount,
        intake.card_amount,
    )
    return {
        "id": intake.id,
        "status": intake.status,
        "classification": intake.classification,
        "date": intake.date.isoformat() if intake.date else None,
        "closure_number": intake.closure_number,
        "total_amount": str(intake.total_amount) if intake.total_amount is not None else None,
        "cash_amount": str(intake.cash_amount) if intake.cash_amount is not None else None,
        "card_amount": str(intake.card_amount) if intake.card_amount is not None else None,
        "unallocated_amount": (
            str(unallocated_amount) if unallocated_amount is not None else None
        ),
        "anomalies": intake.anomalies,
        "ocr_values": intake.ocr_values,
        "created_at": intake.created_at.isoformat(),
        "updated_at": intake.updated_at.isoformat(),
        "document": {
            "id": document.id,
            "month": document.month,
            "original_filename": document.original_filename,
            "file_url": document.file_url,
            "preview_url": document.preview_url,
        },
        "closure_id": intake.closure_id,
    }


def get_intake_for_bar(
    db: Session,
    intake_id: int,
    bar_id: int,
    *,
    pending_only: bool = False,
) -> CashClosureIntake:
    filters = [
        CashClosureIntake.id == intake_id,
        CashClosureIntake.bar_id == bar_id,
        Document.bar_id == bar_id,
    ]
    intake = db.scalar(
        select(CashClosureIntake)
        .join(Document, Document.id == CashClosureIntake.document_id)
        .outerjoin(
            DailyCashClosure,
            DailyCashClosure.id == CashClosureIntake.closure_id,
        )
        .where(*filters)
        .where(
            or_(
                CashClosureIntake.closure_id.is_(None),
                DailyCashClosure.bar_id == bar_id,
            )
        )
    )
    if intake is None:
        raise HTTPException(status_code=404, detail="cash closure review not found")
    if pending_only and intake.status != "pending":
        raise HTTPException(status_code=409, detail="cash closure review is no longer pending")
    return intake


def validate_money(name: str, amount: Decimal | None) -> None:
    if amount is not None and (amount < 0 or amount.as_tuple().exponent < -2):
        raise HTTPException(
            status_code=422,
            detail=f"{name} must be a non-negative amount with at most two decimal places",
        )


def unallocated_payment_amount(
    total_amount: Decimal | None,
    cash_amount: Decimal | None,
    card_amount: Decimal | None,
) -> Decimal | None:
    if total_amount is None or cash_amount is None or card_amount is None:
        return None
    difference = total_amount - cash_amount - card_amount
    return difference if difference > 0 else None


def validate_payment_breakdown(
    total_amount: Decimal,
    cash_amount: Decimal | None,
    card_amount: Decimal | None,
) -> None:
    if (
        cash_amount is not None
        and card_amount is not None
        and cash_amount + card_amount > total_amount
    ):
        raise HTTPException(
            status_code=422,
            detail="La somma di contanti e POS non può superare il totale della chiusura.",
        )


@router.get("/review")
def list_cash_closure_reviews(
    month: str | None = Query(default=None, description="Upload month in YYYY-MM format"),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = (
        select(CashClosureIntake)
        .join(Document, Document.id == CashClosureIntake.document_id)
        .outerjoin(
            DailyCashClosure,
            DailyCashClosure.id == CashClosureIntake.closure_id,
        )
        .where(
            CashClosureIntake.status == "pending",
            CashClosureIntake.bar_id == context.bar.id,
            Document.bar_id == context.bar.id,
            or_(
                CashClosureIntake.closure_id.is_(None),
                DailyCashClosure.bar_id == context.bar.id,
            ),
        )
    )
    if month:
        query = query.where(Document.month == month)
    intakes = db.scalars(query.order_by(CashClosureIntake.created_at.desc())).all()
    return [intake_to_dict(intake) for intake in intakes]


@router.get("/review/{intake_id}")
def get_cash_closure_review(
    intake_id: int,
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(
        db,
        intake_id,
        context.bar.id,
        pending_only=True,
    )
    return intake_to_dict(intake)


@router.patch("/review/{intake_id}")
def correct_cash_closure_review(
    intake_id: int,
    payload: CashClosureCorrection,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(
        db,
        intake_id,
        context.bar.id,
        pending_only=True,
    )
    corrections = payload.model_dump(exclude_unset=True)
    for field, value in corrections.items():
        if field in {"total_amount", "cash_amount", "card_amount"}:
            validate_money(field, value)
        if field == "closure_number" and value is not None:
            value = value.strip() or None
        setattr(intake, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Una chiusura con la stessa data e lo stesso numero è già presente.",
        ) from exc
    db.refresh(intake)
    return intake_to_dict(intake)


@router.post("/review/{intake_id}/approve")
def approve_cash_closure_review(
    intake_id: int,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(db, intake_id, context.bar.id)
    if intake.status == "approved":
        return intake_to_dict(intake)
    if intake.status != "pending":
        raise HTTPException(status_code=409, detail="cash closure review is no longer pending")
    if intake.date is None or not intake.closure_number or intake.total_amount is None:
        raise HTTPException(
            status_code=422,
            detail="Data, numero di chiusura e totale sono necessari per approvare.",
        )
    validate_money("total_amount", intake.total_amount)
    validate_money("cash_amount", intake.cash_amount)
    validate_money("card_amount", intake.card_amount)
    validate_payment_breakdown(
        intake.total_amount,
        intake.cash_amount,
        intake.card_amount,
    )

    duplicate_closure = db.scalar(
        select(DailyCashClosure).where(
            DailyCashClosure.bar_id == context.bar.id,
            DailyCashClosure.date == intake.date,
            DailyCashClosure.closure_number == intake.closure_number,
        )
    )
    duplicate_intake = db.scalar(
        select(CashClosureIntake).where(
            CashClosureIntake.id != intake.id,
            CashClosureIntake.bar_id == context.bar.id,
            CashClosureIntake.date == intake.date,
            CashClosureIntake.closure_number == intake.closure_number,
            CashClosureIntake.status.in_(("pending", "approved")),
        )
    )
    if duplicate_closure is not None or duplicate_intake is not None:
        raise HTTPException(
            status_code=409,
            detail="Una chiusura con la stessa data e lo stesso numero è già presente.",
        )

    closure = DailyCashClosure(
        bar_id=context.bar.id,
        date=intake.date,
        closure_number=intake.closure_number,
        total_amount=intake.total_amount,
        cash_amount=intake.cash_amount,
        card_amount=intake.card_amount,
        document_id=intake.document_id,
    )
    db.add(closure)
    intake.status = "approved"
    intake.document.status = "Elaborato"

    try:
        db.flush()
        intake.closure_id = closure.id
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Una chiusura con la stessa data e lo stesso numero è già presente.",
        ) from exc
    db.refresh(intake)
    return intake_to_dict(intake)


@router.post("/review/{intake_id}/reject")
def reject_cash_closure_review(
    intake_id: int,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(
        db,
        intake_id,
        context.bar.id,
        pending_only=True,
    )
    intake.status = "rejected"
    intake.document.status = "Rifiutata"
    db.commit()
    return {"id": intake.id, "status": intake.status}
