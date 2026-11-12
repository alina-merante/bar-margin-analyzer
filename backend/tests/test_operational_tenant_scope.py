import datetime as dt
import importlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, get_db
from app.models import (
    Bar,
    CashClosureIntake,
    CategoryRule,
    DailyCashClosure,
    Document,
    ExpenseCategory,
    MembershipRole,
    Product,
    SaleLine,
    Transaction,
    User,
    UserBarMembership,
)
from app.routers.auth import router as auth_router
from app.routers.bar_context import router as bar_context_router
from app.routers.cash_closures import router as cash_closures_router
from app.routers.categories import router as categories_router
from app.security import hash_password

documents_module = importlib.import_module("app.routers.documents")
imports_module = importlib.import_module("app.routers.imports")


ALLOWED_ORIGIN = "http://localhost:5173"
TEST_PASSWORD = "correct horse battery"


@pytest.fixture
def operational_environment(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'operational-scope.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_sessionmaker = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    api = FastAPI()
    for router in (
        auth_router,
        bar_context_router,
        categories_router,
        imports_module.router,
        cash_closures_router,
    ):
        api.include_router(router)

    def override_get_db():
        db = test_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    api.dependency_overrides[get_db] = override_get_db

    monkeypatch.setattr(documents_module, "ensure_upload_dirs", lambda: None)
    monkeypatch.setattr(
        documents_module,
        "get_document_path",
        lambda filename: str(tmp_path / filename),
    )
    monkeypatch.setattr(
        documents_module,
        "get_preview_path",
        lambda filename: str(tmp_path / filename),
    )
    monkeypatch.setattr(
        documents_module,
        "get_document_url",
        lambda filename: f"/uploads/documents/{filename}",
    )
    monkeypatch.setattr(
        documents_module,
        "get_preview_url",
        lambda filename: f"/uploads/previews/{filename}",
    )
    monkeypatch.setattr(
        documents_module,
        "create_text_preview_image",
        lambda **_kwargs: "/uploads/previews/test.png",
    )
    monkeypatch.setattr(
        imports_module,
        "create_bank_document",
        documents_module.create_bank_document,
    )

    with TestClient(api) as client:
        yield client, engine, test_sessionmaker, api
    engine.dispose()


def create_document(db, bar_id, filename, section="bank"):
    document = Document(
        bar_id=bar_id,
        month="2026-07",
        original_filename=filename,
        stored_filename=filename,
        section=section,
        document_type="CSV",
        category="Documento tabellare",
        result="Test document",
        file_url=f"/uploads/documents/{filename}",
        preview_url=f"/uploads/documents/{filename}",
        status="Elaborato",
    )
    db.add(document)
    db.flush()
    return document


def seed_bars(sessionmaker_for_test):
    with sessionmaker_for_test() as db:
        bar_one = Bar(name="Bar Uno")
        bar_two = Bar(name="Bar Due")
        owner = User(
            email="owner@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        manager = User(
            email="manager@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        staff = User(
            email="staff@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        outsider = User(
            email="outsider@example.test",
            password_hash=hash_password(TEST_PASSWORD),
        )
        db.add_all([bar_one, bar_two, owner, manager, staff, outsider])
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
        return {
            "bar_one": bar_one.id,
            "bar_two": bar_two.id,
            "owner": owner.id,
            "manager": manager.id,
            "staff": staff.id,
            "outsider": outsider.id,
        }


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


def upload(client, path, csrf_token, filename, content, data=None):
    return client.post(
        path,
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        files={"file": (filename, content, "text/csv")},
        data=data or {},
    )


def test_categories_and_pos_import_are_scoped_by_selected_bar(operational_environment):
    client, _engine, test_sessionmaker, _api = operational_environment
    ids = seed_bars(test_sessionmaker)
    csrf_token = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200

    category_one = client.post(
        "/categories",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"name": "Food"},
    )
    assert category_one.status_code == 200
    rule_one = client.post(
        "/rules",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"keyword": "grocery", "category_id": category_one.json()["id"]},
    )
    assert rule_one.status_code == 200
    first_pos = upload(
        client,
        "/imports/pos-csv",
        csrf_token,
        "sales.csv",
        b"date,product,qty,total\n2026-07-01,Coffee,2,8.00\n",
        {"bar_id": str(ids["bar_two"])},
    )
    assert first_pos.status_code == 200

    assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200
    category_two = client.post(
        "/categories",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"name": "Food"},
    )
    assert category_two.status_code == 200
    rule_two = client.post(
        "/rules",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"keyword": "grocery", "category_id": category_two.json()["id"]},
    )
    assert rule_two.status_code == 200
    second_pos = upload(
        client,
        "/imports/pos-csv",
        csrf_token,
        "sales.csv",
        b"date,product,qty,total\n2026-07-01,Coffee,1,4.00\n",
    )
    assert second_pos.status_code == 200

    assert [row["name"] for row in client.get("/categories").json()] == ["Food"]
    assert len(client.get("/rules").json()) == 1
    with test_sessionmaker() as db:
        products = db.scalars(select(Product).order_by(Product.bar_id)).all()
        sale_lines = db.scalars(select(SaleLine).order_by(SaleLine.bar_id)).all()
        assert [(product.bar_id, product.name) for product in products] == [
            (ids["bar_one"], "Coffee"),
            (ids["bar_two"], "Coffee"),
        ]
        assert [(line.bar_id, line.product.bar_id) for line in sale_lines] == [
            (ids["bar_one"], ids["bar_one"]),
            (ids["bar_two"], ids["bar_two"]),
        ]


