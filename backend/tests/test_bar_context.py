import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.bar_context import (
    BarPermission,
    require_bar_permission,
    require_manager_or_owner,
    require_owner,
)
from app.database import Base, get_db
from app.models import (
    AuthSession,
    Bar,
    MembershipRole,
    User,
    UserBarMembership,
)
from app.routers.auth import router as auth_router
from app.routers.bar_context import router as bar_context_router
from app.security import hash_password


ALLOWED_ORIGIN = "http://localhost:5173"
TEST_PASSWORD = "correct horse battery"


def permission_probe(permission):
    def endpoint(context=Depends(require_bar_permission(permission))):
        return {"bar_id": context.bar.id, "role": context.role.value}

    return endpoint


@pytest.fixture
def context_environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bar-context.db'}")

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
    api.include_router(auth_router)
    api.include_router(bar_context_router)

    def owner_probe():
        return {"ok": True}

    def manager_probe():
        return {"ok": True}

    api.add_api_route(
        "/test/owner",
        owner_probe,
        methods=["GET"],
        dependencies=[Depends(require_owner)],
    )
    api.add_api_route(
        "/test/manager",
        manager_probe,
        methods=["GET"],
        dependencies=[Depends(require_manager_or_owner)],
    )
    api.add_api_route(
        "/test/operate",
        permission_probe(BarPermission.OPERATE),
        methods=["GET"],
    )
    api.add_api_route(
        "/test/users",
        permission_probe(BarPermission.MANAGE_USERS),
        methods=["GET"],
    )
    api.add_api_route(
        "/test/documents",
        permission_probe(BarPermission.READ_DOCUMENTS),
        methods=["GET"],
    )
    api.add_api_route(
        "/test/upload",
        permission_probe(BarPermission.UPLOAD_DOCUMENTS),
        methods=["GET"],
    )
    api.add_api_route(
        "/test/ocr",
        permission_probe(BarPermission.REVIEW_OCR),
        methods=["GET"],
    )
    api.add_api_route(
        "/test/delete",
        permission_probe(BarPermission.DELETE_RECORDS),
        methods=["GET"],
    )
    api.add_api_route(
        "/test/payments",
        permission_probe(BarPermission.MANAGE_PAYMENTS),
        methods=["GET"],
    )

    def override_get_db():
        db = test_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    api.dependency_overrides[get_db] = override_get_db
    with TestClient(api) as client:
        yield client, engine, test_sessionmaker, api
    engine.dispose()


def seed_memberships(sessionmaker_for_test):
    with sessionmaker_for_test() as db:
        bar_one = Bar(name="Bar Uno")
        bar_two = Bar(name="Bar Due")
        inactive_bar = Bar(name="Bar Inattivo", is_active=False)
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
        db.add_all(
            [
                bar_one,
                bar_two,
                inactive_bar,
                owner,
                manager,
                staff,
                outsider,
            ]
        )
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
                    role=MembershipRole.manager,
                ),
                UserBarMembership(
                    user_id=owner.id,
                    bar_id=inactive_bar.id,
                    role=MembershipRole.owner,
                ),
                UserBarMembership(
                    user_id=manager.id,
                    bar_id=bar_two.id,
                    role=MembershipRole.manager,
                ),
                UserBarMembership(
                    user_id=staff.id,
                    bar_id=bar_two.id,
                    role=MembershipRole.staff,
                ),
            ]
        )
        db.commit()
        return {
            "bar_one": bar_one.id,
            "bar_two": bar_two.id,
            "inactive_bar": inactive_bar.id,
            "owner": owner.id,
            "manager": manager.id,
            "staff": staff.id,
            "outsider": outsider.id,
        }


def login(client, email):
    csrf_token = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def select_bar(client, bar_id, csrf_token, *, origin=ALLOWED_ORIGIN):
    headers = {"X-CSRF-Token": csrf_token}
    if origin is not None:
        headers["Origin"] = origin
    return client.put(
        "/auth/active-bar",
        headers=headers,
        json={"bar_id": bar_id},
    )


def test_user_can_select_multiple_bars_with_different_roles(context_environment):
    client, _engine, test_sessionmaker, _api = context_environment
    ids = seed_memberships(test_sessionmaker)
    csrf_token = login(client, "owner@example.test")

    bars = client.get("/auth/bars")
    assert bars.status_code == 200
    assert bars.headers["cache-control"] == "no-store"
    assert [
        (bar["id"], bar["role"], bar["selected"])
        for bar in bars.json()
    ] == [
        (ids["bar_two"], "manager", False),
        (ids["bar_one"], "owner", False),
    ]

    first_selection = select_bar(client, ids["bar_one"], csrf_token)
    assert first_selection.status_code == 200
    assert first_selection.json() == {
        "id": ids["bar_one"],
        "name": "Bar Uno",
        "role": "owner",
    }
    assert client.get("/auth/active-bar").json()["id"] == ids["bar_one"]

    second_selection = select_bar(client, ids["bar_two"], csrf_token)
    assert second_selection.status_code == 200
    assert second_selection.json()["role"] == "manager"
    assert client.get("/auth/active-bar").json()["id"] == ids["bar_two"]
    assert client.get("/auth/bars").json()[0]["selected"] is True

    with test_sessionmaker() as db:
        auth_session = db.scalar(select(AuthSession))
        assert auth_session is not None
        assert auth_session.active_bar_id == ids["bar_two"]


