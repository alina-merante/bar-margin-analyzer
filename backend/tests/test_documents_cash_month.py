import datetime as dt
import os
import sys
import tempfile
from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app import config
from app.bar_context import resolve_active_bar_context
from app.models import (
    AuthSession,
    Bar,
    CashClosureIntake,
    DailyCashClosure,
    Document,
    Invoice,
    InvoicePaymentLink,
    InvoiceStatus,
    MembershipRole,
    Payment,
    Transaction,
    User,
    UserBarMembership,
)
from app.routers import (
    documents as documents_router,
    finance as finance_router,
    imports as imports_router,
)
from analytics_test_support import monthly_pnl, overview
from app.routers.auth import router as auth_router
from app.routers.bar_context import router as bar_context_router
from app.security import hash_password, token_hash
from app.settings import settings


ALLOWED_ORIGIN = "http://localhost:5173"
TEST_PASSWORD = "correct horse battery"
TEST_SESSION_TOKEN = "document-unit-test-session"


def _test_context(db):
    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == token_hash(TEST_SESSION_TOKEN))
    )
    if auth_session is None:
        bar = db.scalar(select(Bar).order_by(Bar.id))
        if bar is None:
            bar = Bar(name="Document test bar")
            db.add(bar)
            db.flush()
        user = User(email="document-unit@example.test", password_hash="test")
        db.add(user)
        db.flush()
        db.add(UserBarMembership(user_id=user.id, bar_id=bar.id, role=MembershipRole.owner))
        now = dt.datetime.now(dt.timezone.utc)
        auth_session = AuthSession(
            user_id=user.id, active_bar_id=bar.id, token_hash=token_hash(TEST_SESSION_TOKEN),
            csrf_token_hash=token_hash("test-csrf"), created_at=now,
            expires_at=now + dt.timedelta(days=1),
        )
        db.add(auth_session)
        db.flush()
    return resolve_active_bar_context(auth_session, db, auth_session.active_bar_id)


async def upload_for_test(*, db, **kwargs):
    context = _test_context(db)
    request = Request({
        "type": "http", "method": "POST", "path": "/documents/upload",
        "headers": [
            (b"cookie", f"{settings.cookie_name}={TEST_SESSION_TOKEN}".encode()),
            (b"x-expected-bar-id", str(context.bar.id).encode()),
        ],
    })
    return await documents_router.upload_document(
        request=request, _auth_session=context.auth_session, context=context, db=db, **kwargs
    )


@pytest.fixture
def bank_document_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bank_document_dates.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _test_context(session)
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def authenticated_bank_import_environment(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'bank-import.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_sessionmaker = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    api = FastAPI()
    api.include_router(auth_router)
    api.include_router(bar_context_router)
    api.include_router(imports_router.router)
    api.include_router(documents_router.router)

    def override_get_db():
        db = test_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    api.dependency_overrides[documents_router.get_db] = override_get_db

    def ensure_test_upload_dirs():
        (tmp_path / "uploads" / "documents").mkdir(parents=True, exist_ok=True)
        (tmp_path / "uploads" / "previews").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(documents_router, "ensure_upload_dirs", ensure_test_upload_dirs)
    monkeypatch.setattr(
        documents_router,
        "get_document_path",
        lambda filename: str(tmp_path / "uploads" / "documents" / filename),
    )
    monkeypatch.setattr(
        documents_router,
        "get_preview_path",
        lambda filename: str(tmp_path / "uploads" / "previews" / filename),
    )
    monkeypatch.setattr(
        documents_router,
        "get_document_url",
        lambda filename: f"/uploads/documents/{filename}",
    )
    monkeypatch.setattr(
        documents_router,
        "create_text_preview_image",
        lambda **_kwargs: "/uploads/previews/test.png",
    )
    monkeypatch.setattr(
        imports_router,
        "create_bank_document",
        documents_router.create_bank_document,
    )

    with test_sessionmaker() as db:
        bar = Bar(name="Test bar")
        user = User(
            email="bank-import@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        db.add_all([bar, user])
        db.flush()
        db.add(
            UserBarMembership(
                user_id=user.id,
                bar_id=bar.id,
                role=MembershipRole.owner,
            )
        )
        db.commit()
        bar_id = bar.id

    with TestClient(api) as client:
        pre_auth_csrf = client.get("/auth/csrf").json()["csrf_token"]
        login = client.post(
            "/auth/login",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "X-CSRF-Token": pre_auth_csrf,
            },
            json={
                "email": "bank-import@example.test",
                "password": TEST_PASSWORD,
            },
        )
        assert login.status_code == 200
        csrf_token = login.json()["csrf_token"]
        active_bar = client.put(
            "/auth/active-bar",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "X-CSRF-Token": csrf_token,
            },
            json={"bar_id": bar_id},
        )
        assert active_bar.status_code == 200
        client.headers["X-Expected-Bar-ID"] = str(bar_id)
        yield client, test_sessionmaker, csrf_token, bar_id
    engine.dispose()


