import asyncio
import datetime as dt
import json
from io import BytesIO
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import (
    Invoice,
    InvoicePaymentLink,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    Transaction,
)
from app.routers.analytics import expenses_by_category, invoices_summary, monthly_pnl, overview
from app.routers import finance as finance_router
from app.routers.finance import (
    LinkPaymentPayload,
    PaymentCreate,
    ReconcileTransactionPayload,
    create_payment,
    create_invoice,
    delete_invoice,
    get_transaction_candidates,
    link_payment,
    list_invoices,
    reconcile_invoice_transaction,
)


@pytest.fixture

def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reconciliation.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_invoice(db, total="420.00", status=InvoiceStatus.pending):
    invoice = Invoice(
        supplier="TORREFAZIONE ITALIANA S.p.A.",
        invoice_number="TC-2026-071",
        issue_date=dt.date(2026, 7, 2),
        due_date=dt.date(2026, 7, 10),
        total=Decimal(total),
        vat=Decimal("60.00"),
        status=status,
    )
    db.add(invoice)
    db.commit()
    return invoice


def add_transaction(db, amount="-420.00", date=dt.date(2026, 7, 3), description=None):
    transaction = Transaction(
        date=date,
        description=description or "SEPA transfer - Torrefazione Italiana S.p.A.",
        amount=Decimal(amount),
        counterparty="Torrefazione Italiana S.p.A.",
    )
    db.add(transaction)
    db.commit()
    return transaction


def reconcile(db, invoice, transaction):
    return reconcile_invoice_transaction(
        invoice.id,
        ReconcileTransactionPayload(transaction_id=transaction.id),
        db,
    )


def reupload_invoice(db, tmp_path, monkeypatch, *, total="525.00"):
    extracted = {
        "supplier": "TORREFAZIONE ITALIANA S.p.A.",
        "invoice_number": "TC-2026-071",
        "issue_date": dt.date(2026, 8, 1),
        "due_date": dt.date(2026, 8, 31),
        "total": Decimal(total),
        "vat": Decimal("75.00"),
    }
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(finance_router, "extract_invoice_from_xml", lambda _: {})
    monkeypatch.setattr(finance_router, "normalize_extracted_invoice", lambda _: extracted)
    upload = UploadFile(filename="invoice.xml", file=BytesIO(b"<invoice />"))
    return asyncio.run(finance_router.extract_invoice(upload, db))


def extract_invoice_with_data(db, tmp_path, monkeypatch, extracted):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(finance_router, "extract_invoice_from_xml", lambda _: extracted)
    upload = UploadFile(filename="invoice.xml", file=BytesIO(b"<invoice />"))
    return asyncio.run(finance_router.extract_invoice(upload, db))


async def post_json(app, path, payload):
    body = json.dumps(payload).encode()
    request_sent = False
    messages = []

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
            "client": ("testclient", 123),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    response_start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return response_start["status"], json.loads(response_body)


def test_exact_transaction_is_candidate_without_database_changes(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)

    result = get_transaction_candidates(invoice.id, db)

    assert result["linked_amount"] == 0.0
    assert result["remaining_amount"] == 420.0
    assert [item["id"] for item in result["candidates"]] == [transaction.id]
    assert result["candidates"][0]["amount"] == -420.0
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    assert invoice.status == InvoiceStatus.pending


