import datetime as dt
from decimal import Decimal
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    Bar, DailyCashClosure, Invoice, InvoicePaymentLink, InvoiceStatus, Payment,
    PaymentMethod, Product, SaleLine, Transaction, UserBarMembership,
)
from app.routers.analytics import (
    fetch_ranked_products, invoice_payment_totals_subquery, monthly_pnl,
    router as analytics_router,
)
from test_operational_tenant_scope import (
    login, operational_environment, seed_bars, select_bar,
)


@pytest.fixture
def analytics_environment(operational_environment):
    client, _engine, factory, api = operational_environment
    api.include_router(analytics_router)
    ids = seed_bars(factory)
    with factory() as db:
        for bar_id, amount, previous, product_name, quantity, cost in (
            (ids["bar_one"], "1000", "500", "Coffee", "10", "100"),
            (ids["bar_two"], "3000", "2000", "Tea", "20", "250"),
            (None, "9000", "8000", "Legacy", "99", "900"),
        ):
            db.add_all([
                DailyCashClosure(
                    bar_id=bar_id, date=dt.date(2026, 7, 10),
                    total_amount=Decimal(amount), cash_amount=Decimal("10"),
                    card_amount=Decimal("20"),
                    created_at=dt.datetime(2026, 7, 10, 12),
                ),
                DailyCashClosure(
                    bar_id=bar_id, date=dt.date(2026, 6, 10),
                    total_amount=Decimal(previous), created_at=dt.datetime(2026, 6, 10, 12),
                ),
                DailyCashClosure(
                    bar_id=bar_id, date=dt.date(2025, 12, 10),
                    total_amount=Decimal("111" if bar_id == ids["bar_one"] else
                                         "222" if bar_id == ids["bar_two"] else "999"),
                    created_at=dt.datetime(2025, 12, 10, 12),
                ),
                Transaction(
                    bar_id=bar_id, date=dt.date(2026, 7, 11),
                    description="bank", counterparty="supplier", amount=Decimal("-1"),
                ),
            ])
            product = Product(bar_id=bar_id, name=product_name)
            invoice = Invoice(
                bar_id=bar_id, supplier="Coffee supplier", invoice_number=f"INV-{product_name}",
                issue_date=dt.date(2026, 7, 1), due_date=dt.date(2026, 7, 31),
                total=Decimal(cost), vat=Decimal("0"), status=InvoiceStatus.paid,
            )
            payment = Payment(
                bar_id=bar_id, date=dt.date(2026, 7, 12),
                amount=Decimal(cost), method=PaymentMethod.bank_transfer,
                counterparty="supplier", reference=product_name,
            )
            db.add_all([product, invoice, payment])
            db.flush()
            db.add_all([
                SaleLine(
                    bar_id=bar_id, product_id=product.id, date=dt.date(2026, 7, 10),
                    qty=Decimal(quantity), total=Decimal(amount),
                ),
                InvoicePaymentLink(
                    bar_id=bar_id, invoice_id=invoice.id, payment_id=payment.id,
                ),
            ])

        product_one = db.scalar(select(Product).where(Product.name == "Coffee"))
        product_two = db.scalar(select(Product).where(Product.name == "Tea"))
        db.add_all([
            DailyCashClosure(
                bar_id=ids["bar_two"], date=dt.date(2027, 1, 10),
                total_amount=Decimal("123"), created_at=dt.datetime(2027, 1, 10, 12),
            ),
            DailyCashClosure(
                bar_id=None, date=dt.date(2030, 1, 10),
                total_amount=Decimal("9999"), created_at=dt.datetime(2030, 1, 10, 12),
            ),
            Transaction(
                bar_id=ids["bar_two"], date=dt.date(2028, 1, 10),
                description="other bank", counterparty="supplier", amount=Decimal("-1"),
            ),
            Transaction(
                bar_id=None, date=dt.date(2031, 1, 10),
                description="legacy bank", counterparty="supplier", amount=Decimal("-1"),
            ),
            Payment(
                bar_id=ids["bar_one"], date=dt.date(2026, 7, 12), amount=Decimal("7"),
                method=PaymentMethod.cash, counterparty="supplier", reference="cash",
            ),
            Payment(
                bar_id=ids["bar_one"], date=dt.date(2026, 7, 12), amount=Decimal("8"),
                method=PaymentMethod.card, counterparty="supplier", reference="card",
            ),
            SaleLine(
                bar_id=ids["bar_one"], product_id=product_two.id,
                date=dt.date(2026, 7, 10), qty=Decimal("999"), total=Decimal("9999"),
            ),
            SaleLine(
                bar_id=ids["bar_two"], product_id=product_one.id,
                date=dt.date(2026, 7, 10), qty=Decimal("999"), total=Decimal("9999"),
            ),
            SaleLine(
                bar_id=None, product_id=product_one.id,
                date=dt.date(2026, 7, 10), qty=Decimal("999"), total=Decimal("9999"),
            ),
        ])
        invalid_invoice = Invoice(
            bar_id=ids["bar_one"], supplier="Other", invoice_number="INVALID-LINK",
            issue_date=dt.date(2026, 7, 1), due_date=dt.date(2026, 7, 31),
            total=Decimal("50"), vat=Decimal("0"), status=InvoiceStatus.paid,
        )
        foreign_payment = Payment(
            bar_id=ids["bar_two"], date=dt.date(2026, 7, 15), amount=Decimal("50"),
            method=PaymentMethod.card, counterparty="foreign", reference="bad",
        )
        db.add_all([invalid_invoice, foreign_payment])
        db.flush()
        db.add(InvoicePaymentLink(
            bar_id=ids["bar_one"], invoice_id=invalid_invoice.id, payment_id=foreign_payment.id,
        ))
        db.commit()
    return client, factory, api, ids


