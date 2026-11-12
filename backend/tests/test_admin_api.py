import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.bar_context import get_active_bar_context
from app.database import Base, get_db
from app.models import AdminAudit, AdminWriteLock, AuthSession, Bar, MembershipPermission, MembershipRole, User, UserBarMembership
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.bar_context import router as bar_router
from app.security import hash_password, token_hash
from app.settings import settings

ORIGIN = "http://localhost:5173"
PASSWORD = "a temporary secure password"


@pytest.fixture
def admin_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory.begin() as db:
        db.add(AdminWriteLock(id=1))
        bar = Bar(name="Bar A")
        users = [
            User(email=f"{role}@example.test", password_hash=hash_password(PASSWORD), is_global_admin=role == "admin")
            for role in ("admin", "owner", "manager", "staff")
        ]
        db.add_all([bar, *users])
        db.flush()
        for user, role in zip(users[1:], (MembershipRole.owner, MembershipRole.manager, MembershipRole.staff)):
            db.add(UserBarMembership(user_id=user.id, bar_id=bar.id, role=role))
        ids = {user.email.split("@")[0]: user.id for user in users}
        ids["bar"] = bar.id

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(bar_router)
    app.include_router(admin_router)

    @app.get("/test-tenant")
    def tenant(context=Depends(get_active_bar_context)):
        return {"bar_id": context.bar.id}

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, factory, ids
    engine.dispose()


def login(client, role):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post("/auth/login", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                           json={"email": f"{role}@example.test", "password": PASSWORD})
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def test_admin_bar_and_account_crud_and_audit(admin_env):
    client, factory, ids = admin_env
    headers = login(client, "admin")
    assert client.get("/admin/bars").status_code == 200
    assert client.get("/test-tenant", headers={"X-Expected-Bar-ID": str(ids["bar"])}).status_code == 409
    assert client.get("/admin/bars").headers["cache-control"] == "private, no-store"
    bar = client.post("/admin/bars", headers=headers, json={"name": "  Bar B  "})
    assert bar.status_code == 201 and bar.json()["name"] == "Bar B"
    bar_id = bar.json()["id"]
    assert client.patch(f"/admin/bars/{bar_id}", headers=headers, json={"is_active": False}).status_code == 200
    assert client.get(f"/admin/bars/{bar_id}").json()["is_active"] is False
    assert len(client.get("/admin/bars").json()) == 2
    created = client.post("/admin/users", headers=headers, json={"email": " New@Example.Test "})
    assert created.status_code == 201
    assert created.json()["email"] == "new@example.test"
    assert created.json()["password_setup_required"] is True
    assert "password" not in created.json() and "password_hash" not in str(client.get("/admin/users").json())
    assert client.post("/admin/users", headers=headers, json={"email": "NEW@example.test"}).status_code == 409
    user_id = created.json()["id"]
    assert client.patch(f"/admin/users/{user_id}", headers=headers, json={"email": "updated@example.test"}).status_code == 200
    assert client.get(f"/admin/users/{user_id}").json()["email"] == "updated@example.test"
    with factory() as db:
        audits = db.scalars(select(AdminAudit).order_by(AdminAudit.id)).all()
        assert [row.action for row in audits] == ["bar.create", "bar.update", "user.create", "user.update"]
        assert all(row.actor_id == ids["admin"] for row in audits)
        assert "password" not in str([row.changes for row in audits])