def test_create_invoice_api_requires_issue_date_and_ignores_paid_status(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'create-invoice.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    api = FastAPI()
    api.include_router(finance_router.router)

    def override_get_db():
        with Session(engine) as session:
            yield session

    api.dependency_overrides[get_db] = override_get_db
    payload_without_issue_date = {
        "supplier": "Supplier API",
        "invoice_number": "INV-API-1",
        "due_date": "2026-09-15",
        "total": "120.00",
        "vat": "20.00",
        "status": "paid",
    }

    try:
        status_code, _ = asyncio.run(post_json(api, "/invoices", payload_without_issue_date))
        assert status_code == 422
        with Session(engine) as session:
            assert session.scalars(select(Invoice)).all() == []

        payload_with_issue_date = {
            **payload_without_issue_date,
            "issue_date": "2026-08-30",
        }
        status_code, result = asyncio.run(post_json(api, "/invoices", payload_with_issue_date))
        assert status_code == 200
        assert result["status"] == InvoiceStatus.pending.value
        assert result["issue_date"] == "2026-08-30"
        assert result["linked_amount"] == 0.0
        assert result["remaining_amount"] == 120.0
        with Session(engine) as session:
            invoice = session.scalar(select(Invoice))
            assert invoice.status == InvoiceStatus.pending
            assert session.scalars(select(InvoicePaymentLink)).all() == []
    finally:
        api.dependency_overrides.clear()
        engine.dispose()


def test_candidate_search_excludes_positive_used_and_over_residual_transactions(db):
    invoice = add_invoice(db)
    positive = add_transaction(db, amount="100.00", description="Incoming transfer")
    over_residual = add_transaction(db, amount="-500.00", description="Supplier payment")
    used = add_transaction(db, amount="-100.00", description="Already used")
    payment = Payment(
        date=used.date,
        amount=Decimal("100.00"),
        method=PaymentMethod.bank_transfer,
        counterparty=used.counterparty,
        reference=used.description,
        transaction_id=used.id,
    )
    db.add(payment)
    db.commit()

    candidates = get_transaction_candidates(invoice.id, db)["candidates"]

    assert [item["id"] for item in candidates] == []
    assert db.get(Transaction, positive.id) is not None
    assert db.get(Transaction, over_residual.id) is not None


def test_reconcile_full_payment_links_transaction_and_marks_invoice_paid(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)

    result = reconcile(db, invoice, transaction)

    payment = db.scalar(select(Payment))
    link = db.scalar(select(InvoicePaymentLink))
    assert payment.amount == Decimal("420.00")
    assert payment.transaction_id == transaction.id
    assert payment.date == transaction.date
    assert payment.method == PaymentMethod.bank_transfer
    assert link.invoice_id == invoice.id
    assert link.payment_id == payment.id
    assert result["invoice_status"] == "paid"
    assert result["linked_amount"] == 420.0
    assert result["remaining_amount"] == 0.0
    assert invoice.status == InvoiceStatus.paid
    summary = invoices_summary(db)
    assert summary["paid_invoices"] == 1
    assert summary["paid_amount"] == 420.0


@pytest.mark.parametrize(
    ("description", "expected_method"),
    [
        ("SEPA transfer - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Bank transfer - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Transfer - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Bonifico - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
        ("Card payment - Torrefazione Italiana S.p.A.", PaymentMethod.card),
        ("Card - Torrefazione Italiana S.p.A.", PaymentMethod.card),
        ("Pagamento con carta - Torrefazione Italiana S.p.A.", PaymentMethod.card),
        ("Outgoing debit - Torrefazione Italiana S.p.A.", PaymentMethod.bank_transfer),
    ],
)
def test_reconciliation_classifies_payment_method_from_transaction(
    db, description, expected_method
):
    invoice = add_invoice(db)
    transaction = add_transaction(db, description=description)

    reconcile(db, invoice, transaction)

    payment = db.scalar(select(Payment))
    assert payment.method == expected_method


def test_unlinked_invoice_can_be_deleted(db):
    invoice = add_invoice(db)

    result = delete_invoice(invoice.id, db)

    assert result == {"ok": True, "deleted_invoice_id": invoice.id}
    assert db.get(Invoice, invoice.id) is None
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []


@pytest.mark.parametrize("payment_amount", ["420.00", "200.00"])
def test_invoice_with_reconciled_payment_cannot_be_deleted(db, payment_amount):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount=f"-{payment_amount}")
    reconcile(db, invoice, transaction)
    original_invoice_status = invoice.status
    original_transaction = (transaction.date, transaction.description, transaction.amount)
    payment = db.scalar(select(Payment))
    link = db.scalar(select(InvoicePaymentLink))

    with pytest.raises(HTTPException) as error:
        delete_invoice(invoice.id, db)

    assert error.value.status_code == 409
    assert error.value.detail == "La fattura non può essere eliminata perché contiene pagamenti riconciliati."
    db.expire_all()
    assert db.get(Invoice, invoice.id).status == original_invoice_status
    assert db.get(Payment, payment.id).transaction_id == transaction.id
    assert db.get(InvoicePaymentLink, link.id).invoice_id == invoice.id
    current_transaction = db.get(Transaction, transaction.id)
    assert (current_transaction.date, current_transaction.description, current_transaction.amount) == original_transaction


def test_reconcile_partial_payment_keeps_invoice_pending_and_exposes_residual(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="-200.00")

    result = reconcile(db, invoice, transaction)
    invoice_response = list_invoices(status=None, supplier=None, month=None, db=db)[0]

    assert result["invoice_status"] == "pending"
    assert invoice_response["linked_amount"] == 200.0
    assert invoice_response["remaining_amount"] == 220.0
    assert invoice.status == InvoiceStatus.pending
    summary = invoices_summary(db)
    assert summary["paid_invoices"] == 0
    assert summary["paid_amount"] == 0.0


def test_invoice_two_reconciled_payments_flow_updates_dashboard_pnl_once(db):
    taxable_amount = Decimal("409.84")
    vat_amount = Decimal("90.16")
    invoice = add_invoice(db, total="500.00")
    invoice.invoice_number = "INV-E2E-500"
    invoice.vat = vat_amount
    db.commit()

    assert taxable_amount + invoice.vat == invoice.total
    assert invoice.status == InvoiceStatus.pending

    month_start = dt.date(2026, 7, 1)
    month_end = dt.date(2026, 8, 1)

    def assert_invoice_and_analytics(expected_linked, expected_remaining, expected_expenses):
        invoice_result = next(
            row for row in list_invoices(status=None, supplier=None, month=None, db=db)
            if row["id"] == invoice.id
        )
        pnl_result = monthly_pnl(db, month_start, month_end)
        dashboard_result = overview(month="2026-07", db=db)

        assert invoice_result["status"] == (
            InvoiceStatus.paid.value
            if expected_remaining == 0
            else InvoiceStatus.pending.value
        )
        assert invoice_result["total"] == 500.0
        assert invoice_result["vat"] == 90.16
        assert invoice_result["linked_amount"] == expected_linked
        assert invoice_result["remaining_amount"] == expected_remaining
        assert pnl_result["expenses"] == Decimal(str(expected_expenses))
        assert dashboard_result["pnl_summary"]["expenses"] == expected_expenses

    assert_invoice_and_analytics(0.0, 500.0, 0.0)

    transaction_one = add_transaction(db, amount="-200.00", date=dt.date(2026, 7, 10))
    first_result = reconcile(db, invoice, transaction_one)

    assert first_result["invoice_status"] == InvoiceStatus.pending.value
    assert first_result["linked_amount"] == 200.0
    assert first_result["remaining_amount"] == 300.0
    assert_invoice_and_analytics(200.0, 300.0, 0.0)

    transaction_two = add_transaction(db, amount="-300.00", date=dt.date(2026, 7, 20))
    second_result = reconcile(db, invoice, transaction_two)

    assert second_result["invoice_status"] == InvoiceStatus.paid.value
    assert second_result["linked_amount"] == 500.0
    assert second_result["remaining_amount"] == 0.0
    assert_invoice_and_analytics(500.0, 0.0, 500.0)

    second_invoice_result = create_invoice(
        finance_router.InvoiceCreate(
            supplier="Supplier B",
            invoice_number="INV-E2E-REUSE-GUARD",
            issue_date=dt.date(2026, 7, 2),
            due_date=dt.date(2026, 7, 31),
            total=Decimal("600.00"),
            vat=Decimal("108.20"),
        ),
        db,
    )
    second_invoice_id = second_invoice_result["id"]
    first_payment = db.scalar(select(Payment).where(Payment.transaction_id == transaction_one.id))
    second_payment = db.scalar(select(Payment).where(Payment.transaction_id == transaction_two.id))
    original_links = db.scalars(
        select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == invoice.id)
    ).all()
    original_payment_ids = {link.payment_id for link in original_links}

    assert len(original_links) == 2
    assert original_payment_ids == {first_payment.id, second_payment.id}

    for payment in (first_payment, second_payment):
        with pytest.raises(HTTPException) as error:
            link_payment(
                second_invoice_id,
                LinkPaymentPayload(payment_id=payment.id),
                db,
            )

        assert error.value.status_code == 409
        current_links = db.scalars(
            select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == invoice.id)
        ).all()
        assert {link.payment_id for link in current_links} == original_payment_ids
        assert db.scalars(
            select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == second_invoice_id)
        ).all() == []

    assert_invoice_and_analytics(500.0, 0.0, 500.0)