ENDPOINTS = (
    "/analytics/top-products?month=2026-07",
    "/analytics/bottom-products?month=2026-07",
    "/analytics/pnl?month=2026-07",
    "/analytics/pnl/trend?month=2026-07&months=2",
    "/analytics/pnl/ytd?year=2026",
    "/analytics/insights?month=2026-07",
    "/analytics/overview?month=2026-07",
    "/analytics/expenses-by-category?month=2026-07",
    "/analytics/expenses-by-supplier?month=2026-07",
    "/analytics/invoices-summary",
    "/analytics/payments-by-method?month=2026-07",
)


def test_all_analytics_require_auth_and_active_bar(analytics_environment):
    client, _factory, _api, ids = analytics_environment
    for endpoint in ENDPOINTS:
        assert client.get(endpoint).status_code == 401, endpoint
    csrf = login(client, "owner@example.test")
    for endpoint in ENDPOINTS:
        assert client.get(endpoint).status_code == 409, endpoint
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    for endpoint in ENDPOINTS:
        response = client.get(endpoint)
        assert response.status_code == 200, (endpoint, response.text)
        assert "no-store" in response.headers["cache-control"]
        assert "Cookie" in response.headers["vary"]


@pytest.mark.parametrize(
    "bar_key,revenue,previous,cost,product,quantity",
    [
        ("bar_one", 1000, 500, 100, "Coffee", 10),
        ("bar_two", 3000, 2000, 250, "Tea", 20),
    ],
)
def test_numeric_kpis_trends_rankings_and_tenant_switch(
    analytics_environment, bar_key, revenue, previous, cost, product, quantity
):
    client, _factory, _api, ids = analytics_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids[bar_key], csrf).status_code == 200
    pnl = client.get("/analytics/pnl", params={"month": "2026-07", "bar_id": -1}).json()
    assert pnl == {
        "month": "2026-07", "revenue": revenue, "expenses": cost,
        "profit": revenue - cost, "previous_month_revenue": previous,
        "previous_month_expenses": 0, "previous_month_profit": previous,
        "revenue_delta": revenue - previous, "expenses_delta": cost,
        "profit_delta": revenue - cost - previous,
    }
    trend = client.get("/analytics/pnl/trend?month=2026-07&months=2").json()
    assert [(row["month"], row["revenue"], row["expenses"]) for row in trend] == [
        ("2026-06", previous, 0), ("2026-07", revenue, cost),
    ]
    year = client.get("/analytics/pnl/ytd?year=2026").json()
    assert (year["revenue_ytd"], year["expenses_ytd"], year["profit_ytd"]) == (
        revenue + previous, cost, revenue + previous - cost,
    )
    assert year["monthly_breakdown"][6]["revenue"] == revenue
    expected_december = 111 if bar_key == "bar_one" else 222
    assert client.get("/analytics/pnl?month=2026-01").json()[
        "previous_month_revenue"
    ] == expected_december
    assert client.get("/analytics/pnl/ytd?year=2025").json()["revenue_ytd"] == expected_december
    insight = client.get("/analytics/insights?month=2026-07").json()["metrics"]
    assert insight["revenue"] == revenue
    assert insight["expenses"] == cost
    assert insight["profit"] == revenue - cost
    assert insight["revenue_change_pct"] == (revenue - previous) / previous * 100

    for endpoint in ("top-products", "bottom-products"):
        ranked = client.get(f"/analytics/{endpoint}?month=2026-07").json()
        assert ranked["by_quantity"] == [
            {"rank": 1, "product": product, "quantity": quantity, "revenue": revenue}
        ]
        assert ranked["by_revenue"] == ranked["by_quantity"]
        assert client.get(f"/analytics/{endpoint}?month=2026-08").json()["by_quantity"] == []

    overview = client.get("/analytics/overview?month=2026-07").json()
    assert overview["pnl_summary"] == {
        "month": "2026-07", "revenue": revenue, "expenses": cost, "profit": revenue - cost,
    }
    assert overview["top_products_by_quantity"] == [
        {"product": product, "quantity": quantity, "revenue": revenue}
    ]
    assert overview["latest_cash_closure_date"] == (
        "2026-07-10" if bar_key == "bar_one" else "2027-01-10"
    )
    assert overview["latest_bank_transaction_date"] == (
        "2026-07-11" if bar_key == "bar_one" else "2028-01-10"
    )
    assert overview["latest_cash_closure_uploaded_at"] == (
        "2026-07-10T12:00:00+00:00" if bar_key == "bar_one" else "2027-01-10T12:00:00+00:00"
    )
    assert client.get("/analytics/expenses-by-category?month=2026-07").json()["items"][0][
        "total_amount"
    ] == cost
    assert client.get("/analytics/expenses-by-category?month=2026-08").json()["items"] == []
    assert client.get("/analytics/expenses-by-supplier?month=2026-07").json()["items"] == []
    summary = client.get("/analytics/invoices-summary").json()
    assert summary == {
        "total_invoices": 2 if bar_key == "bar_one" else 1,
        "paid_invoices": 1, "pending_invoices": 1 if bar_key == "bar_one" else 0,
        "paid_amount": cost, "pending_amount": 50 if bar_key == "bar_one" else 0,
    }
    payments = client.get("/analytics/payments-by-method?month=2026-07").json()["items"]
    assert {"method": "bank_transfer", "total_amount": cost} in payments
    if bar_key == "bar_two":
        assert {"method": "card", "total_amount": 50} in payments
    else:
        assert {"method": "cash", "total_amount": 7} in payments
        assert {"method": "card", "total_amount": 8} in payments
        assert len(payments) == 3

    other = "bar_two" if bar_key == "bar_one" else "bar_one"
    assert select_bar(client, ids[other], csrf).status_code == 200
    assert client.get("/analytics/pnl?month=2026-07").json()["revenue"] != revenue


