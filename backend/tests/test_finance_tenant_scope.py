import datetime as dt
import importlib
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, get_db
from app.models import (
    Bar,
    Invoice,
    InvoicePaymentLink,
    InvoiceStatus,
    MembershipRole,
    Payment,
    PaymentMethod,
    Transaction,
    User,
    UserBarMembership,
)
from app.routers.auth import router as auth_router
from app.routers.bar_context import router as bar_context_router
from app.routers.finance import router as finance_router
from app.security import hash_password

finance_module = importlib.import_module("app.routers.finance")


ALLOWED_ORIGIN = "http://localhost:5173"
TEST_PASSWORD = "correct horse battery"


@pytest.fixture
def finance_environment(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'finance-scope.db'}")

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
    api.include_router(finance_router)

    def override_get_db():
        db = test_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    api.dependency_overrides[get_db] = override_get_db
    invoice_upload_dir = tmp_path / "invoice-uploads"
    invoice_upload_dir.mkdir()
    monkeypatch.setattr(
        finance_module,
        "UPLOAD_INVOICES_DIR",
        str(invoice_upload_dir),
    )
    monkeypatch.setattr(finance_module, "ensure_upload_dirs", lambda: None)

    with test_sessionmaker() as db:
        bar_one = Bar(name="Bar Uno")
        bar_two = Bar(name="Bar Due")
        owner = User(
            email="finance-owner@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        manager = User(
            email="finance-manager@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        staff = User(
            email="finance-staff@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        db.add_all([bar_one, bar_two, owner, manager, staff])
        db.flush()
        db.add_all(
            [
                UserBarMembership(
                    user_id=owner.id,
                    bar_id=bar_one.id,
                    role=MembershipRole.owner,
                ),
                UserBarMembership(
                    user_id=owner.id,
                    bar_id=bar_two.id,
                    role=MembershipRole.owner,
                ),
                UserBarMembership(
                    user_id=manager.id,
                    bar_id=bar_one.id,
                    role=MembershipRole.manager,
                ),
                UserBarMembership(
                    user_id=staff.id,
                    bar_id=bar_one.id,
                    role=MembershipRole.staff,
                ),
            ]
        )
        db.commit()
        ids = {
            "bar_one": bar_one.id,
            "bar_two": bar_two.id,
            "owner": owner.id,
            "manager": manager.id,
            "staff": staff.id,
        }

    with TestClient(api) as client:
        yield client, test_sessionmaker, ids, invoice_upload_dir
    engine.dispose()


def login(client, email):
    pre_auth_csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": pre_auth_csrf,
        },
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def select_bar(client, bar_id, csrf_token):
    response = client.put(
        "/auth/active-bar",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        json={"bar_id": bar_id},
    )
    if response.status_code == 200:
        client.headers["X-Expected-Bar-ID"] = str(bar_id)
    return response


def create_invoice(client, csrf_token, *, number="INV-1", bar_id=None):
    payload = {
        "supplier": "Fornitore Comune",
        "invoice_number": number,
        "issue_date": "2026-07-02",
        "due_date": "2026-07-20",
        "total": "120.00",
        "vat": "20.00",
    }
    if bar_id is not None:
        payload["bar_id"] = bar_id
    return client.post(
        "/invoices",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        json=payload,
    )


def post_json(client, path, csrf_token, payload):
    return client.post(
        path,
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        json=payload,
    )


def create_manual_payment(client, csrf_token, amount="50.00"):
    return post_json(
        client,
        "/payments",
        csrf_token,
        {
            "date": "2026-07-05",
            "amount": amount,
            "method": "cash",
            "counterparty": "Fornitore Comune",
            "reference": "contanti",
        },
    )