def test_invoice_summary_excludes_paid_status_without_full_linked_total(db):
    invoice_without_links = add_invoice(db, total="120.00", status=InvoiceStatus.paid)
    invoice_with_partial_links = add_invoice(db, total="100.00", status=InvoiceStatus.paid)
    payment = Payment(
        date=dt.date(2026, 7, 3),
        amount=Decimal("40.00"),
        method=PaymentMethod.bank_transfer,
        counterparty="TORREFAZIONE ITALIANA S.p.A.",
        reference="legacy partial payment",
    )
    db.add(payment)
    db.flush()
    db.add(InvoicePaymentLink(invoice_id=invoice_with_partial_links.id, payment_id=payment.id))
    db.commit()

    summary = invoices_summary(db)

    assert db.get(Invoice, invoice_without_links.id).status == InvoiceStatus.paid
    assert db.get(Invoice, invoice_with_partial_links.id).status == InvoiceStatus.paid
    assert summary["paid_invoices"] == 0
    assert summary["paid_amount"] == 0.0


def test_reupload_unpaid_invoice_updates_existing_fields(db, tmp_path, monkeypatch):
    invoice = add_invoice(db)
    invoice.file_url = "/uploads/original.xml"
    db.commit()

    result = reupload_invoice(db, tmp_path, monkeypatch)

    db.refresh(invoice)
    assert result["already_exists"] is True
    assert result["has_payment_links"] is False
    assert result["update_applied"] is True
    assert invoice.issue_date == dt.date(2026, 8, 1)
    assert invoice.due_date == dt.date(2026, 8, 31)
    assert invoice.total == Decimal("525.00")
    assert invoice.vat == Decimal("75.00")
    assert invoice.status == InvoiceStatus.pending
    assert invoice.file_url == result["file_url"]
    assert invoice.file_url != "/uploads/original.xml"
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    assert (tmp_path / invoice.file_url.removeprefix("/" )).is_file()