def test_selection_rejects_nonmember_and_inactive_bars(context_environment):
    client, _engine, test_sessionmaker, _api = context_environment
    ids = seed_memberships(test_sessionmaker)
    csrf_token = login(client, "outsider@example.test")

    unauthorized = select_bar(client, ids["bar_one"], csrf_token)
    inactive = select_bar(client, ids["inactive_bar"], csrf_token)
    assert unauthorized.status_code == 403
    assert inactive.status_code == 403
    assert client.get("/auth/active-bar").json() is None


def test_active_bar_is_independent_for_each_session(context_environment):
    _client, _engine, test_sessionmaker, api = context_environment
    ids = seed_memberships(test_sessionmaker)
    first_client = TestClient(api)
    second_client = TestClient(api)
    try:
        first_csrf = login(first_client, "owner@example.test")
        second_csrf = login(second_client, "owner@example.test")
        assert select_bar(first_client, ids["bar_one"], first_csrf).status_code == 200
        assert select_bar(second_client, ids["bar_two"], second_csrf).status_code == 200
        assert first_client.get("/auth/active-bar").json()["id"] == ids["bar_one"]
        assert second_client.get("/auth/active-bar").json()["id"] == ids["bar_two"]
    finally:
        first_client.close()
        second_client.close()


def test_revoked_membership_blocks_selected_bar(context_environment):
    client, _engine, test_sessionmaker, _api = context_environment
    ids = seed_memberships(test_sessionmaker)
    csrf_token = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf_token).status_code == 200

    with test_sessionmaker() as db:
        membership = db.scalar(
            select(UserBarMembership).where(
                UserBarMembership.user_id == ids["owner"],
                UserBarMembership.bar_id == ids["bar_one"],
            )
        )
        assert membership is not None
        db.delete(membership)
        db.commit()

    assert client.get("/auth/active-bar").status_code == 403
    assert client.get("/test/owner").status_code == 403


def test_bar_selection_requires_csrf_and_trusted_origin(context_environment):
    client, _engine, test_sessionmaker, _api = context_environment
    ids = seed_memberships(test_sessionmaker)
    csrf_token = login(client, "owner@example.test")

    missing_csrf = client.put(
        "/auth/active-bar",
        headers={"Origin": ALLOWED_ORIGIN},
        json={"bar_id": ids["bar_one"]},
    )
    missing_origin = select_bar(client, ids["bar_one"], csrf_token, origin=None)
    untrusted_origin = select_bar(
        client,
        ids["bar_one"],
        csrf_token,
        origin="https://attacker.example",
    )
    assert missing_csrf.status_code == 403
    assert missing_origin.status_code == 403
    assert untrusted_origin.status_code == 403


def test_role_permissions_match_owner_manager_and_staff(context_environment):
    owner_client, _engine, test_sessionmaker, api = context_environment
    ids = seed_memberships(test_sessionmaker)
    manager_client = TestClient(api)
    staff_client = TestClient(api)
    try:
        owner_csrf = login(owner_client, "owner@example.test")
        manager_csrf = login(manager_client, "manager@example.test")
        staff_csrf = login(staff_client, "staff@example.test")
        assert select_bar(owner_client, ids["bar_one"], owner_csrf).status_code == 200
        for client, csrf_token in (
            (manager_client, manager_csrf),
            (staff_client, staff_csrf),
        ):
            assert select_bar(client, ids["bar_two"], csrf_token).status_code == 200

        assert owner_client.get("/test/users").status_code == 200
        assert owner_client.get("/test/payments").status_code == 200

        assert manager_client.get("/test/operate").status_code == 200
        assert manager_client.get("/test/payments").status_code == 200
        assert manager_client.get("/test/users").status_code == 403
        assert manager_client.get("/test/owner").status_code == 403
        assert manager_client.get("/test/manager").status_code == 200

        for path in ("/test/documents", "/test/upload", "/test/ocr"):
            assert staff_client.get(path).status_code == 200
        for path in ("/test/operate", "/test/delete", "/test/payments", "/test/users"):
            assert staff_client.get(path).status_code == 403
        assert staff_client.get("/test/manager").status_code == 403
    finally:
        manager_client.close()
        staff_client.close()