@pytest.mark.parametrize("role", ["owner", "manager", "staff"])
def test_non_admin_roles_denied_all_administration(admin_env, role):
    client, _, ids = admin_env
    headers = login(client, role)
    for path in ("/admin/bars", f"/admin/bars/{ids['bar']}", "/admin/users",
                 f"/admin/users/{ids[role]}", f"/admin/bars/{ids['bar']}/memberships"):
        assert client.get(path).status_code == 403
    assert client.post("/admin/bars", headers=headers, json={"name": "No"}).status_code == 403
    assert client.patch(f"/admin/users/{ids[role]}", headers=headers, json={"is_active": False}).status_code == 403
    assert client.post("/admin/users", headers=headers, json={"email": "new@example.test"}).status_code == 403
    assert client.patch(f"/admin/bars/{ids['bar']}", headers=headers, json={"is_active": False}).status_code == 403
    assert client.post(f"/admin/bars/{ids['bar']}/memberships", headers=headers,
                       json={"user_id": ids[role], "role": "owner"}).status_code == 403
    assert client.patch(f"/admin/bars/{ids['bar']}/memberships/{ids[role]}", headers=headers,
                        json={"role": "owner"}).status_code == 403
    assert client.delete(f"/admin/bars/{ids['bar']}/memberships/{ids[role]}", headers=headers).status_code == 403


def test_membership_revocation_blocks_active_session_and_preserves_bar(admin_env):
    client, factory, ids = admin_env
    headers = login(client, "staff")
    assert client.put("/auth/active-bar", headers=headers, json={"bar_id": ids["bar"]}).status_code == 200
    old_cookies = dict(client.cookies)
    assert client.get("/test-tenant", headers={"X-Expected-Bar-ID": str(ids["bar"])}).status_code == 200
    assert client.get("/test-tenant").status_code == 428
    assert client.get("/test-tenant", headers={"X-Expected-Bar-ID": "999"}).status_code == 409
    client.cookies.clear()
    admin_headers = login(client, "admin")
    bar_id = client.post("/admin/bars", headers=admin_headers, json={"name": "Bar B"}).json()["id"]
    assign = {"user_id": ids["staff"], "role": "staff"}
    assert client.post(f"/admin/bars/{bar_id}/memberships", headers=admin_headers, json=assign).status_code == 201
    assert client.post(f"/admin/bars/{bar_id}/memberships", headers=admin_headers, json=assign).status_code == 409
    assert client.patch(f"/admin/bars/{bar_id}/memberships/{ids['staff']}", headers=admin_headers,
                        json={"role": "owner"}).status_code == 200
    assert client.patch(f"/admin/bars/{bar_id}/memberships/{ids['staff']}", headers=admin_headers,
                        json={"role": "manager"}).status_code == 422
    assert client.delete(f"/admin/bars/{ids['bar']}/memberships/{ids['staff']}", headers=admin_headers).status_code == 200
    memberships = client.get(f"/admin/bars/{bar_id}/memberships").json()
    assert len(memberships) == 1
    assert memberships[0]["user"]["email"] == "staff@example.test"
    client.cookies.clear()
    client.cookies.update(old_cookies)
    assert client.get("/test-tenant", headers={"X-Expected-Bar-ID": str(ids["bar"])}).status_code == 403
    with factory() as db:
        assert db.get(Bar, ids["bar"]) is not None
        assert db.scalar(select(UserBarMembership).where(
            UserBarMembership.user_id == ids["staff"], UserBarMembership.bar_id == bar_id
        )) is not None


def test_csrf_privilege_escalation_last_admin_and_secrets(admin_env):
    client, factory, ids = admin_env
    assert client.get("/admin/bars").status_code == 401
    headers = login(client, "admin")
    assert client.post("/admin/bars", json={"name": "No"}).status_code == 403
    assert client.post("/admin/bars", headers={**headers, "Origin": "https://evil.example"},
                       json={"name": "No"}).status_code == 403
    for path, data in [
        ("/admin/users", {"email": "a@example.test", "is_global_admin": True}),
        (f"/admin/users/{ids['staff']}", {"is_global_admin": True}),
        (f"/admin/users/{ids['admin']}", {"is_global_admin": True}),
    ]:
        response = client.post(path, headers=headers, json=data) if path == "/admin/users" else client.patch(path, headers=headers, json=data)
        assert response.status_code == 422
    secret = "never-return-this-secret"
    response = client.post("/admin/users", headers=headers, json={"email": "a@example.test", "password": secret})
    assert response.status_code == 422 and secret not in response.text
    assert client.patch(f"/admin/users/{ids['admin']}", headers=headers, json={"is_active": False}).status_code == 409
    with factory() as db:
        assert db.get(User, ids["admin"]).is_active
        assert not db.get(User, ids["staff"]).is_global_admin
        assert db.scalars(select(AdminAudit)).all() == []


