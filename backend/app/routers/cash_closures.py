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
from app.bar_context import (
    get_active_bar_context,
    financial_read_scope,
)
from app.database import get_db
from app.models import AdminAudit, AuthSession, MembershipRole
from app.models.cash_closure_intake import CashClosureIntake
from app.models.daily_cash_closure import DailyCashClosure
from app.models.document import Document
from app.routers import documents
from app.routers.upload_files import document_urls, open_upload_file
from app.services import cash_closure_policy, document_ocr

from app.bar_context import (
    require_delegable_permission,
    financial_read_scope,
    require_financial_permissions,
)
from app.permissions import DelegablePermission

router = APIRouter(prefix="/cash-closures", tags=["cash-closures"])
review_context = require_delegable_permission(
    DelegablePermission.CASH_CLOSURES_REVIEW
)

edit_context = require_delegable_permission(
    DelegablePermission.CASH_CLOSURES_EDIT
)


class CashClosureCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date | None = None
    closure_number: str | None = None
    total_amount: Decimal | None = None
    cash_amount: Decimal | None = None
    card_amount: Decimal | None = None
    receipts_count: int | None = Field(default=None, ge=0, le=999999)


class CashClosureAnnulment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class ReprocessConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_version: str
    extraction_version: str


def can_approve(context: BarContext) -> bool:
    return context.role == MembershipRole.owner or context.user.is_global_admin


def can_use_closure_permission(context: BarContext, permission: DelegablePermission) -> bool:
    try:
        require_financial_permissions(context, permission)
        return True
    except HTTPException as exc:
        if exc.status_code == 403:
            return False
        raise


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
        "can_edit": can_use_closure_permission(
            context, DelegablePermission.CASH_CLOSURES_EDIT
        ) if context else False,
        "can_verify": can_use_closure_permission(
            context, DelegablePermission.CASH_CLOSURES_REVIEW
        ) if context else False,
        "classification": intake.classification,
        "verification": (intake.ocr_values or {}).get("verification"),
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
    if (intake.status in {"approved", "annulled"}) != (intake.closure_id is not None):
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



def cash_closure_read_scope(context: BarContext) -> str:
    return financial_read_scope(
        context,
        DelegablePermission.CASH_CLOSURES_VIEW_OWN,
        DelegablePermission.CASH_CLOSURES_VIEW_ALL,
    )


def check_cash_closure_read_access(
    context: BarContext,
    intake: CashClosureIntake,
) -> None:
    if (
        cash_closure_read_scope(context) == "own"
        and intake.document.created_by_user_id != context.user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="Chiusura da verificare non trovata.",
        )



