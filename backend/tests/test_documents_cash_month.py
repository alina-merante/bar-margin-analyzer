import datetime as dt
import os
import sys
import tempfile
from decimal import Decimal
from io import BytesIO

from fastapi import HTTPException, UploadFile
from PIL import Image
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import (
    DailyCashClosure,
    Document,
    Invoice,
    InvoicePaymentLink,
    InvoiceStatus,
    Payment,
    Transaction,
)
from app.routers import documents as documents_router, finance as finance_router, imports as imports_router
from app.routers.analytics import monthly_pnl, overview


@pytest.fixture
def bank_document_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bank_document_dates.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def create_bank_history_document(db):
    document = Document(
        month="2026-07",
        original_filename="bank_test.csv",
        stored_filename="bank_test.csv",
        section="bank",
        document_type="CSV",
        category="Documento tabellare",
        result="Dati strutturati rilevati",
        file_url="/uploads/documents/bank_test.csv",
        preview_url="/uploads/documents/bank_test.csv",
        created_at=dt.datetime(2026, 9, 30, 12, 0),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def create_cash_history_document(db):
    document = Document(
        month="2026-07",
        original_filename="cash_test.pdf",
        stored_filename="cash_test.pdf",
        section="cash",
        document_type="PDF",
        category="Documento PDF",
        result="Testo rilevato",
        file_url="/uploads/documents/cash_test.pdf",
        preview_url="/uploads/documents/cash_test.pdf",
        created_at=dt.datetime(2026, 9, 30, 12, 0),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def test_bank_document_history_uses_single_transaction_date(bank_document_db):
    document = create_bank_history_document(bank_document_db)
    bank_document_db.add(
        Transaction(
            date=dt.date(2026, 7, 18),
            description="Commissioni bancarie luglio",
            amount=Decimal("-5.00"),
            counterparty="Banca Test",
            document_id=document.id,
        )
    )
    bank_document_db.commit()

    result = documents_router.list_documents(month="2026-07", db=bank_document_db)

    assert result[0]["effective_date"] == "2026-07-18"
    assert result[0]["effective_date_end"] == "2026-07-18"


def test_bank_document_history_uses_transaction_date_range(bank_document_db):
    document = create_bank_history_document(bank_document_db)
    bank_document_db.add_all(
        [
            Transaction(
                date=dt.date(2026, 7, 3),
                description="Primo movimento",
                amount=Decimal("-5.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
            Transaction(
                date=dt.date(2026, 7, 31),
                description="Ultimo movimento",
                amount=Decimal("-8.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
        ]
    )
    bank_document_db.commit()

    result = documents_router.list_documents(month="2026-07", db=bank_document_db)

    assert result[0]["effective_date"] == "2026-07-03"
    assert result[0]["effective_date_end"] == "2026-07-31"


def test_bank_document_history_with_same_transaction_date_stays_single_date(
    bank_document_db,
):
    document = create_bank_history_document(bank_document_db)
    bank_document_db.add_all(
        [
            Transaction(
                date=dt.date(2026, 7, 18),
                description="Primo movimento",
                amount=Decimal("-5.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
            Transaction(
                date=dt.date(2026, 7, 18),
                description="Secondo movimento",
                amount=Decimal("-8.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
        ]
    )
    bank_document_db.commit()

    result = documents_router.list_documents(month="2026-07", db=bank_document_db)

    assert result[0]["effective_date"] == "2026-07-18"
    assert result[0]["effective_date_end"] == "2026-07-18"


def test_legacy_bank_document_history_has_no_transaction_date(bank_document_db):
    document = create_bank_history_document(bank_document_db)

    result = documents_router.list_documents(month="2026-07", db=bank_document_db)

    assert result[0]["effective_date"] is None
    assert result[0]["effective_date_end"] is None
    assert result[0]["created_at"] == "2026-09-30T12:00:00+00:00"


def test_cash_document_history_uses_linked_closure_date(bank_document_db):
    document = create_cash_history_document(bank_document_db)
    bank_document_db.add(
        DailyCashClosure(
            date=dt.date(2026, 7, 14),
            total_amount=Decimal("500.00"),
            document_id=document.id,
        )
    )
    bank_document_db.commit()

    result = documents_router.list_documents(month="2026-07", db=bank_document_db)

    assert result[0]["effective_date"] == "2026-07-14"


def test_legacy_cash_document_history_keeps_created_at_fallback(bank_document_db):
    document = create_cash_history_document(bank_document_db)

    result = documents_router.list_documents(month="2026-07", db=bank_document_db)

    assert result[0]["effective_date"] is None
    assert result[0]["created_at"] == "2026-09-30T12:00:00+00:00"


def test_invoice_history_payload_includes_issue_date(bank_document_db):
    invoice = Invoice(
        supplier="Fornitore Test",
        invoice_number="FT-2026-07",
        issue_date=dt.date(2026, 7, 2),
        due_date=dt.date(2026, 7, 20),
        total=Decimal("100.00"),
        vat=Decimal("22.00"),
        status=InvoiceStatus.pending,
    )
    bank_document_db.add(invoice)
    bank_document_db.commit()

    result = finance_router.list_invoices(
        status=None,
        supplier=None,
        month="2026-07",
        db=bank_document_db,
    )

    assert result[0]["issue_date"] == "2026-07-02"
    assert result[0]["due_date"] == "2026-07-20"


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


def _fake_cash_data(content: bytes, extension: str) -> dict:
    return {
        "date": dt.date(2026, 7, 14),
        "closure_number": "301",
        "total_amount": Decimal("100.00"),
        "cash_amount": Decimal("40.00"),
        "card_amount": Decimal("60.00"),
        "receipts_count": 5,
    }


def _upload_cash_pdf(session):
    return __import__("asyncio").run(
        documents_router.upload_document(
            file=UploadFile(file=BytesIO(b"%PDF fake"), filename="closure.pdf"),
            month="2026-09",
            section="cash",
            db=session,
        )
    )


def _list_files(root):
    return sorted(
        os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs
    )


@pytest.fixture
def cash_upload_env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test_documents.db")
    Base.metadata.create_all(engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _fake_cash_data)
    monkeypatch.setattr(
        documents_router,
        "convert_from_bytes",
        lambda content, dpi: [Image.new("RGB", (50, 50)), Image.new("RGB", (50, 50))],
    )
    return engine


def test_cash_upload_failure_after_document_flush_rolls_back_and_removes_files(
    cash_upload_env, monkeypatch
):
    def failing_closure(**kwargs):
        raise RuntimeError("closure creation failed")

    monkeypatch.setattr(documents_router, "DailyCashClosure", failing_closure)

    with Session(cash_upload_env) as session:
        with pytest.raises(RuntimeError):
            _upload_cash_pdf(session)

        assert session.scalars(select(Document)).all() == []
        assert session.scalars(select(DailyCashClosure)).all() == []

    assert _list_files("uploads") == []


def test_cash_upload_commit_failure_rolls_back_and_removes_files(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        original_commit = session.commit

        def failing_commit():
            raise RuntimeError("commit failed")

        monkeypatch.setattr(session, "commit", failing_commit)

        with pytest.raises(RuntimeError):
            _upload_cash_pdf(session)

        monkeypatch.setattr(session, "commit", original_commit)
        assert session.scalars(select(Document)).all() == []
        assert session.scalars(select(DailyCashClosure)).all() == []

    assert _list_files("uploads") == []


def test_cash_upload_success_persists_document_closure_and_files_with_single_commit(
    cash_upload_env,
):
    with Session(cash_upload_env) as session:
        commits = []
        original_commit = session.commit
        session.commit = lambda: commits.append(1) or original_commit()

        payload = _upload_cash_pdf(session)

        documents = session.scalars(select(Document)).all()
        closures = session.scalars(select(DailyCashClosure)).all()

        assert len(commits) == 1
        assert len(documents) == 1 and len(closures) == 1
        assert closures[0].document_id == documents[0].id
        assert documents[0].month == "2026-07"
        assert payload["id"] == documents[0].id

    files = _list_files("uploads")
    assert len(files) == 3  # original + 2 preview pages


def test_cash_upload_refresh_failure_after_commit_keeps_records_and_files(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        commits = []
        original_commit = session.commit
        session.commit = lambda: commits.append(1) or original_commit()

        def failing_refresh(instance, *args, **kwargs):
            raise RuntimeError("refresh failed")

        monkeypatch.setattr(session, "refresh", failing_refresh)

        with pytest.raises(RuntimeError, match="refresh failed"):
            _upload_cash_pdf(session)

        documents = session.scalars(select(Document)).all()
        closures = session.scalars(select(DailyCashClosure)).all()

        assert len(commits) == 1
        assert len(documents) == 1 and len(closures) == 1
        assert closures[0].document_id == documents[0].id

    assert len(_list_files("uploads")) == 3


def test_cash_upload_without_closure_number_is_rejected_before_any_write(
    cash_upload_env, monkeypatch
):
    monkeypatch.setattr(
        documents_router,
        "extract_daily_cash_closure",
        lambda content, extension: {**_fake_cash_data(content, extension), "closure_number": None},
    )

    with Session(cash_upload_env) as session:
        commits = []
        flushes = []
        monkeypatch.setattr(session, "commit", lambda: commits.append(1))
        monkeypatch.setattr(session, "flush", lambda *a, **k: flushes.append(1))

        with pytest.raises(HTTPException) as exc_info:
            _upload_cash_pdf(session)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == (
            "Numero di chiusura non rilevato. "
            "Carica un'immagine o un PDF più leggibile."
        )
        assert commits == [] and flushes == []
        assert session.scalars(select(Document)).all() == []
        assert session.scalars(select(DailyCashClosure)).all() == []

    assert not os.path.exists("uploads") or _list_files("uploads") == []


from sqlalchemy.exc import IntegrityError


class _FakeDiag:
    def __init__(self, constraint_name):
        self.constraint_name = constraint_name


class _FakePgError(Exception):
    def __init__(self, constraint_name):
        super().__init__("integrity error")
        self.diag = _FakeDiag(constraint_name)


def _add_existing_closure(session):
    session.add(
        DailyCashClosure(
            date=dt.date(2026, 7, 14),
            closure_number="301",
            total_amount=Decimal("100.00"),
            cash_amount=Decimal("40.00"),
            card_amount=Decimal("60.00"),
        )
    )
    session.commit()


def test_db_rejects_duplicate_date_and_closure_number(cash_upload_env):
    with Session(cash_upload_env) as session:
        _add_existing_closure(session)
        session.add(
            DailyCashClosure(
                date=dt.date(2026, 7, 14),
                closure_number="301",
                total_amount=Decimal("100.00"),
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        assert len(session.scalars(select(DailyCashClosure)).all()) == 1


def test_db_allows_same_number_on_different_dates_and_different_numbers_same_date(
    cash_upload_env,
):
    with Session(cash_upload_env) as session:
        _add_existing_closure(session)
        session.add_all(
            [
                DailyCashClosure(
                    date=dt.date(2026, 7, 15), closure_number="301", total_amount=Decimal("1.00")
                ),
                DailyCashClosure(
                    date=dt.date(2026, 7, 14), closure_number="302", total_amount=Decimal("1.00")
                ),
            ]
        )
        session.commit()

        assert len(session.scalars(select(DailyCashClosure)).all()) == 3


def test_concurrent_duplicate_cash_upload_returns_409_and_cleans_up(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        _add_existing_closure(session)

        # Simulate the race: the pre-check does not see the competing closure,
        # so the real UNIQUE constraint rejects the insert at commit time.
        real_find = documents_router.find_existing_cash_closure
        calls = []

        def find_blind_first_time(db, extracted_data):
            calls.append(1)
            return None if len(calls) == 1 else real_find(db, extracted_data)

        monkeypatch.setattr(documents_router, "find_existing_cash_closure", find_blind_first_time)

        with pytest.raises(HTTPException) as exc_info:
            _upload_cash_pdf(session)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == (
            "Questa chiusura cassa è già stata caricata "
            "(14/07/2026 – chiusura n. 301 – 100,00 €)."
        )
        assert session.scalars(select(Document)).all() == []
        closures = session.scalars(select(DailyCashClosure)).all()
        assert len(closures) == 1 and closures[0].total_amount == Decimal("100.00")
        revenue = monthly_pnl(session, dt.date(2026, 7, 1), dt.date(2026, 8, 1))
        assert revenue["revenue"] == Decimal("100.00")

    assert _list_files("uploads") == []


def test_postgres_unique_violation_by_constraint_name_returns_409(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        def failing_commit():
            raise IntegrityError(
                "INSERT", {}, _FakePgError(documents_router.CASH_CLOSURE_UNIQUE_CONSTRAINT)
            )

        monkeypatch.setattr(session, "commit", failing_commit)

        with pytest.raises(HTTPException) as exc_info:
            _upload_cash_pdf(session)

        assert exc_info.value.status_code == 409
        assert session.scalars(select(Document)).all() == []

    assert _list_files("uploads") == []


def test_other_integrity_errors_are_not_reported_as_duplicate_closure(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        _add_existing_closure(session)
        real_find = documents_router.find_existing_cash_closure
        calls = []
        monkeypatch.setattr(
            documents_router,
            "find_existing_cash_closure",
            lambda db, data: None if not calls.append(1) and len(calls) == 1 else real_find(db, data),
        )

        def failing_commit():
            raise IntegrityError("INSERT", {}, _FakePgError("some_other_constraint"))

        monkeypatch.setattr(session, "commit", failing_commit)

        with pytest.raises(IntegrityError):
            _upload_cash_pdf(session)

        assert session.scalars(select(Document)).all() == []

    assert _list_files("uploads") == []


DATE_ERROR_DETAIL = (
    "Data della chiusura non rilevata o non valida. "
    "Carica un'immagine o un PDF più leggibile."
)


def _extract_with_text(monkeypatch, text):
    monkeypatch.setattr(documents_router, "extract_text_from_document", lambda c, e: text)
    return documents_router.extract_daily_cash_closure(b"x", "png")


def test_extractor_reads_four_digit_year_date(monkeypatch):
    data = _extract_with_text(monkeypatch, "NUM. CHIUSURA 201\nDEL GIORNO: 14/07/2026")
    assert data["date"] == dt.date(2026, 7, 14)


def test_extractor_reads_two_digit_year_date(monkeypatch):
    data = _extract_with_text(monkeypatch, "NUM. CHIUSURA 201\nDATA 14/07/26")
    assert data["date"] == dt.date(2026, 7, 14)


def test_extractor_returns_none_when_no_date_found(monkeypatch):
    data = _extract_with_text(monkeypatch, "NUM. CHIUSURA 201\nAMMONTARE GIORNO 10,00")
    assert data["date"] is None
    assert data["closure_number"] == "201"


def test_extractor_returns_none_for_impossible_date_without_raising(monkeypatch):
    data = _extract_with_text(monkeypatch, "NUM. CHIUSURA 201\nDEL GIORNO: 45/13/2026")
    assert data["date"] is None


def _assert_rejected_without_writes(session, monkeypatch, expected_detail):
    commits, flushes = [], []
    monkeypatch.setattr(session, "commit", lambda: commits.append(1))
    monkeypatch.setattr(session, "flush", lambda *a, **k: flushes.append(1))

    with pytest.raises(HTTPException) as exc_info:
        _upload_cash_pdf(session)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == expected_detail
    assert commits == [] and flushes == []
    assert session.scalars(select(Document)).all() == []
    assert session.scalars(select(DailyCashClosure)).all() == []
    assert not os.path.exists("uploads") or _list_files("uploads") == []


def test_cash_upload_with_missing_date_is_rejected_before_any_write(
    cash_upload_env, monkeypatch
):
    monkeypatch.setattr(
        documents_router,
        "extract_daily_cash_closure",
        lambda content, extension: {**_fake_cash_data(content, extension), "date": None},
    )

    with Session(cash_upload_env) as session:
        _assert_rejected_without_writes(session, monkeypatch, DATE_ERROR_DETAIL)


def test_cash_upload_with_impossible_ocr_date_returns_422_not_500(
    cash_upload_env, monkeypatch
):
    # Real extractor, only the OCR text is controlled.
    monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)
    monkeypatch.setattr(
        documents_router,
        "extract_text_from_document",
        lambda c, e: "NUM. CHIUSURA 301\nDEL GIORNO: 45/13/2026\nAMMONTARE GIORNO 10,00",
    )

    with Session(cash_upload_env) as session:
        _assert_rejected_without_writes(session, monkeypatch, DATE_ERROR_DETAIL)


_real_extractor = documents_router.extract_daily_cash_closure