def test_role_change_clears_grants_and_legacy_manager_is_not_converted(admin_env):
    client, factory, ids = admin_env
    with factory.begin() as db:
        membership = db.scalar(select(UserBarMembership).where(UserBarMembership.user_id == ids["manager"]))
        db.add(MembershipPermission(membership=membership, permission="invoices.upload"))
    headers = login(client, "admin")
    url = f"/admin/bars/{ids['bar']}/memberships/{ids['manager']}"
    assert client.get(f"/admin/bars/{ids['bar']}/memberships").json()[1]["role"] == "manager"
    assert client.patch(url, headers=headers, json={"role": "staff"}).status_code == 200
    with factory() as db:
        membership = db.scalar(select(UserBarMembership).where(UserBarMembership.user_id == ids["manager"]))
        assert not membership.permissions
        audit = db.scalar(select(AdminAudit).where(AdminAudit.action == "membership.role"))
        assert audit.changes == {"role": {"from": "manager", "to": "staff"}}


def test_deactivated_bar_and_user_block_existing_sessions_without_deleting_membership(admin_env):
    client, factory, ids = admin_env
    staff_headers = login(client, "staff")
    assert client.put("/auth/active-bar", headers=staff_headers, json={"bar_id": ids["bar"]}).status_code == 200
    staff_cookies = dict(client.cookies)
    client.cookies.clear()
    admin_headers = login(client, "admin")
    admin_cookies = dict(client.cookies)
    assert client.patch(f"/admin/bars/{ids['bar']}", headers=admin_headers, json={"is_active": False}).status_code == 200
    assert len(client.get(f"/admin/bars/{ids['bar']}/memberships").json()) == 3
    client.cookies.clear()
    client.cookies.update(staff_cookies)
    assert client.get("/test-tenant", headers={"X-Expected-Bar-ID": str(ids["bar"])}).status_code == 403
    client.cookies.clear()
    client.cookies.update(admin_cookies)
    assert client.patch(f"/admin/users/{ids['staff']}", headers=admin_headers, json={"is_active": False}).status_code == 200
    client.cookies.clear()
    client.cookies.update(staff_cookies)
    assert client.get("/test-tenant", headers={"X-Expected-Bar-ID": str(ids["bar"])}).status_code == 401
    with factory() as db:
        assert db.get(Bar, ids["bar"]) is not None
        assert db.scalar(select(UserBarMembership).where(
            UserBarMembership.user_id == ids["staff"], UserBarMembership.bar_id == ids["bar"]
        )) is not None


def test_deactivation_revokes_all_devices_even_after_reactivation(admin_env):
    client, factory, ids = admin_env
    with TestClient(client.app) as first, TestClient(client.app) as second, TestClient(client.app) as other:
        login(first, "staff")
        login(second, "staff")
        login(other, "manager")
        cookies = [dict(first.cookies), dict(second.cookies)]
        hashes = [token_hash(cookie[settings.cookie_name]) for cookie in cookies]
        other_hash = token_hash(other.cookies[settings.cookie_name])
        headers = login(client, "admin")

        assert client.patch(f"/admin/users/{ids['staff']}", headers=headers, json={"is_active": False}).status_code == 200
        with factory() as db:
            sessions = db.scalars(select(AuthSession).where(AuthSession.token_hash.in_(hashes))).all()
            assert len(sessions) == 2 and all(session.revoked_at is not None for session in sessions)
            assert db.scalar(select(AuthSession).where(AuthSession.token_hash == other_hash)).revoked_at is None
            audit = db.scalar(select(AdminAudit).where(AdminAudit.action == "user.update"))
            assert audit.changes["sessions_revoked"] == 2
        assert all(device.get("/auth/session").status_code == 401 for device in (first, second))
        assert other.get("/auth/session").status_code == 200
        assert client.patch(f"/admin/users/{ids['staff']}", headers=headers, json={"is_active": True}).status_code == 200
        assert all(device.get("/auth/session").status_code == 401 for device in (first, second))
        for device, cookie in zip((first, second), cookies):
            device.cookies.clear()
            device.cookies.update(cookie)
            assert device.get("/auth/session").status_code == 401
        first.cookies.clear()
        login(first, "staff")
        assert first.get("/auth/session").status_code == 200


