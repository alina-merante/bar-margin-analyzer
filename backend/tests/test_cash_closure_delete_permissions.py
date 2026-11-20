import datetime as dt
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    CashClosureIntake,
    DailyCashClosure,
    Document,
    MembershipPermission,
    UserBarMembership,
)
from test_document_tenant_scope import document_environment, headers, login, select_bar
from test_approved_closure_document_delete import create_test_document


def grant_cash_delete(factory, ids):
    with factory() as db:
        membership = db.scalar(
            select(UserBarMembership).where(
                UserBarMembership.user_id == ids["staff"],
                UserBarMembership.bar_id == ids["bar_one"],
            )
        )
        db.add(
            MembershipPermission(
                membership_id=membership.id,
                permission="cash_closures.delete",
            )
        )
        db.commit()


def test_staff_needs_cash_delete_permission(document_environment):
    client, factory, ids, _root, _app = document_environment
    csrf = login(client, "staff@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    document_id = create_test_document(
        factory, ids["bar_one"], "pending-cash.png"
    )

    response = client.delete(
        f"/documents/{document_id}", headers=headers(csrf)
    )
    assert response.status_code == 403

    grant_cash_delete(factory, ids)

    response = client.delete(
        f"/documents/{document_id}", headers=headers(csrf)
    )
    assert response.status_code == 200

    with factory() as db:
        assert db.get(Document, document_id) is None


def test_staff_cannot_delete_approved_closure(document_environment):
    client, factory, ids, _root, _app = document_environment
    csrf = login(client, "staff@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    grant_cash_delete(factory, ids)

    document_id = create_test_document(
        factory, ids["bar_one"], "approved-cash.png"
    )

    with factory() as db:
        closure = DailyCashClosure(
            bar_id=ids["bar_one"],
            document_id=document_id,
            date=dt.date(2026, 11, 20),
            closure_number="APPROVED-STAFF",
            total_amount=Decimal("150.00"),
        )
        db.add(closure)
        db.flush()

        intake = CashClosureIntake(
            bar_id=ids["bar_one"],
            document_id=document_id,
            closure_id=closure.id,
            source_sha256="e" * 64,
            classification="SAVE_FOR_REVIEW",
            status="approved",
            ocr_values={},
            anomalies=[],
        )
        db.add(intake)
        db.commit()
        closure_id = closure.id
        intake_id = intake.id

    response = client.delete(
        f"/documents/{document_id}", headers=headers(csrf)
    )
    assert response.status_code == 409

    with factory() as db:
        assert db.get(Document, document_id) is not None
        assert db.get(DailyCashClosure, closure_id) is not None
        assert db.get(CashClosureIntake, intake_id) is not None