def test_extract_missing_issue_date_rejects_without_invoice_or_uploaded_file(db, tmp_path, monkeypatch):
    extracted = {
        "supplier": "TORREFAZIONE ITALIANA S.p.A.",
        "invoice_number": "TC-2026-071",
        "issue_date": None,
        "due_date": "2026-07-10",
        "total": "420.00",
        "vat": "60.00",
    }

    with pytest.raises(HTTPException) as error:
        extract_invoice_with_data(db, tmp_path, monkeypatch, extracted)

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "missing_issue_date"
    assert error.value.detail["message"] == (
        "Non è stato possibile riconoscere la data della fattura. "
        "Verifica il documento e inserisci la fattura manualmente."
    )
    assert db.scalars(select(Invoice)).all() == []
    assert not (tmp_path / "uploads").exists()


def test_extract_missing_due_date_rejects_without_invoice_or_uploaded_file(db, tmp_path, monkeypatch):
    extracted = {
        "supplier": "TORREFAZIONE ITALIANA S.p.A.",
        "invoice_number": "TC-2026-071",
        "issue_date": "2026-07-02",
        "due_date": None,
        "total": "420.00",
        "vat": "60.00",
    }

    with pytest.raises(HTTPException) as error:
        extract_invoice_with_data(db, tmp_path, monkeypatch, extracted)

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "missing_due_date"
    assert db.scalars(select(Invoice)).all() == []
    assert not (tmp_path / "uploads").exists()