def test_invoice_subquery_rejects_mismatched_and_legacy_links(analytics_environment):
    client, factory, _api, ids = analytics_environment
    with factory() as db:
        for index, (invoice_bar, link_bar, payment_bar) in enumerate((
            (ids["bar_one"], ids["bar_two"], ids["bar_one"]),
            (ids["bar_one"], None, ids["bar_one"]),
            (ids["bar_two"], ids["bar_one"], ids["bar_one"]),
            (None, ids["bar_one"], ids["bar_one"]),
            (ids["bar_one"], ids["bar_one"], None),
        )):
            invoice = Invoice(
                bar_id=invoice_bar, supplier="Bad link", invoice_number=f"BAD-{index}",
                issue_date=dt.date(2026, 7, 1), due_date=dt.date(2026, 7, 31),
                total=Decimal("70"), vat=Decimal("0"), status=InvoiceStatus.paid,
            )
            payment = Payment(
                bar_id=payment_bar, date=dt.date(2026, 7, 12), amount=Decimal("70"),
                method=PaymentMethod.cash, counterparty="supplier", reference=f"bad-{index}",
            )
            db.add_all([invoice, payment])
            db.flush()
            db.add(InvoicePaymentLink(
                bar_id=link_bar, invoice_id=invoice.id, payment_id=payment.id
            ))
        db.commit()
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert client.get("/analytics/pnl?month=2026-07").json()["expenses"] == 100
    summary = client.get("/analytics/invoices-summary").json()
    assert summary["paid_amount"] == 100
    assert summary["paid_invoices"] == 1
    assert summary["pending_amount"] == 260


def test_query_helpers_reject_missing_tenant(analytics_environment):
    _client, factory, _api, _ids = analytics_environment
    missing_tenant = cast(int, None)
    with factory() as db:
        with pytest.raises(ValueError):
            monthly_pnl(db, dt.date(2026, 7, 1), dt.date(2026, 8, 1), missing_tenant)
        with pytest.raises(ValueError):
            invoice_payment_totals_subquery(missing_tenant)
        with pytest.raises(ValueError):
            fetch_ranked_products(db, "2026-07", "desc", missing_tenant)


def test_roles_revocation_and_deactivated_bar(analytics_environment):
    _client, factory, api, ids = analytics_environment
    for role in ("owner", "manager", "staff"):
        with TestClient(api) as client:
            csrf = login(client, f"{role}@example.test")
            assert select_bar(client, ids["bar_one"], csrf).status_code == 200
            for endpoint in ENDPOINTS:
                assert client.get(endpoint).status_code == 200, (role, endpoint)
            assert client.get("/analytics/pnl?month=2026-07").json()["revenue"] == 1000
    with TestClient(api) as staff:
        csrf = login(staff, "staff@example.test")
        assert select_bar(staff, ids["bar_one"], csrf).status_code == 200
        with factory() as db:
            membership = db.scalar(select(UserBarMembership).where(
                UserBarMembership.user_id == ids["staff"],
                UserBarMembership.bar_id == ids["bar_one"],
            ))
            db.delete(membership)
            db.commit()
        for endpoint in ENDPOINTS:
            assert staff.get(endpoint).status_code == 403
    with TestClient(api) as owner:
        csrf = login(owner, "owner@example.test")
        assert select_bar(owner, ids["bar_one"], csrf).status_code == 200
        with factory() as db:
            db.get(Bar, ids["bar_one"]).is_active = False
            db.commit()
        for endpoint in ENDPOINTS:
            assert owner.get(endpoint).status_code == 403
