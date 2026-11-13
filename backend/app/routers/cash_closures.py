import datetime as dt
import hashlib
import json
import re
from calendar import monthrange
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_session_csrf
from app import config
from app.bar_context import (
    BarContext, BarPermission, require_bar_permission, revalidate_active_bar_context,
)
from app.database import get_db
from app.models import AuthSession, MembershipRole
from app.models.cash_closure_intake import CashClosureIntake
from app.models.daily_cash_closure import DailyCashClosure
from app.models.document import Document
from app.routers import documents
from app.routers.upload_files import document_urls, open_upload_file
from app.services import cash_closure_policy, document_ocr

router = APIRouter(prefix="/cash-closures", tags=["cash-closures"])
review_context = require_bar_permission(BarPermission.REVIEW_OCR)


class CashClosureCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date | None = None
    closure_number: str | None = None
    total_amount: Decimal | None = None
    cash_amount: Decimal | None = None
    card_amount: Decimal | None = None
    receipts_count: int | None = Field(default=None, ge=0, le=999999)


class ReprocessConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_version: str
    extraction_version: str


def can_approve(context: BarContext) -> bool:
    return context.role == MembershipRole.owner or context.user.is_global_admin


def intake_to_dict(intake: CashClosureIntake, context: BarContext | None = None) -> dict:
    document = intake.document
    file_url, preview_url = document_urls(document)
    unallocated_amount = unallocated_payment_amount(
        intake.total_amount,
        intake.cash_amount,
        intake.card_amount,
    )
    return {
        "id": intake.id,
        "status": intake.status,
        "can_approve": can_approve(context) if context else False,
        "classification": intake.classification,
        "date": intake.date.isoformat() if intake.date else None,
        "closure_number": intake.closure_number,
        "total_amount": str(intake.total_amount) if intake.total_amount is not None else None,
        "cash_amount": str(intake.cash_amount) if intake.cash_amount is not None else None,
        "card_amount": str(intake.card_amount) if intake.card_amount is not None else None,
        "receipts_count": intake.ocr_values.get(
            "review_receipts_count", intake.ocr_values.get("receipts_count")
        ),
        "receipts_total": intake.ocr_values.get("receipts_total"),
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
            "file_url": file_url,
            "preview_url": preview_url,
        },
        "closure_id": intake.closure_id,
    }


def get_intake_for_bar(
    db: Session,
    intake_id: int,
    bar_id: int,
    *,
    pending_only: bool = False,
    lock: bool = False,
) -> CashClosureIntake:
    filters = [
        CashClosureIntake.id == intake_id,
        CashClosureIntake.bar_id == bar_id,
        Document.bar_id == bar_id,
    ]
    query = (
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
                (DailyCashClosure.bar_id == bar_id)
                & (DailyCashClosure.document_id == CashClosureIntake.document_id),
            )
        )
    )
    if lock:
        query = query.with_for_update(of=CashClosureIntake).execution_options(
            populate_existing=True
        )
    intake = db.scalar(query)
    if intake is None:
        raise HTTPException(status_code=404, detail="Chiusura da verificare non trovata.")
    if (intake.status == "approved") != (intake.closure_id is not None):
        raise HTTPException(status_code=409, detail="La scheda della chiusura non è coerente.")
    if pending_only and intake.status != "pending":
        raise HTTPException(status_code=409, detail="La chiusura non è più in attesa di revisione.")
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
    month: str | None = Query(default=None, description="Closure month in YYYY-MM format"),
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
            CashClosureIntake.closure_id.is_(None),
            CashClosureIntake.bar_id == context.bar.id,
            Document.bar_id == context.bar.id,
            or_(
                CashClosureIntake.closure_id.is_(None),
                (DailyCashClosure.bar_id == context.bar.id)
                & (DailyCashClosure.document_id == CashClosureIntake.document_id),
            ),
        )
    )
    if month:
        if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
            raise HTTPException(status_code=422, detail="Il mese deve avere il formato AAAA-MM.")
        year, month_number = map(int, month.split("-"))
        if year < 1:
            raise HTTPException(status_code=422, detail="Il mese deve avere il formato AAAA-MM.")
        start = dt.date(year, month_number, 1)
        end = dt.date(year, month_number, monthrange(year, month_number)[1])
        query = query.where(CashClosureIntake.date >= start, CashClosureIntake.date <= end)
    intakes = db.scalars(query.order_by(CashClosureIntake.created_at.desc())).all()
    return [intake_to_dict(intake, context) for intake in intakes]


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
    return intake_to_dict(intake, context)


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
        lock=True,
    )
    corrections = payload.model_dump(exclude_unset=True)
    for field, value in corrections.items():
        if field == "receipts_count":
            intake.ocr_values = {**intake.ocr_values, "review_receipts_count": value}
            continue
        if field in {"total_amount", "cash_amount", "card_amount"}:
            validate_money(field, value)
        if field == "closure_number" and value is not None:
            value = value.strip() or None
        setattr(intake, field, value)

    try:
        if "date" in corrections and intake.date is not None:
            intake.document.month = intake.date.isoformat()[:7]
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Una chiusura con la stessa data e lo stesso numero è già presente.",
        ) from exc
    db.refresh(intake)
    return intake_to_dict(intake, context)