def test_invoice_and_payment_reads_and_creation_are_scoped_by_active_bar(
    finance_environment,
):
    client, test_sessionmaker, ids, _invoice_upload_dir = finance_environment
    csrf_token = login(client, "finance-owner@example.test")
    assert client.get("/invoices").status_code == 409
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    missing_origin = client.post(
        "/payments",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "date": "2026-07-05",
            "amount": "5.00",
            "method": "cash",
            "counterparty": "Fornitore",
            "reference": "test",
        },
    )
    assert missing_origin.status_code == 403

    first = create_invoice(client, csrf_token, bar_id=ids["bar_two"])
    assert first.status_code == 200
    invoice_one_id = first.json()["id"]
    assert first.json()["supplier"] == "Fornitore Comune"

    payment_one = create_manual_payment(client, csrf_token)
    assert payment_one.status_code == 200
    assert client.get("/payments").json()[0]["id"] == payment_one.json()["id"]

    assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200
    second = create_invoice(client, csrf_token)
    assert second.status_code == 200
    invoice_two_id = second.json()["id"]
    payment_two = create_manual_payment(client, csrf_token, "30.00")
    assert payment_two.status_code == 200

    assert {row["id"] for row in client.get("/invoices").json()} == {invoice_two_id}
    assert {row["id"] for row in client.get("/payments").json()} == {
        payment_two.json()["id"]
    }
    assert client.get(f"/invoices/{invoice_one_id}/payments").status_code == 404
    assert client.get(
        f"/invoices/{invoice_one_id}/transaction-candidates"
    ).status_code == 404
    cross_tenant_delete = client.delete(
        f"/invoices/delete/{invoice_one_id}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
    )
    assert cross_tenant_delete.status_code == 404

    with test_sessionmaker() as db:
        invoices = db.scalars(select(Invoice).order_by(Invoice.bar_id)).all()
        payments = db.scalars(select(Payment).order_by(Payment.bar_id)).all()
        assert [(row.bar_id, row.invoice_number) for row in invoices] == [
            (ids["bar_one"], "INV-1"),
            (ids["bar_two"], "INV-1"),
        ]
        assert [row.bar_id for row in payments] == [ids["bar_one"], ids["bar_two"]]


