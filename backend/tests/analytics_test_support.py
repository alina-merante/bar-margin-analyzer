import datetime as dt
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.analytics import router as analytics_router
from app.routers.finance import router as finance_router
from app.settings import settings
from finance_test_support import finance_request


def api_request(db, method, path, *, params=None, payload=None):
    if "finance_client" in db.info:
        response = finance_request(db, method, path, params=params, payload=payload)
    else:
        from test_documents_cash_month import TEST_SESSION_TOKEN, _test_context

        context = _test_context(db)
        db.commit()
        app = FastAPI()
        app.include_router(analytics_router)
        app.include_router(finance_router)

        def override_db():
            with Session(db.get_bind()) as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as client:
            client.cookies.set(settings.cookie_name, TEST_SESSION_TOKEN)
            client.cookies.set("barmanager_csrf", "test-csrf")
            response = client.request(
                method, path, params=params, json=payload,
                headers={
                    "Origin": "http://localhost:5173",
                    "X-CSRF-Token": "test-csrf",
                    "X-Expected-Bar-ID": str(context.bar.id),
                },
            )
        db.expire_all()
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.json()["detail"])
    return response.json()


def monthly_pnl(db, start, end):
    next_month = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    assert start.day == 1 and end == next_month
    result = api_request(db, "GET", "/analytics/pnl", params={"month": start.strftime("%Y-%m")})
    return {key: Decimal(str(result[key])) for key in ("revenue", "expenses", "profit")}


def overview(month, db):
    return api_request(db, "GET", "/analytics/overview", params={"month": month})


def invoices_summary(db):
    return api_request(db, "GET", "/analytics/invoices-summary")


def expenses_by_category(month, db):
    return api_request(db, "GET", "/analytics/expenses-by-category", params={"month": month})


def link_payment_endpoint(invoice_id, payload, db):
    return api_request(
        db, "POST", f"/invoices/{invoice_id}/link-payment",
        payload=payload.model_dump(mode="json"),
    )