def test_failed_deactivation_rolls_back_status_sessions_and_audit(admin_env, monkeypatch):
    from app.routers import admin

    client, factory, ids = admin_env
    with TestClient(client.app) as staff:
        login(staff, "staff")
        headers = login(client, "admin")

        def fail_after_flush(db, *_args, **_kwargs):
            db.flush()
            raise RuntimeError("simulated audit failure")

        monkeypatch.setattr(admin, "audit", fail_after_flush)
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            client.patch(f"/admin/users/{ids['staff']}", headers=headers, json={"is_active": False})
        with factory() as db:
            assert db.get(User, ids["staff"]).is_active
            session = db.scalar(select(AuthSession).where(AuthSession.user_id == ids["staff"]))
            assert session.revoked_at is None
            assert db.scalars(select(AdminAudit)).all() == []
        assert staff.get("/auth/session").status_code == 200


def test_last_admin_rejection_does_not_revoke_sessions(admin_env):
    client, factory, ids = admin_env
    with TestClient(client.app) as second:
        login(second, "admin")
        headers = login(client, "admin")
        assert client.patch(f"/admin/users/{ids['admin']}", headers=headers, json={"is_active": False}).status_code == 409
        with factory() as db:
            sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == ids["admin"])).all()
            assert len(sessions) == 2 and all(session.revoked_at is None for session in sessions)
        assert client.get("/auth/session").status_code == 200
        assert second.get("/auth/session").status_code == 200


def test_repeated_deactivation_revokes_preexisting_unrevoked_sessions(admin_env):
    client, factory, ids = admin_env
    with TestClient(client.app) as staff:
        login(staff, "staff")
        with factory.begin() as db:
            db.get(User, ids["staff"]).is_active = False
        headers = login(client, "admin")
        assert client.patch(f"/admin/users/{ids['staff']}", headers=headers, json={"is_active": False}).status_code == 200
        with factory() as db:
            assert db.scalar(select(AuthSession).where(AuthSession.user_id == ids["staff"])).revoked_at is not None
        assert client.patch(f"/admin/users/{ids['staff']}", headers=headers, json={"is_active": True}).status_code == 200
        assert staff.get("/auth/session").status_code == 401


def test_admin_self_deactivation_revokes_all_own_sessions(admin_env):
    client, factory, ids = admin_env
    with factory.begin() as db:
        db.get(User, ids["owner"]).is_global_admin = True
    with TestClient(client.app) as second, TestClient(client.app) as other_admin:
        login(second, "admin")
        other_headers = login(other_admin, "owner")
        headers = login(client, "admin")
        assert client.patch(f"/admin/users/{ids['admin']}", headers=headers, json={"is_active": False}).status_code == 200
        assert other_admin.patch(f"/admin/users/{ids['admin']}", headers=other_headers,
                                 json={"is_active": True}).status_code == 200
        assert client.get("/auth/session").status_code == 401
        assert second.get("/auth/session").status_code == 401
        with factory() as db:
            sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == ids["admin"])).all()
            assert len(sessions) == 2 and all(session.revoked_at is not None for session in sessions)