def test_manual_payment_links_reject_cross_tenant_ids_and_unlink_scoped_payment(
    finance_environment,
):
    client, test_sessionmaker, ids, _invoice_upload_dir = finance_environment
    csrf_token = login(client, "finance-owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    invoice_one = create_invoice(client, csrf_token).json()
    payment_one = create_manual_payment(client, csrf_token).json()

    assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200
    invoice_two = create_invoice(client, csrf_token).json()
    payment_two = create_manual_payment(client, csrf_token, "30.00").json()
    foreign_link = post_json(
        client,
        f"/invoices/{invoice_two['id']}/link-payment",
        csrf_token,
        {"payment_id": payment_one["id"]},
    )
    assert foreign_link.status_code == 404

    link_response = post_json(
        client,
        f"/invoices/{invoice_two['id']}/link-payment",
        csrf_token,
        {"payment_id": payment_two["id"]},
    )
    assert link_response.status_code == 200
    assert link_response.json()["linked_amount"] == 30.0
    invoice_two_payments = client.get(
        f"/invoices/{invoice_two['id']}/payments"
    ).json()
    assert [row["payment_id"] for row in invoice_two_payments["payments"]] == [
        payment_two["id"]
    ]

    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    foreign_unlink = client.delete(
        f"/invoices/{invoice_two['id']}/payments/{link_response.json()['id']}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
    )
    assert foreign_unlink.status_code == 404
    assert client.get(
        f"/invoices/{invoice_one['id']}/payments"
    ).json()["payments"] == []

    assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200
    unlinked = client.delete(
        f"/invoices/{invoice_two['id']}/payments/{link_response.json()['id']}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["payment_deleted"] is False
    assert unlinked.json()["linked_amount"] == 0.0
    with test_sessionmaker() as db:
        assert db.get(Payment, payment_one["id"]) is not None
        assert db.get(Payment, payment_two["id"]) is not None
        assert db.scalars(select(InvoicePaymentLink)).all() == []


def test_preexisting_cross_tenant_links_are_hidden_and_not_mutated(
    finance_environment,
):
    client, test_sessionmaker, ids, _invoice_upload_dir = finance_environment
    csrf_token = login(client, "finance-owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    invoice = create_invoice(client, csrf_token).json()

    assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200
    payment = create_manual_payment(client, csrf_token).json()

    with test_sessionmaker() as db:
        foreign_transaction = Transaction(
            bar_id=ids["bar_two"],
            date=dt.date(2026, 7, 6),
            description="Bonifico altro bar",
            amount=Decimal("-5.00"),
            counterparty="Altro bar",
        )
        db.add(foreign_transaction)
        db.flush()
        cross_tenant_transaction_payment = Payment(
            bar_id=ids["bar_one"],
            date=dt.date(2026, 7, 6),
            amount=Decimal("5.00"),
            method=PaymentMethod.bank_transfer,
            counterparty="Altro bar",
            reference="dati incoerenti",
            transaction_id=foreign_transaction.id,
        )
        db.add(cross_tenant_transaction_payment)
        db.add(
            InvoicePaymentLink(
                bar_id=ids["bar_one"],
                invoice_id=invoice["id"],
                payment_id=payment["id"],
            )
        )
        db.commit()
        foreign_link = db.scalar(
            select(InvoicePaymentLink).where(
                InvoicePaymentLink.invoice_id == invoice["id"]
            )
        )
        foreign_link_id = foreign_link.id

    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    invoice_list_row = client.get("/invoices").json()[0]
    assert invoice_list_row["linked_amount"] == 0.0
    assert client.get("/payments").json() == []
    invoice_payments = client.get(
        f"/invoices/{invoice['id']}/payments"
    ).json()
    assert invoice_payments["linked_amount"] == 0.0
    assert invoice_payments["payments"] == []

    unlink = client.delete(
        f"/invoices/{invoice['id']}/payments/{foreign_link_id}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
    )
    delete_invoice = client.delete(
        f"/invoices/delete/{invoice['id']}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
    )
    assert unlink.status_code == 409
    assert delete_invoice.status_code == 409
    with test_sessionmaker() as db:
        assert db.get(Invoice, invoice["id"]) is not None
        assert db.get(Payment, payment["id"]) is not None
        assert db.get(InvoicePaymentLink, foreign_link_id) is not None


def test_bank_reconciliation_isolated_and_balances_update_after_unlink(
    finance_environment,
):
    client, test_sessionmaker, ids, _invoice_upload_dir = finance_environment
    with test_sessionmaker() as db:
        tx_one = Transaction(
            bar_id=ids["bar_one"],
            date=dt.date(2026, 7, 3),
            description="Bonifico Fornitore Comune",
            amount=Decimal("-120.00"),
            counterparty="Fornitore Comune",
        )
        tx_two = Transaction(
            bar_id=ids["bar_two"],
            date=dt.date(2026, 7, 4),
            description="Bonifico Fornitore Comune",
            amount=Decimal("-120.00"),
            counterparty="Fornitore Comune",
        )
        db.add_all([tx_one, tx_two])
        db.commit()
        transaction_one_id, transaction_two_id = tx_one.id, tx_two.id

    csrf_token = login(client, "finance-owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    invoice_one = create_invoice(client, csrf_token).json()
    candidates = client.get(
        f"/invoices/{invoice_one['id']}/transaction-candidates"
    ).json()
    assert [row["id"] for row in candidates["candidates"]] == [transaction_one_id]

    cross_reconcile = post_json(
        client,
        f"/invoices/{invoice_one['id']}/reconcile-transaction",
        csrf_token,
        {"transaction_id": transaction_two_id},
    )
    assert cross_reconcile.status_code == 404

    reconciled = post_json(
        client,
        f"/invoices/{invoice_one['id']}/reconcile-transaction",
        csrf_token,
        {"transaction_id": transaction_one_id},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["linked_amount"] == 120.0
    assert reconciled.json()["remaining_amount"] == 0.0
    invoice_payments = client.get(
        f"/invoices/{invoice_one['id']}/payments"
    ).json()
    assert invoice_payments["linked_amount"] == 120.0
    assert invoice_payments["payments"][0]["transaction_id"] == transaction_one_id

    link_id = invoice_payments["payments"][0]["link_id"]
    unlinked = client.delete(
        f"/invoices/{invoice_one['id']}/payments/{link_id}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["payment_deleted"] is True
    assert unlinked.json()["remaining_amount"] == 120.0
    with test_sessionmaker() as db:
        assert db.get(Transaction, transaction_one_id) is not None
        assert db.get(Payment, reconciled.json()["payment_id"]) is None
        assert db.get(Transaction, transaction_two_id).payment is None


def test_staff_is_read_only_legacy_rows_hidden_and_membership_rechecked(
    finance_environment,
):
    client, test_sessionmaker, ids, _invoice_upload_dir = finance_environment
    csrf_token = login(client, "finance-owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    invoice = create_invoice(client, csrf_token).json()
    legacy_invoice = Invoice(
        supplier="Legacy",
        invoice_number="LEG-1",
        issue_date=dt.date(2026, 7, 1),
        due_date=dt.date(2026, 7, 10),
        total=Decimal("10.00"),
        vat=Decimal("0.00"),
        status=InvoiceStatus.pending,
    )
    legacy_payment = Payment(
        date=dt.date(2026, 7, 2),
        amount=Decimal("10.00"),
        method=PaymentMethod.cash,
        counterparty="Legacy",
        reference="legacy",
    )
    with test_sessionmaker() as db:
        db.add_all([legacy_invoice, legacy_payment])
        db.flush()
        legacy_invoice_id = legacy_invoice.id
        db.add(
            InvoicePaymentLink(
                invoice_id=legacy_invoice.id,
                payment_id=legacy_payment.id,
            )
        )
        db.commit()

    assert {row["id"] for row in client.get("/invoices").json()} == {invoice["id"]}
    assert client.get("/payments").json() == []
    assert client.get(f"/invoices/{legacy_invoice_id}/payments").status_code == 404
    client.post(
        "/auth/logout",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
    )
    staff_csrf = login(client, "finance-staff@example.test")
    assert select_bar(client, ids["bar_one"], staff_csrf).status_code == 200
    assert {row["id"] for row in client.get("/invoices").json()} == {invoice["id"]}
    assert client.get("/payments").json() == []

    denied_create_payment = create_manual_payment(client, staff_csrf)
    denied_create_invoice = create_invoice(client, staff_csrf, number="STAFF")
    denied_unlink = client.delete(
        f"/invoices/{invoice['id']}/payments/1",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": staff_csrf,
        },
    )
    assert denied_create_payment.status_code == 403
    assert denied_create_invoice.status_code == 403
    assert denied_unlink.status_code == 403

    with test_sessionmaker() as db:
        membership = db.scalar(
            select(UserBarMembership).where(
                UserBarMembership.user_id == ids["staff"],
                UserBarMembership.bar_id == ids["bar_one"],
            )
        )
        assert membership is not None
        db.delete(membership)
        db.commit()
    assert client.get("/invoices").status_code == 403


def test_manager_can_operate_finances_and_disabled_bar_revokes_context(
    finance_environment,
):
    client, test_sessionmaker, ids, _invoice_upload_dir = finance_environment
    csrf_token = login(client, "finance-manager@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    assert create_invoice(client, csrf_token).status_code == 200
    assert create_manual_payment(client, csrf_token).status_code == 200

    with test_sessionmaker() as db:
        bar = db.get(Bar, ids["bar_one"])
        assert bar is not None
        bar.is_active = False
        db.commit()

    assert client.get("/invoices").status_code == 403


def test_invoice_extract_requires_auth_and_assigns_active_bar(
    finance_environment,
    monkeypatch,
):
    client, test_sessionmaker, ids, invoice_upload_dir = finance_environment
    content = b"<invoice/>"
    unauthenticated = client.post(
        "/invoices/extract",
        files={"file": ("invoice.xml", content, "application/xml")},
    )
    assert unauthenticated.status_code == 401

    csrf_token = login(client, "finance-owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    extracted = {
        "supplier": "Fornitore XML",
        "invoice_number": "XML-1",
        "issue_date": dt.date(2026, 7, 1),
        "due_date": dt.date(2026, 7, 10),
        "total": Decimal("12.00"),
        "vat": Decimal("2.00"),
    }
    monkeypatch.setattr(finance_module, "extract_invoice_from_xml", lambda _content: {})
    monkeypatch.setattr(
        finance_module,
        "normalize_extracted_invoice",
        lambda _extracted: extracted,
    )
    response = client.post(
        "/invoices/extract",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        files={"file": ("invoice.xml", content, "application/xml")},
    )
    assert response.status_code == 200
    assert response.json()["supplier"] == "Fornitore XML"
    assert list(invoice_upload_dir.iterdir())
    with test_sessionmaker() as db:
        invoice = db.scalar(
            select(Invoice).where(Invoice.invoice_number == "XML-1")
        )
        assert invoice is not None
        assert invoice.bar_id == ids["bar_one"]