def post_bank_csv(client, csrf_token, filename, content, data=None):
    return client.post(
        "/imports/bank-csv",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        files={"file": (filename, content, "text/csv")},
        data=data or {},
    )


def create_bank_history_document(db):
    document = Document(
        bar_id=_test_context(db).bar.id,
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
        bar_id=_test_context(db).bar.id,
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
            bar_id=document.bar_id,
            date=dt.date(2026, 7, 18),
            description="Commissioni bancarie luglio",
            amount=Decimal("-5.00"),
            counterparty="Banca Test",
            document_id=document.id,
        )
    )
    bank_document_db.commit()

    result = documents_router.list_documents(
        month="2026-07", context=_test_context(bank_document_db), db=bank_document_db
    )

    assert result[0]["effective_date"] == "2026-07-18"
    assert result[0]["effective_date_end"] == "2026-07-18"


def test_bank_document_history_uses_transaction_date_range(bank_document_db):
    document = create_bank_history_document(bank_document_db)
    bank_document_db.add_all(
        [
            Transaction(
                bar_id=document.bar_id,
                date=dt.date(2026, 7, 3),
                description="Primo movimento",
                amount=Decimal("-5.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
            Transaction(
                bar_id=document.bar_id,
                date=dt.date(2026, 7, 31),
                description="Ultimo movimento",
                amount=Decimal("-8.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
        ]
    )
    bank_document_db.commit()

    result = documents_router.list_documents(
        month="2026-07", context=_test_context(bank_document_db), db=bank_document_db
    )

    assert result[0]["effective_date"] == "2026-07-03"
    assert result[0]["effective_date_end"] == "2026-07-31"


def test_bank_document_history_with_same_transaction_date_stays_single_date(
    bank_document_db,
):
    document = create_bank_history_document(bank_document_db)
    bank_document_db.add_all(
        [
            Transaction(
                bar_id=document.bar_id,
                date=dt.date(2026, 7, 18),
                description="Primo movimento",
                amount=Decimal("-5.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
            Transaction(
                bar_id=document.bar_id,
                date=dt.date(2026, 7, 18),
                description="Secondo movimento",
                amount=Decimal("-8.00"),
                counterparty="Banca Test",
                document_id=document.id,
            ),
        ]
    )
    bank_document_db.commit()

    result = documents_router.list_documents(
        month="2026-07", context=_test_context(bank_document_db), db=bank_document_db
    )

    assert result[0]["effective_date"] == "2026-07-18"
    assert result[0]["effective_date_end"] == "2026-07-18"


def test_legacy_bank_document_history_has_no_transaction_date(bank_document_db):
    document = create_bank_history_document(bank_document_db)

    result = documents_router.list_documents(
        month="2026-07", context=_test_context(bank_document_db), db=bank_document_db
    )

    assert result[0]["effective_date"] is None
    assert result[0]["effective_date_end"] is None
    assert result[0]["created_at"] == "2026-09-30T12:00:00+00:00"


def test_cash_document_history_uses_linked_closure_date(bank_document_db):
    document = create_cash_history_document(bank_document_db)
    bank_document_db.add(
        DailyCashClosure(
            bar_id=document.bar_id,
            date=dt.date(2026, 7, 14),
            total_amount=Decimal("500.00"),
            document_id=document.id,
        )
    )
    bank_document_db.commit()

    result = documents_router.list_documents(
        month="2026-07", context=_test_context(bank_document_db), db=bank_document_db
    )

    assert result[0]["effective_date"] == "2026-07-14"


def test_legacy_cash_document_history_keeps_created_at_fallback(bank_document_db):
    document = create_cash_history_document(bank_document_db)

    result = documents_router.list_documents(
        month="2026-07", context=_test_context(bank_document_db), db=bank_document_db
    )

    assert result[0]["effective_date"] is None
    assert result[0]["created_at"] == "2026-09-30T12:00:00+00:00"


def test_invoice_history_payload_includes_issue_date(bank_document_db):
    invoice = Invoice(
        bar_id=_test_context(bank_document_db).bar.id,
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
        context=_test_context(bank_document_db),
        db=bank_document_db,
    )

    assert result[0]["issue_date"] == "2026-07-02"
    assert result[0]["due_date"] == "2026-07-20"


def test_dashboard_bank_reminder_uses_latest_transaction_date(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_bank_reminder.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        bar_id = _test_context(session).bar.id
        session.add_all(
            [
                Transaction(
                    bar_id=bar_id,
                    date=dt.date(2026, 7, 10),
                    description="Older bank movement",
                    amount=Decimal("-25.00"),
                    counterparty="Supplier A",
                ),
                Transaction(
                    bar_id=bar_id,
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


def test_uploading_old_bank_csv_does_not_advance_latest_transaction_date(
    authenticated_bank_import_environment,
):
    client, test_sessionmaker, csrf_token, bar_id = (
        authenticated_bank_import_environment
    )
    bank_csv = (
        b"date,description,amount\n"
        b"2026-07-10,Bank transfer - Supplier A,-25.00\n"
        b"2026-07-15,SEPA transfer - Supplier B,-200.00\n"
    )

    imported = post_bank_csv(
        client,
        csrf_token,
        "07_movimento_parziale_bevande_2026-07.csv",
        bank_csv,
        {"month": "2026-07"},
    )
    assert imported.status_code == 200
    assert imported.json() == {"imported_rows": 2, "skipped_rows": 0}

    with test_sessionmaker() as session:
        before_upload = overview(month="2026-07", db=session)
        response = client.post(
            "/documents/upload",
            headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
            files={"file": ("07_movimento_parziale_bevande_2026-07.csv", bank_csv)},
            data={"month": "2026-09", "section": "bank"},
        )
        assert response.status_code == 200, response.text
        document = response.json()
        after_upload = overview(month="2026-07", db=session)
        uploaded_at = dt.datetime.fromisoformat(document["created_at"])
        uploaded_document = session.get(Document, document["id"])
        tenant_document = session.scalar(
            select(Document).where(Document.bar_id == bar_id)
        )

        assert uploaded_at.date() == dt.datetime.now(dt.UTC).date()
        assert before_upload["latest_bank_transaction_date"] == "2026-07-15"
        assert after_upload["latest_bank_transaction_date"] == "2026-07-15"
        assert uploaded_document is not None
        assert uploaded_document.bar_id == bar_id
        assert tenant_document is not None


def test_bank_csv_document_month_uses_single_transaction_month_not_selected_month(
    authenticated_bank_import_environment,
):
    client, test_sessionmaker, csrf_token, bar_id = (
        authenticated_bank_import_environment
    )
    bank_csv = (
        b"date,description,amount\n"
        b"2026-07-03,SEPA transfer - Torrefazione Italiana S.p.A.,-420.00\n"
        b"2026-07-09,Bank transfer - Distribuzione Bevande S.R.L.,-310.00\n"
        b"2026-07-11,Payment to Energia Bar Luglio,-95.00\n"
        b"2026-07-12,Card payment - Pulizie Splendore,-120.00\n"
        b"2026-07-14,POS settlement - Incassi carte,2000.00\n"
    )

    first_import = post_bank_csv(
        client,
        csrf_token,
        "05_movimenti_bancari_2026-07.csv",
        bank_csv,
        {"month": "2026-09"},
    )
    assert first_import.status_code == 200
    assert first_import.json() == {"imported_rows": 5, "skipped_rows": 0}

    with test_sessionmaker() as session:
        document = session.scalar(select(Document))
        assert document is not None
        assert document.bar_id == bar_id
        duplicate_import = post_bank_csv(
            client,
            csrf_token,
            "05_movimenti_bancari_2026-07.csv",
            bank_csv,
            {"document_id": str(document.id)},
        )
        assert duplicate_import.status_code == 200
        assert duplicate_import.json() == {"imported_rows": 0, "skipped_rows": 5}

        transactions = session.scalars(
            select(Transaction).order_by(Transaction.id)
        ).all()
        assert len(transactions) == 5
        assert {transaction.document_id for transaction in transactions} == {
            document.id
        }
        assert transactions[0].counterparty == "Torrefazione Italiana S.p.A."
        assert transactions[0].amount == Decimal("-420.00")

        assert document.month == "2026-07"
        assert len(session.scalars(select(Transaction)).all()) == 5
        assert session.scalars(select(Payment)).all() == []
        assert session.scalars(select(InvoicePaymentLink)).all() == []

        pnl = monthly_pnl(
            session,
            dt.date(2026, 7, 1),
            dt.date(2026, 8, 1),
        )
        assert pnl["expenses"] == Decimal("0.00")


def test_atomic_bank_import_creates_linked_document_and_transaction(
    authenticated_bank_import_environment,
):
    client, test_sessionmaker, csrf_token, bar_id = (
        authenticated_bank_import_environment
    )
    content = b"date,description,amount\n2026-07-18,Commissioni bancarie luglio,-5.00\n"
    result = post_bank_csv(
        client,
        csrf_token,
        "atomic_bank.csv",
        content,
        {"month": "2026-07"},
    )

    assert result.status_code == 200
    assert result.json() == {"imported_rows": 1, "skipped_rows": 0}
    with test_sessionmaker() as db:
        document = db.scalar(select(Document))
        transaction = db.scalar(select(Transaction))

        assert document is not None
        assert document.bar_id == bar_id
        assert document.original_filename == "atomic_bank.csv"
        assert document.section == "bank"
        assert transaction is not None
        assert transaction.bar_id == bar_id
        assert transaction.date == dt.date(2026, 7, 18)
        assert transaction.description == "Commissioni bancarie luglio"
        assert transaction.amount == Decimal("-5.00")
        assert transaction.document_id == document.id


def test_invalid_atomic_bank_import_leaves_no_document_or_transactions(
    authenticated_bank_import_environment,
):
    client, test_sessionmaker, csrf_token, _bar_id = (
        authenticated_bank_import_environment
    )
    content = (
        b"date,description,amount\n"
        b"2026-07-18,Valid movement,-5.00\n"
        b"not-a-date,Invalid movement,-2.00\n"
    )

    response = post_bank_csv(
        client,
        csrf_token,
        "invalid_bank.csv",
        content,
        {"month": "2026-07"},
    )
    assert response.status_code == 400
    with test_sessionmaker() as db:
        assert db.scalars(select(Document)).all() == []
        assert db.scalars(select(Transaction)).all() == []


def test_atomic_bank_import_rolls_back_partial_transactions_and_document(
    authenticated_bank_import_environment, tmp_path, monkeypatch
):
    client, test_sessionmaker, csrf_token, _bar_id = (
        authenticated_bank_import_environment
    )
    content = (
        b"date,description,amount\n"
        b"2026-07-18,First movement,-5.00\n"
        b"2026-07-19,Second movement,-2.00\n"
    )
    original_import = imports_router.import_bank_transactions

    def fail_after_first_row(rows, db, document_id, bar_id):
        original_import(rows[:1], db, document_id, bar_id)
        raise RuntimeError("simulated bank import failure")

    monkeypatch.setattr(imports_router, "import_bank_transactions", fail_after_first_row)

    with pytest.raises(RuntimeError, match="simulated bank import failure"):
        post_bank_csv(
            client,
            csrf_token,
            "failed_bank.csv",
            content,
            {"month": "2026-07"},
        )

    with test_sessionmaker() as db:
        assert db.scalars(select(Document)).all() == []
        assert db.scalars(select(Transaction)).all() == []
    assert not list((tmp_path / "uploads" / "documents").glob("*"))
    assert not list((tmp_path / "uploads" / "previews").glob("*"))


def test_atomic_bank_import_keeps_transaction_deduplication(
    authenticated_bank_import_environment,
):
    client, test_sessionmaker, csrf_token, bar_id = (
        authenticated_bank_import_environment
    )
    content = b"date,description,amount\n2026-07-18,Commissioni bancarie luglio,-5.00\n"
    first_result = post_bank_csv(
        client,
        csrf_token,
        "first_bank.csv",
        content,
        {"month": "2026-07"},
    )
    assert first_result.status_code == 200
    assert first_result.json() == {"imported_rows": 1, "skipped_rows": 0}

    with test_sessionmaker() as db:
        original_transaction = db.scalar(select(Transaction))
        assert original_transaction is not None
        original_document_id = original_transaction.document_id
        assert original_transaction.bar_id == bar_id

    second_result = post_bank_csv(
        client,
        csrf_token,
        "reimport_bank.csv",
        content,
        {"document_id": str(original_document_id)},
    )
    assert second_result.status_code == 200
    assert second_result.json() == {"imported_rows": 0, "skipped_rows": 1}

    with test_sessionmaker() as db:
        transactions = db.scalars(select(Transaction)).all()
        assert len(transactions) == 1
        assert transactions[0].document_id == original_document_id


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
                    upload_for_test(
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
                "diagnostics": {
                    "anomalies": [],
                    "total_label": "explicit",
                    "fields": {
                        "date": {"status": "ok"},
                        "closure_number": {"status": "ok"},
                        "total_amount": {"status": "ok"},
                    },
                },
            }

        documents_router.extract_daily_cash_closure = fake_extract_daily_cash_closure

        try:
            with Session(engine) as session:
                result = __import__("asyncio").run(
                    upload_for_test(
                        file=UploadFile(file=BytesIO(b"cash closure"), filename="closure.png"),
                        month="2026-09",
                        section="cash",
                        db=session,
                    )
                )

                closure = session.scalar(select(DailyCashClosure))
                context = _test_context(session)
                july_documents = documents_router.list_documents("2026-07", context, session)
                september_documents = documents_router.list_documents("2026-09", context, session)

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
                "diagnostics": {
                    "anomalies": [],
                    "total_label": "explicit",
                    "fields": {
                        "date": {"status": "ok"},
                        "closure_number": {"status": "ok"},
                        "total_amount": {"status": "ok"},
                    },
                },
            }

        documents_router.extract_daily_cash_closure = fake_extract_daily_cash_closure

        try:
            with Session(engine) as session:
                upload = lambda: __import__("asyncio").run(
                    upload_for_test(
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
        "diagnostics": {
            "anomalies": [],
            "total_label": "explicit",
            "fields": {
                "date": {"status": "ok"},
                "closure_number": {"status": "ok"},
                "total_amount": {"status": "ok"},
            },
        },
    }


def _upload_cash_pdf(session):
    return __import__("asyncio").run(
        upload_for_test(
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
    monkeypatch.setattr(config, "UPLOAD_BASE_PATH", "uploads")
    monkeypatch.setattr(config, "UPLOAD_DOCUMENTS_DIR", "uploads/documents")
    monkeypatch.setattr(config, "UPLOAD_PREVIEWS_DIR", "uploads/previews")
    monkeypatch.setattr(config, "UPLOAD_INVOICES_DIR", "uploads/invoices")
    monkeypatch.setattr(documents_router, "UPLOAD_PREVIEWS_DIR", "uploads/previews")
    with Session(engine) as session:
        _test_context(session)
        session.commit()
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
    with Session(cash_upload_env) as session:
        original_add = session.add

        def failing_add(instance, *args, **kwargs):
            if isinstance(instance, DailyCashClosure):
                raise RuntimeError("closure creation failed")
            return original_add(instance, *args, **kwargs)

        monkeypatch.setattr(session, "add", failing_add)
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


def test_cash_upload_without_closure_number_is_staged_for_review(
    cash_upload_env, monkeypatch
):
    monkeypatch.setattr(
        documents_router,
        "extract_daily_cash_closure",
        lambda content, extension: {**_fake_cash_data(content, extension), "closure_number": None},
    )

    with Session(cash_upload_env) as session:
        result = _upload_cash_pdf(session)
        intake = session.scalars(select(CashClosureIntake)).one()
        assert result["status"] == "Da verificare"
        assert intake.status == "pending"
        assert intake.closure_number is None
        assert session.scalars(select(DailyCashClosure)).all() == []


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
            bar_id=_test_context(session).bar.id,
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
                bar_id=_test_context(session).bar.id,
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
                    bar_id=_test_context(session).bar.id,
                    date=dt.date(2026, 7, 15), closure_number="301", total_amount=Decimal("1.00")
                ),
                DailyCashClosure(
                    bar_id=_test_context(session).bar.id,
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

        def find_blind_first_time(db, extracted_data, bar_id):
            calls.append(1)
            return None if len(calls) == 1 else real_find(db, extracted_data, bar_id)

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
            lambda db, data, bar_id: (
                None if not calls.append(1) and len(calls) == 1
                else real_find(db, data, bar_id)
            ),
        )

        original_flush = session.flush

        def failing_flush(*args, **kwargs):
            if any(isinstance(item, DailyCashClosure) for item in session.new):
                raise IntegrityError("INSERT", {}, _FakePgError("some_other_constraint"))
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", failing_flush)

        with pytest.raises(IntegrityError):
            _upload_cash_pdf(session)

        assert session.scalars(select(Document)).all() == []

    assert _list_files("uploads") == []


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


def test_cash_upload_with_missing_date_is_staged_for_review(
    cash_upload_env, monkeypatch
):
    monkeypatch.setattr(
        documents_router,
        "extract_daily_cash_closure",
        lambda content, extension: {**_fake_cash_data(content, extension), "date": None},
    )

    with Session(cash_upload_env) as session:
        result = _upload_cash_pdf(session)
        intake = session.scalars(select(CashClosureIntake)).one()
        assert result["status"] == "Da verificare"
        assert intake.status == "pending"
        assert intake.date is None
        assert session.scalars(select(DailyCashClosure)).all() == []


def test_cash_upload_with_impossible_ocr_date_is_staged_for_review(
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
        result = _upload_cash_pdf(session)
        intake = session.scalars(select(CashClosureIntake)).one()
        assert result["status"] == "Da verificare"
        assert intake.status == "pending"
        assert intake.date is None
        assert session.scalars(select(DailyCashClosure)).all() == []


_real_extractor = documents_router.extract_daily_cash_closure


REAL_CLOSURE_201 = """NUM. CHIUSURA 201
DATA 14-07-26 23:45
CORRISP, GIORNALIERO 945,80
AMMONTARE GIORNO 945,80
DOCUM. DI VENDITA 118
PAGAM, ELETTRONICI 625,30
AMMONTARE 320,50
IMPONIBILE N2 320,50
"""

REAL_CLOSURE_202 = """NUM. CHIUSURA 202
DATA 15-07-26 23:45
CORRISP, GIORNALIERO 1.124,20
AMMONTARE GIORNO 1.124,20
DOCUM. DI VENDITA 139
PAGAM, ELETTRONICI 720,00
AMMONTARE 404,20
IMPONIBILE N2 404,20
"""


@pytest.mark.parametrize(
    "label, amount, expected",
    [
        ("PAGAM, ELETTRONICI", "625,30", Decimal("625.30")),
        ("PAGAM. ELETTRONICI", "720,00", Decimal("720.00")),
        ("PAGAM ELETTRONICI", "100,00", Decimal("100.00")),
    ],
)
def test_extractor_reads_electronic_payments_with_any_separator(
    monkeypatch, label, amount, expected
):
    data = _extract_with_text(monkeypatch, f"NUM. CHIUSURA 201\n{label} {amount}")
    assert data["card_amount"] == expected


@pytest.mark.parametrize(
    "label", ["CORRISP, GIORNALIERO", "CORRISP. GIORNALIERO", "CORRISP GIORNALIERO"]
)
def test_extractor_total_falls_back_to_daily_corrispettivo(monkeypatch, label):
    data = _extract_with_text(monkeypatch, f"NUM. CHIUSURA 201\n{label} 1.124,20")
    assert data["total_amount"] == Decimal("1124.20")


def test_extractor_keeps_explicit_zero_card_amount(monkeypatch):
    data = _extract_with_text(monkeypatch, "NUM. CHIUSURA 201\nPAGAM, ELETTRONICI 0,00")
    assert data["card_amount"] == Decimal("0.00")
    assert data["cash_amount"] is None


def test_extractor_keeps_explicit_zero_cash_amount(monkeypatch):
    data = _extract_with_text(
        monkeypatch, "NUM. CHIUSURA 201\nAMMONTARE GIORNO 10,00\nAMMONTARE 0,00"
    )
    assert data["cash_amount"] == Decimal("0.00")
    assert data["card_amount"] is None


def test_extractor_missing_amounts_are_none_and_not_zero(monkeypatch):
    data = _extract_with_text(monkeypatch, "NUM. CHIUSURA 201")
    assert data["total_amount"] is None
    assert data["cash_amount"] is None
    assert data["card_amount"] is None
    assert data["receipts_count"] is None


@pytest.mark.parametrize(
    "text, total, cash, card, receipts",
    [
        (REAL_CLOSURE_201, "945.80", "320.50", "625.30", 118),
        (REAL_CLOSURE_202, "1124.20", "404.20", "720.00", 139),
    ],
)
def test_extractor_reads_real_closure_documents(
    monkeypatch, text, total, cash, card, receipts
):
    data = _extract_with_text(monkeypatch, text)
    assert data["total_amount"] == Decimal(total)
    assert data["cash_amount"] == Decimal(cash)
    assert data["card_amount"] == Decimal(card)
    assert data["receipts_count"] == receipts





def _upload_with_ocr_text(session, monkeypatch, text):
    monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)
    monkeypatch.setattr(documents_router, "extract_text_from_document", lambda c, e: text)
    return _upload_cash_pdf(session)


def test_cash_upload_with_missing_total_is_staged_for_review(
    cash_upload_env, monkeypatch
):
    monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)
    monkeypatch.setattr(
        documents_router,
        "extract_text_from_document",
        lambda c, e: "NUM. CHIUSURA 301\nDATA 14-07-26\nAMMONTARE 40,00",
    )

    with Session(cash_upload_env) as session:
        result = _upload_cash_pdf(session)
        intake = session.scalars(select(CashClosureIntake)).one()
        assert result["status"] == "Da verificare"
        assert intake.status == "pending"
        assert intake.total_amount is None
        assert session.scalars(select(DailyCashClosure)).all() == []


def test_cash_upload_missing_total_still_checks_known_duplicate_key(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        _add_existing_closure(session)
        monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)
        monkeypatch.setattr(
            documents_router,
            "extract_text_from_document",
            lambda c, e: "NUM. CHIUSURA 301\nDATA 14-07-26",
        )
        with pytest.raises(HTTPException) as exc_info:
            _upload_cash_pdf(session)

    assert exc_info.value.status_code == 409


def test_cash_upload_with_explicit_zero_total_is_saved_as_zero(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        _upload_with_ocr_text(
            session,
            monkeypatch,
            "NUM. CHIUSURA 302\nDATA 14-07-26\nAMMONTARE GIORNO 0,00",
        )
        closure = session.scalars(select(DailyCashClosure)).one()

    assert closure.total_amount == Decimal("0.00")
    assert closure.cash_amount is None
    assert closure.card_amount is None


def test_cash_upload_total_from_corrisp_fallback_with_missing_cash_and_card(
    cash_upload_env, monkeypatch
):
    with Session(cash_upload_env) as session:
        _upload_with_ocr_text(
            session,
            monkeypatch,
            "NUM. CHIUSURA 303\nDATA 14-07-26\nCORRISP, GIORNALIERO 1.124,20",
        )
        closure = session.scalars(select(DailyCashClosure)).one()

    assert closure.total_amount == Decimal("1124.20")
    assert closure.cash_amount is None
    assert closure.card_amount is None


NO_CASH_WARNING = "Contanti non rilevati: verifica l'importo sul documento originale."
NO_CARD_WARNING = (
    "Pagamenti elettronici non rilevati: verifica l'importo sul documento originale."
)
MISMATCH_WARNING = (
    "Il totale non coincide con la somma di contanti e pagamenti elettronici. "
    "Verifica eventuali altri metodi di pagamento."
)


def _upload_with_amounts(cash_upload_env, monkeypatch, amounts, closure_number="401"):
    lines = [f"NUM. CHIUSURA {closure_number}", "DATA 14-07-26"]
    lines += amounts
    payload = _upload_with_ocr_text_session(cash_upload_env, monkeypatch, "\n".join(lines))
    with Session(cash_upload_env) as session:
        closure = session.scalar(select(DailyCashClosure))
        if closure is None:
            return payload, None
        return payload, (closure.total_amount, closure.cash_amount, closure.card_amount)


def _upload_with_ocr_text_session(engine, monkeypatch, text):
    with Session(engine) as session:
        return _upload_with_ocr_text(session, monkeypatch, text)


def test_warning_when_cash_missing(cash_upload_env, monkeypatch):
    payload, saved = _upload_with_amounts(
        cash_upload_env,
        monkeypatch,
        ["AMMONTARE GIORNO 100,00", "PAGAM, ELETTRONICI 100,00"],
    )
    assert payload["warnings"] == [NO_CASH_WARNING]
    assert saved == (Decimal("100.00"), None, Decimal("100.00"))


def test_warning_when_card_missing(cash_upload_env, monkeypatch):
    payload, saved = _upload_with_amounts(
        cash_upload_env, monkeypatch, ["AMMONTARE GIORNO 100,00", "AMMONTARE 100,00"]
    )
    assert payload["warnings"] == [NO_CARD_WARNING]
    assert saved == (Decimal("100.00"), Decimal("100.00"), None)


def test_two_warnings_when_cash_and_card_missing_and_no_mismatch_warning(
    cash_upload_env, monkeypatch
):
    payload, saved = _upload_with_amounts(
        cash_upload_env, monkeypatch, ["AMMONTARE GIORNO 100,00"]
    )
    assert payload["warnings"] == [NO_CASH_WARNING, NO_CARD_WARNING]
    assert saved == (Decimal("100.00"), None, None)


def test_explicit_zero_amounts_do_not_warn_as_not_detected(cash_upload_env, monkeypatch):
    payload, saved = _upload_with_amounts(
        cash_upload_env,
        monkeypatch,
        ["AMMONTARE GIORNO 100,00", "PAGAM, ELETTRONICI 100,00", "AMMONTARE 0,00"],
    )
    assert payload["warnings"] == []
    assert saved == (Decimal("100.00"), Decimal("0.00"), Decimal("100.00"))


def test_warning_when_total_differs_from_payments_sum(cash_upload_env, monkeypatch):
    payload, saved = _upload_with_amounts(
        cash_upload_env,
        monkeypatch,
        ["AMMONTARE GIORNO 100,00", "PAGAM, ELETTRONICI 60,00", "AMMONTARE 30,00"],
    )
    assert payload["warnings"] == [MISMATCH_WARNING]
    assert payload["cash_closure_classification"] == "SAVE_FOR_REVIEW"
    assert saved is None


def test_no_warning_when_total_matches_payments_sum(cash_upload_env, monkeypatch):
    payload, _ = _upload_with_amounts(
        cash_upload_env,
        monkeypatch,
        ["AMMONTARE GIORNO 100,00", "PAGAM, ELETTRONICI 60,00", "AMMONTARE 40,00"],
    )
    assert payload["warnings"] == []


def test_non_cash_upload_response_has_no_warnings_key(cash_upload_env):
    with Session(cash_upload_env) as session:
        payload = __import__("asyncio").run(
            upload_for_test(
                file=UploadFile(file=BytesIO(b"hello"), filename="note.txt"),
                month="2026-09",
                section="other",
                db=session,
            )
        )
    assert "warnings" not in payload


# --- Affidabilità OCR: date, numero chiusura, importi, duplicati ---


@pytest.mark.parametrize(
    "date_text",
    ["DATA 112/07/2026", "DATA 14/07/202", "DATA 14/07/20266", "DATA 14/13/2026"],
)
def test_extractor_rejects_malformed_dates(monkeypatch, date_text):
    data = _extract_with_text(monkeypatch, f"NUM. CHIUSURA 201\n{date_text}")
    assert data["date"] is None


def test_extractor_conflicting_unlabeled_dates_are_ambiguous(monkeypatch):
    data = _extract_with_text(monkeypatch, "STAMPA 01/01/26\nNUM. CHIUSURA 201\n14/07/26 23:45")
    assert data["date"] is None


def test_extractor_prefers_single_labeled_date_over_other_dates(monkeypatch):
    data = _extract_with_text(monkeypatch, "STAMPA 01/01/26\nNUM. CHIUSURA 201\nDATA 14-07-26")
    assert data["date"] == dt.date(2026, 7, 14)


def test_extractor_repeated_identical_date_is_not_ambiguous(monkeypatch):
    data = _extract_with_text(monkeypatch, "DATA 14-07-26\nNUM. CHIUSURA 201\nDEL GIORNO: 14/07/2026")
    assert data["date"] == dt.date(2026, 7, 14)


@pytest.mark.parametrize("number_text", ["2O1", "20l", "201A"])
def test_extractor_does_not_truncate_closure_number_with_ocr_letters(monkeypatch, number_text):
    data = _extract_with_text(monkeypatch, f"NUM. CHIUSURA {number_text}\nDATA 14-07-26")
    assert data["closure_number"] is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1.250,50", Decimal("1250.50")),
        ("1250,50", Decimal("1250.50")),
        ("0,50", Decimal("0.50")),
        ("12.345,00", Decimal("12345.00")),
    ],
)
def test_extractor_reads_italian_amounts_exactly(monkeypatch, text, expected):
    data = _extract_with_text(monkeypatch, f"AMMONTARE GIORNO {text}")
    assert data["total_amount"] == expected


@pytest.mark.parametrize(
    "text",
    ["945,805", "945,8", "1.25,50", "1.2504,50", "1250.50", "1 250,50", "-10,00", "945,8O", "n/d"],
)
def test_extractor_rejects_unreadable_or_ambiguous_amounts(monkeypatch, text):
    data = _extract_with_text(monkeypatch, f"AMMONTARE GIORNO {text}")
    assert data["total_amount"] is None


def test_cash_upload_with_ambiguous_date_is_staged_for_review(cash_upload_env, monkeypatch):
    monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)
    monkeypatch.setattr(
        documents_router,
        "extract_text_from_document",
        lambda c, e: "01/01/26\nNUM. CHIUSURA 301\n14/07/26\nAMMONTARE GIORNO 10,00",
    )

    with Session(cash_upload_env) as session:
        result = _upload_cash_pdf(session)
        intake = session.scalars(select(CashClosureIntake)).one()
        assert result["status"] == "Da verificare"
        assert intake.date is None
        assert session.scalars(select(DailyCashClosure)).all() == []


def test_cash_upload_with_unreadable_total_is_staged(cash_upload_env, monkeypatch):
    monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)
    monkeypatch.setattr(
        documents_router,
        "extract_text_from_document",
        lambda c, e: "NUM. CHIUSURA 301\nDATA 14-07-26\nAMMONTARE GIORNO 945,805",
    )

    with Session(cash_upload_env) as session:
        result = _upload_cash_pdf(session)
        intake = session.scalars(select(CashClosureIntake)).one()
        assert result["status"] == "Da verificare"
        assert intake.total_amount is None
        assert intake.status == "pending"
        assert session.scalars(select(DailyCashClosure)).all() == []


def test_two_closures_same_day_are_saved_and_exact_duplicate_is_rejected(cash_upload_env, monkeypatch):
    monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)

    def upload(number):
        text = f"NUM. CHIUSURA {number}\nDATA 14-07-26\nAMMONTARE GIORNO 100,00"
        with Session(cash_upload_env) as session:
            monkeypatch.setattr(documents_router, "extract_daily_cash_closure", _real_extractor)
            monkeypatch.setattr(
                documents_router,
                "extract_text_from_document",
                lambda content, extension: content.decode("utf-8"),
            )
            return __import__("asyncio").run(
                upload_for_test(
                    file=UploadFile(file=BytesIO(text.encode("utf-8")), filename="closure.txt"),
                    month="2026-09",
                    section="cash",
                    db=session,
                )
            )

    upload("501")
    upload("502")
    with pytest.raises(HTTPException) as exc_info:
        upload("501")

    assert exc_info.value.status_code == 409
    with Session(cash_upload_env) as session:
        closures = session.scalars(select(DailyCashClosure)).all()
        assert sorted(c.closure_number for c in closures) == ["501", "502"]
        assert len(session.scalars(select(Document)).all()) == 2
