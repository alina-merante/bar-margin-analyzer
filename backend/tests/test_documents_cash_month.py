import datetime as dt
import os
import sys
import tempfile
from decimal import Decimal
from io import BytesIO

from fastapi import HTTPException, UploadFile
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import DailyCashClosure, Document, InvoicePaymentLink, Payment, Transaction
from app.routers import documents as documents_router, imports as imports_router
from app.routers.analytics import monthly_pnl, overview



def test_dashboard_bank_reminder_uses_latest_transaction_date(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_bank_reminder.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Transaction(
                    date=dt.date(2026, 7, 10),
                    description="Older bank movement",
                    amount=Decimal("-25.00"),
                    counterparty="Supplier A",
                ),
                Transaction(
                    date=dt.date(2026, 7, 15),
                    description="Latest bank movement",
                    amount=Decimal("-200.00"),
                    counterparty="Supplier B",
                ),
            ]
        )
        session.commit()

        result = overview(month="2026-07", db=session)

    engine.dispose()
    assert result["latest_bank_transaction_date"] == "2026-07-15"


def test_uploading_old_bank_csv_does_not_advance_latest_transaction_date(tmp_path):
    bank_csv = (
        b"date,description,amount\n"
        b"2026-07-10,Bank transfer - Supplier A,-25.00\n"
        b"2026-07-15,SEPA transfer - Supplier B,-200.00\n"
    )

    with tempfile.TemporaryDirectory(dir=tmp_path) as temp_dir:
        engine = create_engine(f"sqlite:///{temp_dir}/test_bank_upload_reminder.db")
        Base.metadata.create_all(engine)
        old_cwd = os.getcwd()
        os.chdir(temp_dir)

        try:
            with Session(engine) as session:
                imports_router.import_bank_csv(
                    UploadFile(
                        file=BytesIO(bank_csv),
                        filename="07_movimento_parziale_bevande_2026-07.csv",
                    ),
                    session,
                )
                before_upload = overview(month="2026-07", db=session)
                document = __import__("asyncio").run(
                    documents_router.upload_document(
                        file=UploadFile(
                            file=BytesIO(bank_csv),
                            filename="07_movimento_parziale_bevande_2026-07.csv",
                        ),
                        month="2026-09",
                        section="bank",
                        db=session,
                    )
                )
                after_upload = overview(month="2026-07", db=session)
                uploaded_at = dt.datetime.fromisoformat(document["created_at"])

                assert uploaded_at.date() == dt.datetime.now(dt.UTC).date()
                assert before_upload["latest_bank_transaction_date"] == "2026-07-15"
                assert after_upload["latest_bank_transaction_date"] == "2026-07-15"
        finally:
            os.chdir(old_cwd)
            engine.dispose()


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

                first_import = imports_router.import_bank_csv(
                    UploadFile(
                        file=BytesIO(bank_csv),
                        filename="05_movimenti_bancari_2026-07.csv",
                    ),
                    document_id=document["id"],
                    db=session,
                )
                duplicate_import = imports_router.import_bank_csv(
                    UploadFile(
                        file=BytesIO(bank_csv),
                        filename="05_movimenti_bancari_2026-07.csv",
                    ),
                    document_id=document["id"],
                    db=session,
                )

                assert first_import == {"imported_rows": 5, "skipped_rows": 0}
                assert duplicate_import == {"imported_rows": 0, "skipped_rows": 5}

                transactions = session.scalars(
                    select(Transaction).order_by(Transaction.id)
                ).all()
                assert len(transactions) == 5
                assert {transaction.document_id for transaction in transactions} == {
                    document["id"]
                }
                assert transactions[0].counterparty == "Torrefazione Italiana S.p.A."
                assert transactions[0].amount == Decimal("-420.00")

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


def test_atomic_bank_import_creates_linked_document_and_transaction(bank_document_db, tmp_path):
    content = b"date,description,amount\n2026-07-18,Commissioni bancarie luglio,-5.00\n"
    old_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        result = imports_router.import_bank_csv(
            UploadFile(file=BytesIO(content), filename="atomic_bank.csv"),
            db=bank_document_db,
            month="2026-07",
        )

        document = bank_document_db.scalar(select(Document))
        transaction = bank_document_db.scalar(select(Transaction))

        assert result == {"imported_rows": 1, "skipped_rows": 0}
        assert document is not None
        assert document.original_filename == "atomic_bank.csv"
        assert document.section == "bank"
        assert transaction is not None
        assert transaction.date == dt.date(2026, 7, 18)
        assert transaction.description == "Commissioni bancarie luglio"
        assert transaction.amount == Decimal("-5.00")
        assert transaction.document_id == document.id
    finally:
        os.chdir(old_cwd)


def test_invalid_atomic_bank_import_leaves_no_document_or_transactions(
    bank_document_db, tmp_path
):
    content = (
        b"date,description,amount\n"
        b"2026-07-18,Valid movement,-5.00\n"
        b"not-a-date,Invalid movement,-2.00\n"
    )
    old_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        with pytest.raises(HTTPException):
            imports_router.import_bank_csv(
                UploadFile(file=BytesIO(content), filename="invalid_bank.csv"),
                db=bank_document_db,
                month="2026-07",
            )

        assert bank_document_db.scalars(select(Document)).all() == []
        assert bank_document_db.scalars(select(Transaction)).all() == []
    finally:
        os.chdir(old_cwd)


def test_atomic_bank_import_rolls_back_partial_transactions_and_document(
    bank_document_db, tmp_path, monkeypatch
):
    content = (
        b"date,description,amount\n"
        b"2026-07-18,First movement,-5.00\n"
        b"2026-07-19,Second movement,-2.00\n"
    )
    original_import = imports_router.import_bank_transactions

    def fail_after_first_row(rows, db, document_id):
        original_import(rows[:1], db, document_id)
        raise RuntimeError("simulated bank import failure")

    monkeypatch.setattr(imports_router, "import_bank_transactions", fail_after_first_row)
    old_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        with pytest.raises(RuntimeError, match="simulated bank import failure"):
            imports_router.import_bank_csv(
                UploadFile(file=BytesIO(content), filename="failed_bank.csv"),
                db=bank_document_db,
                month="2026-07",
            )

        assert bank_document_db.scalars(select(Document)).all() == []
        assert bank_document_db.scalars(select(Transaction)).all() == []
        assert not list((tmp_path / "uploads" / "documents").glob("*"))
        assert not list((tmp_path / "uploads" / "previews").glob("*"))
    finally:
        os.chdir(old_cwd)


def test_atomic_bank_import_keeps_transaction_deduplication(bank_document_db, tmp_path):
    content = b"date,description,amount\n2026-07-18,Commissioni bancarie luglio,-5.00\n"
    old_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        first_result = imports_router.import_bank_csv(
            UploadFile(file=BytesIO(content), filename="first_bank.csv"),
            db=bank_document_db,
            month="2026-07",
        )
        original_transaction = bank_document_db.scalar(select(Transaction))
        original_document_id = original_transaction.document_id

        second_result = imports_router.import_bank_csv(
            UploadFile(file=BytesIO(content), filename="reimport_bank.csv"),
            db=bank_document_db,
            month="2026-07",
        )

        transactions = bank_document_db.scalars(select(Transaction)).all()
        assert first_result == {"imported_rows": 1, "skipped_rows": 0}
        assert second_result == {"imported_rows": 0, "skipped_rows": 1}
        assert len(transactions) == 1
        assert transactions[0].document_id == original_document_id
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