def test_login_racing_deactivation_on_sqlite(admin_env, monkeypatch):
    from app.routers import auth as auth_module

    client, factory, ids = admin_env
    headers = login(client, "admin")
    engine = factory.kw["bind"]
    login_checked = Event()
    admin_attempting_lock = Event()
    finish_login = Event()
    original_verify = auth_module.verify_password

    def paused_verify(password, password_hash):
        result = original_verify(password, password_hash)
        login_checked.set()
        if not finish_login.wait(15):
            raise TimeoutError("concurrent deactivation did not reach admin lock")
        return result

    def signal_admin_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("UPDATE admin_write_lock"):
            admin_attempting_lock.set()

    monkeypatch.setattr(auth_module, "verify_password", paused_verify)
    event.listen(engine, "before_cursor_execute", signal_admin_lock)
    try:
        with TestClient(client.app) as staff:
            csrf = staff.get("/auth/csrf").json()["csrf_token"]
            with ThreadPoolExecutor(max_workers=2) as pool:
                login_future = pool.submit(
                    staff.post, "/auth/login",
                    headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                    json={"email": "staff@example.test", "password": PASSWORD},
                )
                try:
                    assert login_checked.wait(15)
                    deactivate_future = pool.submit(
                        client.patch, f"/admin/users/{ids['staff']}",
                        headers=headers, json={"is_active": False},
                    )
                    assert admin_attempting_lock.wait(15)
                finally:
                    finish_login.set()
                assert login_future.result(timeout=15).status_code == 200
                assert deactivate_future.result(timeout=15).status_code == 200
            assert client.patch(f"/admin/users/{ids['staff']}", headers=headers,
                                json={"is_active": True}).status_code == 200
            assert staff.get("/auth/session").status_code == 401
    finally:
        event.remove(engine, "before_cursor_execute", signal_admin_lock)


def test_login_racing_deactivation_on_temporary_postgresql(monkeypatch):
    from app.routers import admin as admin_module
    from app.routers import auth as auth_module

    url = os.getenv("TEST_ADMIN_RACE_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_ADMIN_RACE_POSTGRESQL_URL is not configured.")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    try:
        with factory.begin() as db:
            db.add(AdminWriteLock(id=1))
            admin_user = User(email="admin@example.test", password_hash=hash_password(PASSWORD), is_global_admin=True)
            staff_user = User(email="staff@example.test", password_hash=hash_password(PASSWORD))
            db.add_all([admin_user, staff_user])
            db.flush()
            admin_id, staff_id = admin_user.id, staff_user.id

        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(admin_router)

        def override_db():
            with factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as admin_client, TestClient(app) as staff_client:
            headers = login(admin_client, "admin")
            csrf = staff_client.get("/auth/csrf").json()["csrf_token"]
            login_checked = Event()
            admin_attempting_user_lock = Event()
            finish_login = Event()
            original_verify = auth_module.verify_password
            original_get_user = admin_module.get_user

            def paused_verify(password, password_hash):
                result = original_verify(password, password_hash)
                login_checked.set()
                if not finish_login.wait(15):
                    raise TimeoutError("concurrent deactivation did not reach user lock")
                return result

            def signal_user_lock(db, user_id, *, lock=False):
                if user_id == staff_id and lock:
                    admin_attempting_user_lock.set()
                return original_get_user(db, user_id, lock=lock)

            monkeypatch.setattr(auth_module, "verify_password", paused_verify)
            monkeypatch.setattr(admin_module, "get_user", signal_user_lock)
            with ThreadPoolExecutor(max_workers=2) as pool:
                login_future = pool.submit(
                    staff_client.post, "/auth/login",
                    headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                    json={"email": "staff@example.test", "password": PASSWORD},
                )
                try:
                    assert login_checked.wait(15)
                    deactivate_future = pool.submit(
                        admin_client.patch, f"/admin/users/{staff_id}",
                        headers=headers, json={"is_active": False},
                    )
                    assert admin_attempting_user_lock.wait(15)
                finally:
                    finish_login.set()
                assert login_future.result(timeout=15).status_code == 200
                assert deactivate_future.result(timeout=15).status_code == 200
            assert admin_client.patch(f"/admin/users/{staff_id}", headers=headers,
                                      json={"is_active": True}).status_code == 200
            assert staff_client.get("/auth/session").status_code == 401
            with factory() as db:
                session = db.scalar(select(AuthSession).where(AuthSession.user_id == staff_id))
                assert session is not None and session.revoked_at is not None

            with factory.begin() as db:
                db.get(User, staff_id).is_global_admin = True
            with TestClient(app) as second_admin_session:
                login(second_admin_session, "admin")
                second_hash = token_hash(second_admin_session.cookies[settings.cookie_name])
                session_locked = Event()
                admin_attempting_sessions = Event()

                def signal_session_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "auth_sessions.user_id =" in statement and "FOR UPDATE" in statement:
                        admin_attempting_sessions.set()

                def tenant_write():
                    with factory.begin() as db:
                        db.execute(select(AuthSession.id).where(
                            AuthSession.token_hash == second_hash
                        ).with_for_update()).first()
                        session_locked.set()
                        if not admin_attempting_sessions.wait(15):
                            raise TimeoutError("deactivation did not reach session lock")
                        db.execute(select(User.id).where(User.id == admin_id).with_for_update()).first()

                event.listen(engine, "before_cursor_execute", signal_session_lock)
                try:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        operation_future = pool.submit(tenant_write)
                        assert session_locked.wait(15)
                        deactivate_future = pool.submit(
                            admin_client.patch, f"/admin/users/{admin_id}",
                            headers=headers, json={"is_active": False},
                        )
                        operation_future.result(timeout=15)
                        assert deactivate_future.result(timeout=15).status_code == 200
                    assert second_admin_session.get("/auth/session").status_code == 401
                finally:
                    event.remove(engine, "before_cursor_execute", signal_session_lock)
    finally:
        engine.dispose()