def test_ocr_generic_tail_date_is_rejected_without_invoice_or_uploaded_file(db, tmp_path, monkeypatch):
    ocr_text = (
        "Fornitore Alfa\nNumero fattura F-123\nData fattura: 02/07/2026\n"
        "Totale fattura: 420,00 EUR\nIVA 60,00\nPagamento con bonifico\n31/07/2026"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(finance_router, "ocr_pdf_bytes", lambda _: ocr_text)
    monkeypatch.setattr(finance_router, "parse_invoice_with_llm", lambda _: None)
    upload = UploadFile(filename="invoice.pdf", file=BytesIO(b"%PDF-test"))

    with pytest.raises(HTTPException) as error:
        asyncio.run(finance_router.extract_invoice(upload, db))

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "missing_due_date"
    assert db.scalars(select(Invoice)).all() == []
    assert not (tmp_path / "uploads").exists()


def test_extract_valid_dates_creates_invoice_and_saves_document(db, tmp_path, monkeypatch):
    extracted = {
        "supplier": "TORREFAZIONE ITALIANA S.p.A.",
        "invoice_number": "TC-2026-071",
        "issue_date": "2026-07-02",
        "due_date": "2026-07-10",
        "total": "420.00",
        "vat": "60.00",
    }

    result = extract_invoice_with_data(db, tmp_path, monkeypatch, extracted)

    invoice = db.scalar(select(Invoice).where(Invoice.invoice_number == "TC-2026-071"))
    assert result["issue_date"] == "2026-07-02"
    assert result["due_date"] == "2026-07-10"
    assert invoice.issue_date == dt.date(2026, 7, 2)
    assert invoice.status == InvoiceStatus.pending
    assert (tmp_path / invoice.file_url.removeprefix("/")).is_file()


def test_reupload_partially_paid_invoice_preserves_fields_links_and_upload_file(db, tmp_path, monkeypatch):
    invoice = add_invoice(db)
    invoice.file_url = "/uploads/original.xml"
    db.commit()
    transaction = add_transaction(db, amount="-200.00")
    reconcile(db, invoice, transaction)
    original_fields = (
        invoice.supplier,
        invoice.invoice_number,
        invoice.issue_date,
        invoice.due_date,
        invoice.total,
        invoice.vat,
        invoice.status,
        invoice.file_url,
    )
    original_links = db.scalars(
        select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == invoice.id)
    ).all()

    result = reupload_invoice(db, tmp_path, monkeypatch, total="525.00")

    db.refresh(invoice)
    current_links = db.scalars(
        select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == invoice.id)
    ).all()
    assert result["already_exists"] is True
    assert result["has_payment_links"] is True
    assert result["update_applied"] is False
    assert (
        invoice.supplier,
        invoice.invoice_number,
        invoice.issue_date,
        invoice.due_date,
        invoice.total,
        invoice.vat,
        invoice.status,
        invoice.file_url,
    ) == original_fields
    assert [(link.id, link.payment_id) for link in current_links] == [
        (link.id, link.payment_id) for link in original_links
    ]
    assert result["linked_amount"] == 200.0
    assert result["remaining_amount"] == 220.0
    assert not (tmp_path / "uploads").exists()


def test_reupload_fully_paid_invoice_preserves_status_links_and_pnl(db, tmp_path, monkeypatch):
    invoice = add_invoice(db)
    invoice.file_url = "/uploads/original.xml"
    db.commit()
    transaction = add_transaction(db, amount="-420.00")
    reconcile(db, invoice, transaction)
    original_fields = (
        invoice.issue_date,
        invoice.due_date,
        invoice.total,
        invoice.vat,
        invoice.status,
        invoice.file_url,
    )
    original_links = db.scalars(
        select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == invoice.id)
    ).all()
    month_start = dt.date(2026, 7, 1)
    month_end = dt.date(2026, 8, 1)
    assert monthly_pnl(db, month_start, month_end)["expenses"] == Decimal("420.00")

    result = reupload_invoice(db, tmp_path, monkeypatch, total="525.00")

    db.refresh(invoice)
    current_links = db.scalars(
        select(InvoicePaymentLink).where(InvoicePaymentLink.invoice_id == invoice.id)
    ).all()
    assert result["already_exists"] is True
    assert result["has_payment_links"] is True
    assert result["update_applied"] is False
    assert invoice.status == InvoiceStatus.paid
    assert (
        invoice.issue_date,
        invoice.due_date,
        invoice.total,
        invoice.vat,
        invoice.status,
        invoice.file_url,
    ) == original_fields
    assert [(link.id, link.payment_id) for link in current_links] == [
        (link.id, link.payment_id) for link in original_links
    ]
    assert result["linked_amount"] == 420.0
    assert result["remaining_amount"] == 0.0
    assert monthly_pnl(db, month_start, month_end)["expenses"] == Decimal("420.00")
    assert not (tmp_path / "uploads").exists()


