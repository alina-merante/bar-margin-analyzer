import datetime as dt
import os
import sys
import tempfile
from decimal import Decimal
from io import BytesIO

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import DailyCashClosure, Document, InvoicePaymentLink, Payment, Transaction
from app.routers import documents as documents_router, imports as imports_router
from app.routers.analytics import monthly_pnl


def test_bank_csv_document_month_uses_single_transaction_month_not_selected_month():
    bank_csv = (
        b"date,description,amount\n"
        b"2026-07-03,SEPA transfer - Torrefazione Italiana S.p.A.,-420.00\n"
        b"2026-07-09,Bank transfer - Distribuzione Bevande S.R.L.,-310.00\n"
        b"2026-07-11,Payment to Energia Bar Luglio,-95.00\n"
        b"2026-07-12,Card payment - Pulizie Splendore,-120.00\n"
        b"2026-07-14,POS settlement - Incassi carte,2000.00\n"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        engine = create_engine(f"sqlite:///{temp_dir}/test_bank_import.db")
        Base.metadata.create_all(engine)
        old_cwd = os.getcwd()
        os.chdir(temp_dir)

        try:
            with Session(engine) as session:
                first_import = imports_router.import_bank_csv(
                    UploadFile(
                        file=BytesIO(bank_csv),
                        filename="05_movimenti_bancari_2026-07.csv",
                    ),
                    session,
                )
                duplicate_import = imports_router.import_bank_csv(
                    UploadFile(
                        file=BytesIO(bank_csv),
                        filename="05_movimenti_bancari_2026-07.csv",
                    ),
                    session,
                )

                assert first_import == {"imported_rows": 5, "skipped_rows": 0}
                assert duplicate_import == {"imported_rows": 0, "skipped_rows": 5}

                transactions = session.scalars(
                    select(Transaction).order_by(Transaction.id)
                ).all()
                assert len(transactions) == 5
                assert transactions[0].counterparty == "Torrefazione Italiana S.p.A."
                assert transactions[0].amount == Decimal("-420.00")

                document = __import__("asyncio").run(
                    documents_router.upload_document(
                        file=UploadFile(
                            file=BytesIO(bank_csv),
                            filename="05_movimenti_bancari_2026-07.csv",
                        ),
                        month="2026-09",
                        section="bank",
                        db=session,
                    )
                )

                assert document["month"] == "2026-07"
                assert len(session.scalars(select(Transaction)).all()) == 5
                assert session.scalars(select(Payment)).all() == []
                assert session.scalars(select(InvoicePaymentLink)).all() == []

                pnl = monthly_pnl(
                    session,
                    dt.date(2026, 7, 1),
                    dt.date(2026, 8, 1),
                )
                assert pnl["expenses"] == Decimal("0.00")
        finally:
            os.chdir(old_cwd)


def test_mixed_month_bank_csv_keeps_selected_document_month():
    bank_csv = (
        b"date,description,amount\n"
        b"2026-07-31,Bank movement July,-10.00\n"
        b"2026-08-01,Bank movement August,-20.00\n"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        engine = create_engine(f"sqlite:///{temp_dir}/test_mixed_bank_month.db")
        Base.metadata.create_all(engine)
        old_cwd = os.getcwd()
        os.chdir(temp_dir)

        try:
            with Session(engine) as session:
                document = __import__("asyncio").run(
                    documents_router.upload_document(
                        file=UploadFile(
                            file=BytesIO(bank_csv),
                            filename="mixed_bank_months.csv",
                        ),
                        month="2026-09",
                        section="bank",
                        db=session,
                    )
                )

                assert document["month"] == "2026-09"
        finally:
            os.chdir(old_cwd)


def test_cash_upload_uses_extracted_closure_month_for_document_history():
    with tempfile.TemporaryDirectory() as temp_dir:
        engine = create_engine(f"sqlite:///{temp_dir}/test_documents.db")
        Base.metadata.create_all(engine)
        old_cwd = os.getcwd()
        original_extractor = documents_router.extract_daily_cash_closure
        os.chdir(temp_dir)

        def fake_extract_daily_cash_closure(content: bytes, extension: str) -> dict:
            return {
                "date": dt.date(2026, 7, 14),
                "closure_number": "14",
                "total_amount": Decimal("945.80"),
                "cash_amount": Decimal("300.00"),
                "card_amount": Decimal("645.80"),
                "receipts_count": 42,
            }

        documents_router.extract_daily_cash_closure = fake_extract_daily_cash_closure

        try:
            with Session(engine) as session:
                result = __import__("asyncio").run(
                    documents_router.upload_document(
                        file=UploadFile(file=BytesIO(b"cash closure"), filename="closure.png"),
                        month="2026-09",
                        section="cash",
                        db=session,
                    )
                )

                closure = session.scalar(select(DailyCashClosure))
                july_documents = documents_router.list_documents("2026-07", session)
                september_documents = documents_router.list_documents("2026-09", session)

                assert closure is not None
                assert closure.date == dt.date(2026, 7, 14)
                assert closure.total_amount == Decimal("945.80")
                assert result["month"] == "2026-07"
                assert len(july_documents) == 1
                assert july_documents[0]["id"] == result["id"]
                assert september_documents == []
        finally:
            documents_router.extract_daily_cash_closure = original_extractor
            os.chdir(old_cwd)


def test_duplicate_cash_upload_returns_conflict_without_duplicating_revenue():
    with tempfile.TemporaryDirectory() as temp_dir:
        engine = create_engine(f"sqlite:///{temp_dir}/test_documents.db")
        Base.metadata.create_all(engine)
        old_cwd = os.getcwd()
        original_extractor = documents_router.extract_daily_cash_closure
        os.chdir(temp_dir)

        def fake_extract_daily_cash_closure(content: bytes, extension: str) -> dict:
            return {
                "date": dt.date(2026, 7, 14),
                "closure_number": "201",
                "total_amount": Decimal("945.80"),
                "cash_amount": Decimal("300.00"),
                "card_amount": Decimal("645.80"),
                "receipts_count": 42,
            }

        documents_router.extract_daily_cash_closure = fake_extract_daily_cash_closure

        try:
            with Session(engine) as session:
                upload = lambda: __import__("asyncio").run(
                    documents_router.upload_document(
                        file=UploadFile(file=BytesIO(b"same cash closure"), filename="closure.png"),
                        month="2026-09",
                        section="cash",
                        db=session,
                    )
                )

                upload()

                try:
                    upload()
                except HTTPException as exc:
                    assert exc.status_code == 409
                    assert exc.detail == (
                        "Questa chiusura cassa è già stata caricata "
                        "(14/07/2026 – chiusura n. 201 – 945,80 €)."
                    )
                else:
                    raise AssertionError("duplicate cash upload was accepted")

                documents = session.scalars(select(Document)).all()
                closures = session.scalars(select(DailyCashClosure)).all()
                revenue = monthly_pnl(session, dt.date(2026, 7, 1), dt.date(2026, 8, 1))

                assert len(documents) == 1
                assert len(closures) == 1
                assert closures[0].date == dt.date(2026, 7, 14)
                assert closures[0].closure_number == "201"
                assert revenue["revenue"] == Decimal("945.80")
        finally:
            documents_router.extract_daily_cash_closure = original_extractor
            os.chdir(old_cwd)
