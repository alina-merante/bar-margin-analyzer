import asyncio
import datetime as dt
import sys
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import CashClosureIntake, DailyCashClosure, Document
from app.routers import cash_closures, documents
from app.routers.analytics import monthly_pnl


@pytest.fixture
def review_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cash-review.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def create_document(session, month="2026-11"):
    document = Document(
        month=month,
        original_filename="closure.png",
        stored_filename="closure.png",
        section="cash",
        document_type="PNG",
        category="Immagine",
        result="Test OCR",
        file_url="/uploads/documents/closure.png",
        preview_url="/uploads/documents/closure.png",
    )
    session.add(document)
    session.flush()
    return document


def create_intake(
    session,
    document,
    *,
    date=dt.date(2026, 11, 3),
    closure_number="5",
    total_amount=Decimal("200.00"),
    cash_amount=None,
    card_amount=None,
    source_sha256="a" * 64,
):
    intake = CashClosureIntake(
        document_id=document.id,
        source_sha256=source_sha256,
        classification="SAVE_FOR_REVIEW",
        status="pending",
        date=date,
        closure_number=closure_number,
        total_amount=total_amount,
        cash_amount=cash_amount,
        card_amount=card_amount,
        ocr_values={"diagnostics": {"anomalies": ["total_amount:ambiguous"]}},
        anomalies=["total_amount:ambiguous"],
    )
    session.add(intake)
    session.commit()
    return intake


def test_pending_review_is_excluded_until_approved_and_repeated_approval_counts_once(
    review_session,
):
    document = create_document(review_session)
    intake = create_intake(review_session, document, cash_amount=Decimal("0.00"))

    before = monthly_pnl(review_session, dt.date(2026, 11, 1), dt.date(2026, 12, 1))
    assert before["revenue"] == Decimal("0.00")

    approved = cash_closures.approve_cash_closure_review(intake.id, review_session)
    again = cash_closures.approve_cash_closure_review(intake.id, review_session)
    closures = review_session.scalars(select(DailyCashClosure)).all()
    after = monthly_pnl(review_session, dt.date(2026, 11, 1), dt.date(2026, 12, 1))

    assert approved["closure_id"] == again["closure_id"]
    assert len(closures) == 1
    assert closures[0].cash_amount == Decimal("0.00")
    assert closures[0].card_amount is None
    assert after["revenue"] == Decimal("200.00")


def test_approval_requires_date_number_and_total(review_session):
    document = create_document(review_session)
    intake = create_intake(review_session, document, total_amount=None)

    with pytest.raises(HTTPException) as error:
        cash_closures.approve_cash_closure_review(intake.id, review_session)

    assert error.value.status_code == 422
    assert review_session.scalars(select(DailyCashClosure)).all() == []


def test_duplicate_approval_conflicts_with_existing_accounted_closure(review_session):
    document = create_document(review_session)
    intake = create_intake(review_session, document)
    review_session.add(
        DailyCashClosure(
            date=intake.date,
            closure_number=intake.closure_number,
            total_amount=Decimal("200.00"),
        )
    )
    review_session.commit()

    with pytest.raises(HTTPException) as error:
        cash_closures.approve_cash_closure_review(intake.id, review_session)

    assert error.value.status_code == 409
    assert len(review_session.scalars(select(DailyCashClosure)).all()) == 1


def test_review_correction_cannot_duplicate_another_pending_date_and_number(review_session):
    first_document = create_document(review_session)
    first = create_intake(review_session, first_document)
    second_document = create_document(review_session)
    second = create_intake(
        review_session,
        second_document,
        date=dt.date(2026, 11, 4),
        closure_number="6",
        source_sha256="b" * 64,
    )

    with pytest.raises(HTTPException) as error:
        cash_closures.correct_cash_closure_review(
            second.id,
            cash_closures.CashClosureCorrection(
                date=first.date,
                closure_number=first.closure_number,
            ),
            review_session,
        )

    assert error.value.status_code == 409
    review_session.expire_all()
    assert review_session.get(CashClosureIntake, second.id).date == dt.date(2026, 11, 4)


