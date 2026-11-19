from sqlalchemy import select

from app.models import Invoice, MembershipPermission, UserBarMembership
from test_finance_tenant_scope import (
    ALLOWED_ORIGIN,
    finance_environment,
    login,
    select_bar,
)


def test_staff_invoice_delete_requires_permission(finance_environment):
    client, sessionmaker, ids, _ = finance_environment

    with sessionmaker() as db:
        invoice = Invoice(
            bar_id=ids["bar_one"],
            supplier="Fornitore test",
            invoice_number="DELETE-001",
            issue_date=__import__("datetime").date(2026, 7, 2),
            due_date=__import__("datetime").date(2026, 7, 20),
            total=__import__("decimal").Decimal("120.00"),
            vat=__import__("decimal").Decimal("20.00"),
        )
        db.add(invoice)
        db.commit()
        invoice_id = invoice.id

    staff_csrf = login(client, "finance-staff@example.test")
    assert select_bar(client, ids["bar_one"], staff_csrf).status_code == 200

    def delete_invoice():
        return client.delete(
            f"/invoices/delete/{invoice_id}",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "X-CSRF-Token": staff_csrf,
            },
        )

    denied = delete_invoice()
    assert denied.status_code == 403

    with sessionmaker() as db:
        assert db.get(Invoice, invoice_id) is not None

        membership = db.scalar(
            select(UserBarMembership).where(
                UserBarMembership.user_id == ids["staff"],
                UserBarMembership.bar_id == ids["bar_one"],
            )
        )
        db.add(
            MembershipPermission(
                membership_id=membership.id,
                permission="invoices.delete",
            )
        )
        db.commit()

    allowed = delete_invoice()
    assert allowed.status_code == 200, allowed.text

    with sessionmaker() as db:
        assert db.get(Invoice, invoice_id) is None


def test_staff_cannot_delete_invoice_from_another_bar(finance_environment):
    client, sessionmaker, ids, _ = finance_environment

    with sessionmaker() as db:
        invoice = Invoice(
            bar_id=ids["bar_two"],
            supplier="Altro bar",
            invoice_number="FOREIGN-001",
            issue_date=__import__("datetime").date(2026, 7, 2),
            due_date=__import__("datetime").date(2026, 7, 20),
            total=__import__("decimal").Decimal("100.00"),
            vat=__import__("decimal").Decimal("10.00"),
        )
        db.add(invoice)

        membership = db.scalar(
            select(UserBarMembership).where(
                UserBarMembership.user_id == ids["staff"],
                UserBarMembership.bar_id == ids["bar_one"],
            )
        )
        db.add(
            MembershipPermission(
                membership_id=membership.id,
                permission="invoices.delete",
            )
        )
        db.commit()
        invoice_id = invoice.id

    staff_csrf = login(client, "finance-staff@example.test")
    assert select_bar(client, ids["bar_one"], staff_csrf).status_code == 200

    response = client.delete(
        f"/invoices/delete/{invoice_id}",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": staff_csrf,
        },
    )
    assert response.status_code == 404

    with sessionmaker() as db:
        assert db.get(Invoice, invoice_id) is not None