def test_bank_import_deduplication_category_and_document_links_are_tenant_scoped(
    operational_environment,
):
    client, _engine, test_sessionmaker, _api = operational_environment
    ids = seed_bars(test_sessionmaker)
    csrf_token = login(client, "owner@example.test")

    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    category_one = client.post(
        "/categories",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"name": "Food"},
    ).json()
    assert client.post(
        "/rules",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"keyword": "grocery", "category_id": category_one["id"]},
    ).status_code == 200
    with test_sessionmaker() as db:
        foreign_category = ExpenseCategory(
            bar_id=ids["bar_two"],
            name="Foreign category",
        )
        db.add(foreign_category)
        db.commit()
        foreign_category_id = foreign_category.id
    cross_tenant_category_rule = client.post(
        "/rules",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"keyword": "foreign", "category_id": foreign_category_id},
    )
    assert cross_tenant_category_rule.status_code == 404

    bank_csv = b"date,description,amount\n2026-07-03,Grocery purchase,12.00\n"
    first = upload(
        client,
        "/imports/bank-csv",
        csrf_token,
        "bank.csv",
        bank_csv,
        {"month": "2026-07"},
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"imported_rows": 1, "skipped_rows": 0}
    duplicate = upload(
        client,
        "/imports/bank-csv",
        csrf_token,
        "bank.csv",
        bank_csv,
        {"month": "2026-07"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json() == {"imported_rows": 0, "skipped_rows": 1}

    with test_sessionmaker() as db:
        bar_two_document = create_document(
            db,
            ids["bar_two"],
            "other-bar.csv",
        )
        db.commit()
        other_document_id = bar_two_document.id

    cross_tenant_document = upload(
        client,
        "/imports/bank-csv",
        csrf_token,
        "bank.csv",
        bank_csv,
        {"document_id": str(other_document_id)},
    )
    assert cross_tenant_document.status_code == 404

    assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200
    category_two = client.post(
        "/categories",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"name": "Food"},
    ).json()
    assert client.post(
        "/rules",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"keyword": "grocery", "category_id": category_two["id"]},
    ).status_code == 200
    second_bar_import = upload(
        client,
        "/imports/bank-csv",
        csrf_token,
        "bank.csv",
        bank_csv,
        {"month": "2026-07"},
    )
    assert second_bar_import.status_code == 200
    assert second_bar_import.json() == {"imported_rows": 1, "skipped_rows": 0}

    with test_sessionmaker() as db:
        transactions = db.scalars(
            select(Transaction).order_by(Transaction.bar_id)
        ).all()
        assert len(transactions) == 2
        assert [row.bar_id for row in transactions] == [
            ids["bar_one"],
            ids["bar_two"],
        ]
        assert [row.category.bar_id for row in transactions] == [
            ids["bar_one"],
            ids["bar_two"],
        ]
        documents = db.scalars(
            select(Document).where(Document.section == "bank")
        ).all()
        assert {document.bar_id for document in documents} == {
            ids["bar_one"],
            ids["bar_two"],
        }
        assert all(
            transaction.document_id is None
            or db.get(Document, transaction.document_id).bar_id == transaction.bar_id
            for transaction in transactions
        )