def test_correction_and_manual_rejection(review_session):
    document = create_document(review_session)
    intake = create_intake(review_session, document, date=None, closure_number=None)

    corrected = cash_closures.correct_cash_closure_review(
        intake.id,
        cash_closures.CashClosureCorrection(
            date=dt.date(2026, 11, 4),
            closure_number="6",
            total_amount=Decimal("0.00"),
        ),
        review_session,
    )
    assert corrected["date"] == "2026-11-04"
    assert corrected["total_amount"] == "0.00"

    rejected = cash_closures.reject_cash_closure_review(intake.id, review_session)
    assert rejected == {"id": intake.id, "status": "rejected"}
    assert review_session.scalars(select(DailyCashClosure)).all() == []


def test_review_api_exposes_original_document_and_ocr_anomalies(review_session):
    document = create_document(review_session)
    intake = create_intake(review_session, document)

    listed = cash_closures.list_cash_closure_reviews(None, review_session)
    detail = cash_closures.get_cash_closure_review(intake.id, review_session)

    assert listed[0]["document"]["file_url"] == document.file_url
    assert listed[0]["anomalies"] == ["total_amount:ambiguous"]
    assert detail["ocr_values"]["diagnostics"]["anomalies"] == [
        "total_amount:ambiguous"
    ]


def test_upload_stages_readable_but_unresolved_closure_without_touching_kpis(
    review_session, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        documents,
        "extract_daily_cash_closure",
        lambda _content, _extension: {
            "date": None,
            "closure_number": "5",
            "total_amount": Decimal("200.00"),
            "cash_amount": None,
            "card_amount": None,
            "receipts_count": None,
            "diagnostics": {
                "anomalies": ["date:missing"],
                "fields": {
                    "date": {"status": "missing"},
                    "closure_number": {"status": "ok"},
                    "total_amount": {"status": "ok"},
                },
                "total_label": "explicit",
            },
        },
    )

    response = asyncio.run(
        documents.upload_document(
            file=UploadFile(file=BytesIO(b"unique readable closure"), filename="closure.png"),
            month="2026-11",
            section="cash",
            db=review_session,
        )
    )

    intake = review_session.scalars(select(CashClosureIntake)).one()
    assert response["status"] == "Da verificare"
    assert response["cash_closure_classification"] == "SAVE_FOR_REVIEW"
    assert intake.status == "pending"
    assert review_session.scalars(select(DailyCashClosure)).all() == []
    assert review_session.scalars(select(Document)).one().month == "2026-11"
    pnl = monthly_pnl(review_session, dt.date(2026, 11, 1), dt.date(2026, 12, 1))
    assert pnl["revenue"] == Decimal("0.00")


def test_upload_hash_prevents_duplicate_review_documents(review_session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        documents,
        "extract_daily_cash_closure",
        lambda _content, _extension: {
            "date": None,
            "closure_number": "5",
            "total_amount": Decimal("200.00"),
            "cash_amount": None,
            "card_amount": None,
            "receipts_count": None,
            "diagnostics": {
                "anomalies": ["date:missing"],
                "fields": {
                    "date": {"status": "missing"},
                    "closure_number": {"status": "ok"},
                    "total_amount": {"status": "ok"},
                },
            },
        },
    )
    upload = lambda: asyncio.run(
        documents.upload_document(
            file=UploadFile(file=BytesIO(b"same review file"), filename="closure.png"),
            month="2026-11",
            section="cash",
            db=review_session,
        )
    )

    upload()
    with pytest.raises(HTTPException) as error:
        upload()
    assert error.value.status_code == 409
    assert len(review_session.scalars(select(CashClosureIntake)).all()) == 1
    assert len(review_session.scalars(select(Document)).all()) == 1


def test_upload_without_closure_evidence_is_rejected_without_persistence(
    review_session, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        documents,
        "extract_daily_cash_closure",
        lambda _content, _extension: {
            "date": None,
            "closure_number": None,
            "total_amount": None,
            "cash_amount": None,
            "card_amount": None,
            "receipts_count": None,
            "diagnostics": {
                "anomalies": [],
                "fields": {"date": {"status": "missing"}},
            },
        },
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            documents.upload_document(
                file=UploadFile(file=BytesIO(b"unreadable"), filename="closure.png"),
                month="2026-11",
                section="cash",
                db=review_session,
            )
        )

    assert error.value.status_code == 422
    assert review_session.scalars(select(CashClosureIntake)).all() == []
    assert review_session.scalars(select(Document)).all() == []