def test_multiple_transactions_can_pay_one_invoice(db):
    invoice = add_invoice(db)
    first = add_transaction(db, amount="-200.00")
    second = add_transaction(
        db,
        amount="-220.00",
        date=dt.date(2026, 7, 8),
        description="Second transfer - Torrefazione Italiana S.p.A.",
    )

    first_result = reconcile(db, invoice, first)
    second_result = reconcile(db, invoice, second)

    assert first_result["remaining_amount"] == 220.0
    assert second_result["invoice_status"] == "paid"
    assert db.query(Payment).count() == 2
    assert db.query(InvoicePaymentLink).count() == 2


def test_expenses_by_category_matches_completed_invoice_pnl_costs(db):
    coffee_invoice = add_invoice(db, total="420.00")
    coffee_invoice.supplier = "Torrefazione Italiana S.p.A."
    coffee_invoice.invoice_number = "TC-2026-071"
    reconcile(db, coffee_invoice, add_transaction(db, amount="-420.00"))

    beverage_invoice = add_invoice(db, total="500.00")
    beverage_invoice.supplier = "DISTRIBUZIONE BEVANDE S.R.L."
    beverage_invoice.invoice_number = "DB-2026-072"
    reconcile(
        db,
        beverage_invoice,
        add_transaction(db, amount="-200.00", date=dt.date(2026, 7, 15)),
    )
    reconcile(
        db,
        beverage_invoice,
        add_transaction(db, amount="-300.00", date=dt.date(2026, 7, 18)),
    )

    partial_invoice = add_invoice(db, total="100.00")
    partial_invoice.supplier = "Servizi Alfa"
    partial_invoice.invoice_number = "SA-2026-001"
    reconcile(db, partial_invoice, add_transaction(db, amount="-40.00"))

    add_transaction(db, amount="-90.00", description="Unlinked bank debit")

    result = expenses_by_category("2026-07", db)
    pnl = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))

    assert result["items"] == [
        {"category": "Bevande", "total_amount": 500.0},
        {"category": "Caffe", "total_amount": 420.0},
    ]
    assert sum(item["total_amount"] for item in result["items"]) == float(pnl["expenses"]) == 920.0
    assert expenses_by_category("2026-08", db)["items"] == []


def test_positive_transaction_cannot_pay_invoice(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="100.00", description="Incoming transfer")

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 400
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []


def test_overpayment_is_rejected(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="-421.00")

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 409
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []


def test_same_transaction_cannot_be_reconciled_twice(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)
    reconcile(db, invoice, transaction)

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 409
    assert db.query(Payment).count() == 1
    assert db.query(InvoicePaymentLink).count() == 1


def test_database_rejects_two_payments_for_same_transaction(db):
    transaction = add_transaction(db)
    first_payment = Payment(
        date=transaction.date,
        amount=Decimal("200.00"),
        method=PaymentMethod.bank_transfer,
        counterparty=transaction.counterparty,
        reference="first",
        transaction_id=transaction.id,
    )
    second_payment = Payment(
        date=transaction.date,
        amount=Decimal("220.00"),
        method=PaymentMethod.bank_transfer,
        counterparty=transaction.counterparty,
        reference="second",
        transaction_id=transaction.id,
    )
    db.add_all([first_payment, second_payment])

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()
    assert db.scalars(select(Payment)).all() == []


def test_same_payment_cannot_be_linked_to_two_invoices(db):
    first_invoice = add_invoice(db)
    second_invoice = add_invoice(db, total="500.00")
    payment = create_payment(
        PaymentCreate(
            date=dt.date(2026, 7, 3),
            amount=Decimal("200.00"),
            method=PaymentMethod.bank_transfer,
            counterparty="TORREFAZIONE ITALIANA S.p.A.",
            reference="manual payment",
        ),
        db,
    )

    link_payment(first_invoice.id, LinkPaymentPayload(payment_id=payment["id"]), db)
    with pytest.raises(HTTPException) as error:
        link_payment(second_invoice.id, LinkPaymentPayload(payment_id=payment["id"]), db)

    assert error.value.status_code == 409
    assert db.query(InvoicePaymentLink).count() == 1