@router.get("/history")
def list_cash_closure_history(
    month: str | None = Query(default=None),
    context: BarContext = Depends(get_active_bar_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    scope = cash_closure_read_scope(context)

    query = (
        select(CashClosureIntake, DailyCashClosure, Document)
        .join(
            DailyCashClosure,
            DailyCashClosure.id == CashClosureIntake.closure_id,
        )
        .join(Document, Document.id == CashClosureIntake.document_id)
        .where(
            CashClosureIntake.bar_id == context.bar.id,
            DailyCashClosure.bar_id == context.bar.id,
            Document.bar_id == context.bar.id,
            DailyCashClosure.document_id == Document.id,
            CashClosureIntake.status.in_(("approved", "annulled")),
        )
    )

    if scope == "own":
        query = query.where(
            Document.created_by_user_id == context.user.id
        )

    if month:
        if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
            raise HTTPException(
                status_code=422,
                detail="Il mese deve avere il formato AAAA-MM.",
            )

        year, month_number = map(int, month.split("-"))
        start = dt.date(year, month_number, 1)
        end = dt.date(
            year, month_number, monthrange(year, month_number)[1]
        )

        query = query.where(
            DailyCashClosure.date >= start,
            DailyCashClosure.date <= end,
        )

    rows = db.execute(
        query.order_by(
            DailyCashClosure.date.desc(),
            DailyCashClosure.id.desc(),
        )
    ).all()

    return [
        {
            "id": intake.id,
            "closure_id": closure.id,
            "document_id": document.id,
            "date": closure.date.isoformat(),
            "closure_number": closure.closure_number,
            "total_amount": str(closure.total_amount),
            "cash_amount": (
                str(closure.cash_amount)
                if closure.cash_amount is not None else None
            ),
            "card_amount": (
                str(closure.card_amount)
                if closure.card_amount is not None else None
            ),
            "status": intake.status,
            "can_annul": (
                intake.status == "approved"
                and closure.annulled_at is None
                and can_approve(context)
            ),
            "annulled_at": (
                closure.annulled_at.isoformat()
                if closure.annulled_at else None
            ),
            "annulled_by_user_id": closure.annulled_by_user_id,
            "annulment_reason": closure.annulment_reason,
            "document": {
                "id": document.id,
                "original_filename": document.original_filename,
                "file_url": document_urls(document)[0],
                "preview_url": document_urls(document)[1],
            },
        }
        for intake, closure, document in rows
    ]


@router.get("/review")
def list_cash_closure_reviews(
    month: str | None = Query(default=None, description="Closure month in YYYY-MM format"),
    context: BarContext = Depends(get_active_bar_context),
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
    if cash_closure_read_scope(context) == "own":
        query = query.where(Document.created_by_user_id == context.user.id)

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
    context: BarContext = Depends(get_active_bar_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(
        db,
        intake_id,
        context.bar.id,
        pending_only=True,
    )
    check_cash_closure_read_access(context, intake)
    return intake_to_dict(intake, context)


@router.patch("/review/{intake_id}")
def correct_cash_closure_review(
    intake_id: int,
    payload: CashClosureCorrection,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(edit_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(
        db,
        intake_id,
        context.bar.id,
        pending_only=True,
        lock=True,
    )
    check_cash_closure_read_access(context, intake)
    corrections = payload.model_dump(exclude_unset=True)
    if corrections and (intake.ocr_values or {}).get("verification"):
        values = dict(intake.ocr_values)
        values.pop("verification", None)
        intake.ocr_values = values
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
    context: BarContext = Depends(edit_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(db, intake_id, context.bar.id, pending_only=True)
    check_cash_closure_read_access(context, intake)
    initial_version = review_version(intake)
    extracted = extract_original(intake)
    refreshed_context = revalidate_active_bar_context(request, db, context.bar.id)
    edit_context(refreshed_context)
    intake = get_intake_for_bar(db, intake_id, context.bar.id, pending_only=True)
    check_cash_closure_read_access(refreshed_context, intake)
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
    context: BarContext = Depends(edit_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(db, intake_id, context.bar.id, pending_only=True)
    check_cash_closure_read_access(context, intake)
    if review_version(intake) != payload.review_version:
        raise HTTPException(status_code=409, detail="La scheda è cambiata. Ripeti la rielaborazione.")
    extracted = extract_original(intake)
    if version_of(extracted) != payload.extraction_version:
        raise HTTPException(status_code=409, detail="Il risultato OCR è cambiato. Ripeti la rielaborazione.")
    refreshed_context = revalidate_active_bar_context(request, db, context.bar.id, lock=True)
    edit_context(refreshed_context)
    intake = get_intake_for_bar(
        db, intake_id, context.bar.id, pending_only=True, lock=True
    )
    check_cash_closure_read_access(refreshed_context, intake)
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
    previous_ocr.pop("verification", None)
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
    new_ocr = dict(documents.json_safe(extracted))
    new_ocr.pop("verification", None)
    intake.ocr_values = {
        **new_ocr,
        "reprocessing_history": history,
    }
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


@router.post("/review/{intake_id}/verify")
def verify_cash_closure_review(
    intake_id: int,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    intake = get_intake_for_bar(
        db, intake_id, context.bar.id,
        pending_only=True, lock=True,
    )
    check_cash_closure_read_access(context, intake)

    if intake.date is None or not intake.closure_number or intake.total_amount is None:
        raise HTTPException(
            status_code=422,
            detail="Completa data, numero e totale prima della verifica.",
        )

    validate_money("total_amount", intake.total_amount)
    validate_money("cash_amount", intake.cash_amount)
    validate_money("card_amount", intake.card_amount)
    validate_payment_breakdown(
        intake.total_amount, intake.cash_amount, intake.card_amount
    )

    values = dict(intake.ocr_values or {})
    if values.get("verification"):
        raise HTTPException(
            status_code=409,
            detail="Chiusura già verificata.",
        )

    values["verification"] = {
        "user_id": _auth_session.user_id,
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    intake.ocr_values = values
    db.commit()
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
    if not (intake.ocr_values or {}).get("verification"):
        raise HTTPException(
            status_code=409,
            detail="La chiusura deve essere verificata prima dell'approvazione.",
        )
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


@router.post("/review/{intake_id}/annul")
def annul_cash_closure_review(
    intake_id: int,
    payload: CashClosureAnnulment,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(get_active_bar_context),
    db: Session = Depends(get_db),
) -> dict:
    if not can_approve(context):
        raise HTTPException(
            status_code=403,
            detail="Solo il proprietario del bar o un amministratore globale può annullare la chiusura.",
        )

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(
            status_code=422,
            detail="La motivazione dell'annullamento è obbligatoria.",
        )

    intake = get_intake_for_bar(db, intake_id, context.bar.id, lock=True)

    if intake.status != "approved":
        raise HTTPException(
            status_code=409,
            detail="È possibile annullare soltanto una chiusura approvata.",
        )

    closure = db.scalar(
        select(DailyCashClosure)
        .where(
            DailyCashClosure.id == intake.closure_id,
            DailyCashClosure.bar_id == context.bar.id,
            DailyCashClosure.document_id == intake.document_id,
        )
        .with_for_update()
    )

    if closure is None:
        raise HTTPException(
            status_code=409,
            detail="La chiusura contabile collegata non è coerente.",
        )

    if closure.annulled_at is not None:
        raise HTTPException(
            status_code=409,
            detail="La chiusura risulta già annullata.",
        )

    annulled_at = dt.datetime.now(dt.timezone.utc)

    closure.annulled_at = annulled_at
    closure.annulled_by_user_id = _auth_session.user_id
    closure.annulment_reason = reason
    intake.status = "annulled"

    db.add(
        AdminAudit(
            actor_id=_auth_session.user_id,
            action="cash_closure.annul",
            bar_id=context.bar.id,
            changes={
                "intake_id": intake.id,
                "closure_id": closure.id,
                "document_id": intake.document_id,
                "previous_status": "approved",
                "new_status": "annulled",
                "reason": reason,
                "annulled_at": annulled_at.isoformat(),
            },
        )
    )

    db.commit()
    db.refresh(intake)

    return {
        "id": intake.id,
        "closure_id": closure.id,
        "status": intake.status,
        "annulled_at": annulled_at.isoformat(),
        "annulled_by_user_id": _auth_session.user_id,
        "annulment_reason": reason,
    }


@router.post("/review/{intake_id}/reject")
def reject_cash_closure_review(
    intake_id: int,
    _auth_session: AuthSession = Depends(require_session_csrf),
    context: BarContext = Depends(review_context),
    db: Session = Depends(get_db),
) -> dict:
    if not can_approve(context):
        raise HTTPException(
            status_code=403,
            detail="Solo il proprietario del bar o un amministratore globale può rifiutare la chiusura.",
        )
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