REPROCESS_FIELDS = (
    "date", "closure_number", "total_amount", "cash_amount", "card_amount",
    "receipts_count", "receipts_total",
)


def reprocess_current_values(intake: CashClosureIntake) -> dict:
    return {
        **{field: getattr(intake, field) for field in REPROCESS_FIELDS[:5]},
        "receipts_count": intake.ocr_values.get(
            "review_receipts_count", intake.ocr_values.get("receipts_count")
        ),
        "receipts_total": intake.ocr_values.get("receipts_total"),
    }


def version_of(value: object) -> str:
    encoded = json.dumps(
        documents.json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def review_version(intake: CashClosureIntake) -> str:
    return version_of({
        "id": intake.id,
        "document_id": intake.document_id,
        "stored_filename": intake.document.stored_filename,
        "source_sha256": intake.source_sha256,
        "status": intake.status,
        "values": reprocess_current_values(intake),
        "ocr_values": intake.ocr_values,
        "anomalies": intake.anomalies,
    })


def extract_original(intake: CashClosureIntake) -> dict:
    document = intake.document
    if not document_urls(document)[0]:
        raise HTTPException(status_code=404, detail="Documento originale non disponibile.")
    try:
        file, _ = open_upload_file(config.UPLOAD_DOCUMENTS_DIR, document.stored_filename)
        with file:
            content = file.read()
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Documento originale non disponibile.") from exc
        raise
    if hashlib.sha256(content).hexdigest() != intake.source_sha256:
        raise HTTPException(
            status_code=409,
            detail="Il documento originale non corrisponde al file importato; rielaborazione interrotta.",
        )
    extension = document.stored_filename.rsplit(".", 1)[-1].lower()
    try:
        extracted = documents.extract_daily_cash_closure(content, extension)
    except document_ocr.DocumentReadError as exc:
        raise HTTPException(
            status_code=422, detail="Il documento originale non è leggibile."
        ) from exc
    if cash_closure_policy.classify_closure(extracted) == cash_closure_policy.REJECT:
        raise HTTPException(
            status_code=422,
            detail="Il documento non contiene evidenze sufficienti per riconoscere una chiusura di cassa.",
        )
    return extracted


@router.post("/review/{intake_id}/reprocess/preview")
def preview_cash_closure_reprocess(
    intake_id: int,
    request: Request,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(db, intake_id, context.bar.id, pending_only=True)
    initial_version = review_version(intake)
    extracted = extract_original(intake)
    refreshed_context = revalidate_active_bar_context(request, db, context.bar.id)
    review_context(refreshed_context)
    intake = get_intake_for_bar(db, intake_id, context.bar.id, pending_only=True)
    if review_version(intake) != initial_version:
        raise HTTPException(status_code=409, detail="La scheda è cambiata. Ripeti la rielaborazione.")
    return {
        "previous": documents.json_safe(reprocess_current_values(intake)),
        "proposed": documents.json_safe({field: extracted.get(field) for field in REPROCESS_FIELDS}),
        "review_version": initial_version,
        "extraction_version": version_of(extracted),
    }


@router.post("/review/{intake_id}/reprocess")
def confirm_cash_closure_reprocess(
    intake_id: int,
    payload: ReprocessConfirmation,
    request: Request,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(db, intake_id, context.bar.id, pending_only=True)
    if review_version(intake) != payload.review_version:
        raise HTTPException(status_code=409, detail="La scheda è cambiata. Ripeti la rielaborazione.")
    extracted = extract_original(intake)
    if version_of(extracted) != payload.extraction_version:
        raise HTTPException(status_code=409, detail="Il risultato OCR è cambiato. Ripeti la rielaborazione.")
    refreshed_context = revalidate_active_bar_context(request, db, context.bar.id, lock=True)
    review_context(refreshed_context)
    intake = get_intake_for_bar(
        db, intake_id, context.bar.id, pending_only=True, lock=True
    )
    if review_version(intake) != payload.review_version:
        raise HTTPException(status_code=409, detail="La scheda è cambiata. Ripeti la rielaborazione.")

    if extracted.get("date") is not None and extracted.get("closure_number"):
        existing_closure = documents.find_existing_cash_closure(db, extracted, context.bar.id)
        if existing_closure is not None:
            raise HTTPException(
                status_code=409,
                detail="Una chiusura con la stessa data e lo stesso numero è già presente.",
            )

    previous_ocr = dict(intake.ocr_values)
    history = list(previous_ocr.pop("reprocessing_history", []))
    history.append({
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "user_id": _auth_session.user_id,
        "previous_values": documents.json_safe(reprocess_current_values(intake)),
        "previous_ocr": previous_ocr,
        "previous_anomalies": intake.anomalies,
    })
    for field in REPROCESS_FIELDS[:5]:
        setattr(intake, field, extracted.get(field))
    intake.ocr_values = {**documents.json_safe(extracted), "reprocessing_history": history}
    intake.anomalies = list((extracted.get("diagnostics") or {}).get("anomalies") or [])
    intake.classification = cash_closure_policy.SAVE_FOR_REVIEW
    try:
        if intake.date is not None:
            intake.document.month = intake.date.isoformat()[:7]
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Una chiusura con la stessa data e lo stesso numero è già presente.",
        ) from exc
    db.refresh(intake)
    return intake_to_dict(intake, context)


@router.post("/review/{intake_id}/approve")
def approve_cash_closure_review(
    intake_id: int,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    if not can_approve(context):
        raise HTTPException(
            status_code=403,
            detail="Solo il proprietario del bar o un amministratore globale può approvare la chiusura.",
        )
    intake = get_intake_for_bar(db, intake_id, context.bar.id, lock=True)
    if intake.status == "approved":
        return intake_to_dict(intake, context)
    if intake.status != "pending":
        raise HTTPException(status_code=409, detail="La chiusura non è più in attesa di revisione.")
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
        receipts_count=intake.ocr_values.get(
            "review_receipts_count", intake.ocr_values.get("receipts_count")
        ),
        document_id=intake.document_id,
    )
    db.add(closure)
    intake.status = "approved"
    intake.document.month = intake.date.isoformat()[:7]
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
    return intake_to_dict(intake, context)


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
        lock=True,
    )
    intake.status = "rejected"
    intake.document.status = "Rifiutata"
    db.commit()
    return {"id": intake.id, "status": intake.status}