def test_legacy_link_endpoint_rejects_overpayment(db):
    invoice = add_invoice(db)
    payment = create_payment(
        PaymentCreate(
            date=dt.date(2026, 7, 3),
            amount=Decimal("421.00"),
            method=PaymentMethod.bank_transfer,
            counterparty="TORREFAZIONE ITALIANA S.p.A.",
            reference="overpayment",
        ),
        db,
    )

    with pytest.raises(HTTPException) as error:
        link_payment(invoice.id, LinkPaymentPayload(payment_id=payment["id"]), db)

    assert error.value.status_code == 409
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    assert invoice.status == InvoiceStatus.pending


def test_reconciliation_rolls_back_payment_if_link_creation_fails(db, monkeypatch):
    invoice = add_invoice(db)
    transaction = add_transaction(db)
    original_add = db.add

    def fail_on_link(instance):
        if isinstance(instance, InvoicePaymentLink):
            raise RuntimeError("simulated link failure")
        original_add(instance)

    monkeypatch.setattr(db, "add", fail_on_link)

    with pytest.raises(HTTPException) as error:
        reconcile(db, invoice, transaction)

    assert error.value.status_code == 500
    monkeypatch.setattr(db, "add", original_add)
    assert db.scalars(select(Payment)).all() == []
    assert db.scalars(select(InvoicePaymentLink)).all() == []
    assert invoice.status == InvoiceStatus.pending


def test_transaction_delete_is_restricted_after_reconciliation(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db)
    reconcile(db, invoice, transaction)

    db.delete(transaction)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assert db.get(Transaction, transaction.id) is not None
    assert db.query(Payment).count() == 1


def test_manual_payment_keeps_transaction_id_null(db):
    result = create_payment(
        PaymentCreate(
            date=dt.date(2026, 7, 3),
            amount=Decimal("25.00"),
            method=PaymentMethod.cash,
            counterparty="TORREFAZIONE ITALIANA S.p.A.",
            reference="cash",
        ),
        db,
    )

    assert db.get(Payment, result["id"]).transaction_id is None


def test_invoice_summary_counts_only_remaining_amount_after_partial_payment(db):
    invoice = add_invoice(db)
    transaction = add_transaction(db, amount="-200.00")
    reconcile(db, invoice, transaction)

    summary = invoices_summary(db)

    assert summary["pending_amount"] == 220.0
    assert summary["pending_invoices"] == 1


@pytest.mark.parametrize(
    ("payment_amount", "expected_pending_amount", "expected_pending_invoices", "expected_expenses"),
    [
        (None, 500.0, 1, Decimal("0.00")),
        ("-200.00", 300.0, 1, Decimal("0.00")),
        ("-500.00", 0.0, 0, Decimal("500.00")),
    ],
)
def test_invoice_summary_and_pnl_follow_partial_payment_residual(
    db, payment_amount, expected_pending_amount, expected_pending_invoices, expected_expenses
):
    invoice = add_invoice(db, total="500.00")
    if payment_amount is not None:
        transaction = add_transaction(db, amount=payment_amount)
        reconcile(db, invoice, transaction)

    summary = invoices_summary(db)
    pnl = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))

    assert summary["pending_amount"] == expected_pending_amount
    assert summary["pending_invoices"] == expected_pending_invoices
    assert pnl["expenses"] == expected_expenses


def test_pnl_counts_invoice_once_in_month_partial_and_final_payment_happen(db):
    invoice = add_invoice(db)
    first = add_transaction(db, amount="-200.00", date=dt.date(2026, 7, 3))
    second = add_transaction(db, amount="-220.00", date=dt.date(2026, 7, 20))
    reconcile(db, invoice, first)
    reconcile(db, invoice, second)

    pnl = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))

    assert pnl["expenses"] == Decimal("420.00")


def test_pnl_counts_invoice_only_in_month_final_payment_completes_balance(db):
    invoice = add_invoice(db)
    first = add_transaction(db, amount="-200.00", date=dt.date(2026, 7, 3))
    second = add_transaction(db, amount="-220.00", date=dt.date(2026, 8, 2))
    reconcile(db, invoice, first)
    reconcile(db, invoice, second)

    july = monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1))
    august = monthly_pnl(db, dt.date(2026, 8, 1), dt.date(2026, 9, 1))

    assert july["expenses"] == Decimal("0.00")
    assert august["expenses"] == Decimal("420.00")