def test_cash_closure_review_is_scoped_and_unassigned_ocr_data_is_hidden(
    operational_environment,
):
    client, _engine, test_sessionmaker, _api = operational_environment
    ids = seed_bars(test_sessionmaker)
    with test_sessionmaker() as db:
        categories = [
            ExpenseCategory(bar_id=ids["bar_one"], name="Cash"),
            ExpenseCategory(bar_id=ids["bar_two"], name="Cash"),
        ]
        db.add_all(categories)
        db.flush()
        for index, bar_id in enumerate((ids["bar_one"], ids["bar_two"]), start=1):
            document = create_document(db, bar_id, f"cash-{index}.pdf", section="cash")
            db.add(
                CashClosureIntake(
                    bar_id=bar_id,
                    document_id=document.id,
                    source_sha256=f"{index:064x}",
                    classification="SAVE_FOR_REVIEW",
                    status="pending",
                    date=dt.date(2026, 7, 7),
                    closure_number="01",
                    total_amount=Decimal("100.00"),
                    cash_amount=Decimal("60.00"),
                    card_amount=Decimal("40.00"),
                    ocr_values={},
                    anomalies=[],
                )
            )
        legacy_document = create_document(db, None, "legacy.pdf", section="cash")
        db.add(
            CashClosureIntake(
                bar_id=None,
                document_id=legacy_document.id,
                source_sha256="f" * 64,
                classification="SAVE_FOR_REVIEW",
                status="pending",
                date=dt.date(2026, 7, 8),
                closure_number="legacy",
                total_amount=Decimal("50.00"),
                cash_amount=None,
                card_amount=None,
                ocr_values={},
                anomalies=[],
            )
        )
        db.commit()
        intake_ids = {
            row.bar_id: row.id
            for row in db.scalars(select(CashClosureIntake)).all()
        }
        legacy_intake_id = intake_ids.pop(None)

    csrf_token = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200
    reviews_one = client.get("/cash-closures/review")
    assert reviews_one.status_code == 200
    assert [row["id"] for row in reviews_one.json()] == [intake_ids[ids["bar_one"]]]
    assert client.get(
        f"/cash-closures/review/{intake_ids[ids['bar_two']]}"
    ).status_code == 404
    assert client.get(
        f"/cash-closures/review/{legacy_intake_id}"
    ).status_code == 404

    approve_one = client.post(
        f"/cash-closures/review/{intake_ids[ids['bar_one']]}/approve",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
    )
    assert approve_one.status_code == 200, approve_one.text
    with test_sessionmaker() as db:
        closure_one = db.get(DailyCashClosure, approve_one.json()["closure_id"])
        assert closure_one is not None
        assert closure_one.bar_id == ids["bar_one"]

    assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200
    reviews_two = client.get("/cash-closures/review")
    assert reviews_two.status_code == 200
    assert [row["id"] for row in reviews_two.json()] == [intake_ids[ids["bar_two"]]]
    approve_two = client.post(
        f"/cash-closures/review/{intake_ids[ids['bar_two']]}/approve",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
    )
    assert approve_two.status_code == 200, approve_two.text
    with test_sessionmaker() as db:
        closures = db.scalars(select(DailyCashClosure)).all()
        assert len(closures) == 2
        assert {closure.bar_id for closure in closures} == {
            ids["bar_one"],
            ids["bar_two"],
        }


def test_role_authentication_csrf_and_active_bar_fail_closed(
    operational_environment,
):
    client, _engine, test_sessionmaker, api = operational_environment
    ids = seed_bars(test_sessionmaker)

    unauthenticated = client.get("/categories")
    assert unauthenticated.status_code == 401
    staff_client = TestClient(api)
    outsider_client = TestClient(api)
    try:
        staff_csrf = login(staff_client, "staff@example.test")
        assert select_bar(staff_client, ids["bar_one"], staff_csrf).status_code == 200
        assert staff_client.get("/categories").status_code == 403
        assert staff_client.get("/cash-closures/review").status_code == 200
        assert upload(
            staff_client,
            "/imports/pos-csv",
            staff_csrf,
            "sales.csv",
            b"date,product,qty,total\n2026-07-01,Coffee,1,4\n",
        ).status_code == 403

        outsider_csrf = login(outsider_client, "outsider@example.test")
        assert select_bar(outsider_client, ids["bar_one"], outsider_csrf).status_code == 403
        assert outsider_client.get("/categories").status_code == 409

        manager_csrf = login(client, "manager@example.test")
        assert client.get("/categories").status_code == 409
        no_csrf = client.post("/categories", json={"name": "Unauthorized"})
        assert no_csrf.status_code == 403
        assert select_bar(client, ids["bar_one"], manager_csrf).status_code == 200
        missing_origin = client.post(
            "/categories",
            headers={"X-CSRF-Token": manager_csrf},
            json={"name": "No Origin"},
        )
        assert missing_origin.status_code == 403
        assert client.post(
            "/categories",
            headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": manager_csrf},
            json={"name": "Manager Category"},
        ).status_code == 200

        with test_sessionmaker() as db:
            membership = db.scalar(
                select(UserBarMembership).where(
                    UserBarMembership.user_id == ids["manager"],
                    UserBarMembership.bar_id == ids["bar_one"],
                )
            )
            assert membership is not None
            db.delete(membership)
            db.commit()
        assert client.get("/categories").status_code == 403
    finally:
        staff_client.close()
        outsider_client.close()


def test_scoped_indexes_allow_shared_names_and_enforce_legacy_null_uniqueness(
    operational_environment,
):
    _client, _engine, test_sessionmaker, _api = operational_environment
    ids = seed_bars(test_sessionmaker)
    with test_sessionmaker() as db:
        db.add_all(
            [
                Product(bar_id=ids["bar_one"], name="Shared"),
                Product(bar_id=ids["bar_two"], name="Shared"),
                ExpenseCategory(bar_id=ids["bar_one"], name="Shared"),
                ExpenseCategory(bar_id=ids["bar_two"], name="Shared"),
                Product(bar_id=None, name="Legacy Unique"),
                ExpenseCategory(bar_id=None, name="Legacy Unique"),
            ]
        )
        db.commit()
        db.add(Product(bar_id=None, name="Legacy Unique"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(ExpenseCategory(bar_id=None, name="Legacy Unique"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