def test_concurrent_admin_writes_on_temporary_postgresql():
    url = os.getenv("TEST_ADMIN_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_ADMIN_POSTGRESQL_URL is not configured.")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory.begin() as db:
        db.add(AdminWriteLock(id=1))
        admins = [
            User(email=f"admin{index}@example.test", password_hash=hash_password(PASSWORD), is_global_admin=True)
            for index in (1, 2)
        ]
        employee = User(email="employee@example.test", password_hash=hash_password(PASSWORD))
        bar = Bar(name="Bar")
        db.add_all([*admins, employee, bar])
        db.flush()
        admin_ids = [admin.id for admin in admins]
        employee_id, bar_id = employee.id, bar.id

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(admin_router)

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as first, TestClient(app) as second:
        headers = []
        for index, client in enumerate((first, second), 1):
            csrf = client.get("/auth/csrf").json()["csrf_token"]
            response = client.post("/auth/login", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                                   json={"email": f"admin{index}@example.test", "password": PASSWORD})
            headers.append({"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]})
        barrier = Barrier(2)

        def assign(index):
            barrier.wait(timeout=10)
            return (first, second)[index].post(
                f"/admin/bars/{bar_id}/memberships", headers=headers[index],
                json={"user_id": employee_id, "role": "staff"}
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(assign, (0, 1))) == [201, 409]
        barrier = Barrier(2)

        def disable_other(index):
            barrier.wait(timeout=10)
            return (first, second)[index].patch(
                f"/admin/users/{admin_ids[1 - index]}", headers=headers[index],
                json={"is_active": False}
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(disable_other, (0, 1)))
        assert statuses == [200, 401]
        with factory() as db:
            assert len(db.scalars(select(User).where(User.is_global_admin.is_(True), User.is_active.is_(True))).all()) == 1
            assert len(db.scalars(select(UserBarMembership)).all()) == 1
    engine.dispose()
