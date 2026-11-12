import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import config
from app.database import Base, get_db
from app.models import Bar, MembershipRole, User, UserBarMembership
from app.routers.auth import router as auth_router
from app.routers.bar_context import router as bar_context_router
from app.routers import finance
from app.routers.finance import router as finance_router
from app.routers.analytics import router as analytics_router
from app.security import hash_password


ALLOWED_ORIGIN = "http://localhost:5173"
TEST_PASSWORD = "temporary-finance-test-password"


@pytest.fixture
def finance_http_env(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(config, "UPLOAD_BASE_PATH", str(root))
    for kind in ("documents", "previews", "invoices"):
        monkeypatch.setattr(config, f"UPLOAD_{kind.upper()}_DIR", str(root / kind))
    monkeypatch.setattr(finance, "UPLOAD_INVOICES_DIR", str(root / "invoices"))
    engine = create_engine(
        f"sqlite:///{tmp_path / 'finance-http.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _connection_record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_sessionmaker = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(bar_context_router)
    app.include_router(finance_router)
    app.include_router(analytics_router)

    def override_get_db():
        db = test_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with test_sessionmaker() as db:
        bar = Bar(name="Finance Test Bar")
        owner = User(
            email="finance-test-owner@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        db.add_all([bar, owner])
        db.flush()
        db.add(
            UserBarMembership(
                user_id=owner.id,
                bar_id=bar.id,
                role=MembershipRole.owner,
            )
        )
        db.commit()
        bar_id = bar.id

    try:
        with TestClient(app) as client:
            csrf_token = client.get("/auth/csrf").json()["csrf_token"]
            login = client.post(
                "/auth/login",
                headers={
                    "Origin": ALLOWED_ORIGIN,
                    "X-CSRF-Token": csrf_token,
                },
                json={
                    "email": "finance-test-owner@example.test",
                    "password": TEST_PASSWORD,
                },
            )
            assert login.status_code == 200
            csrf_token = login.json()["csrf_token"]
            selected = client.put(
                "/auth/active-bar",
                headers={
                    "Origin": ALLOWED_ORIGIN,
                    "X-CSRF-Token": csrf_token,
                },
                json={"bar_id": bar_id},
            )
            assert selected.status_code == 200
            yield {
                "bar_id": bar_id,
                "client": client,
                "csrf_token": csrf_token,
                "sessionmaker": test_sessionmaker,
            }
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def finance_request(db, method, path, *, payload=None, files=None, params=None):
    headers = {}
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        headers = {
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": db.info["csrf_token"],
        }
    db.commit()
    response = db.info["finance_client"].request(
        method,
        path,
        headers=headers,
        json=payload,
        files=files,
        params=params,
    )
    db.expire_all()
    db.rollback()
    return response


def finance_response(response):
    if response.status_code >= 400:
        detail = response.json().get("detail")
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()
