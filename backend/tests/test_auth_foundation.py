import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, event, func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from alembic import command
from alembic.config import Config
from app.bootstrap_owner import BootstrapError, bootstrap_owner
from app import bootstrap_owner as bootstrap_owner_module
from app.auth import require_global_admin, require_session_csrf
from app.database import Base, get_db
from app.models import (
    AuthLoginAttempt,
    AuthSession,
    Bar,
    MembershipRole,
    User,
    UserBarMembership,
)
from app.routers.auth import router as auth_router
from app.security import hash_password, token_hash, verify_password
from app.settings import settings


ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture
def auth_test_environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth-test.db'}")

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

    def protected_mutation(_auth_session=Depends(require_session_csrf)):
        return {"ok": True}

    api.add_api_route("/protected", protected_mutation, methods=["POST"])
    api.add_api_route(
        "/test-global-admin",
        lambda user=Depends(require_global_admin): {"id": user.id},
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
        yield client, engine, test_sessionmaker
    engine.dispose()


def create_owner(sessionmaker_for_test, email="owner@example.test"):
    with sessionmaker_for_test() as db:
        bar = Bar(name="Test Bar")
        user = User(email=email, password_hash=hash_password("correct horse battery"))
        db.add_all([bar, user])
        db.flush()
        db.add(
            UserBarMembership(
                user_id=user.id,
                bar_id=bar.id,
                role=MembershipRole.owner,
            )
        )
        db.commit()
        return user.id


def csrf_for_login(client):
    response = client.get("/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def login(client, csrf_token, email="owner@example.test", password="correct horse battery"):
    return client.post(
        "/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": csrf_token,
        },
        json={"email": email, "password": password},
    )


def test_global_admin_guard_cannot_be_escalated_via_login(auth_test_environment):
    client, _engine, factory = auth_test_environment
    user_id = create_owner(factory)
    assert client.get("/test-global-admin").status_code == 401
    csrf = csrf_for_login(client)
    response = client.post(
        "/auth/login",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
        json={
            "email": "owner@example.test",
            "password": "correct horse battery",
            "is_global_admin": True,
            "role": "admin",
        },
    )
    assert response.status_code == 200
    assert client.get("/test-global-admin").status_code == 403
    with factory() as db:
        user = db.get(User, user_id)
        assert not user.is_global_admin
        user.is_global_admin = True
        db.commit()
    assert client.get("/test-global-admin").status_code == 200
    with factory() as db:
        user = db.get(User, user_id)
        user.is_active = False
        db.commit()
    assert client.get("/test-global-admin").status_code == 401


def test_global_admin_cli_requires_explicit_confirmation(auth_test_environment, monkeypatch):
    from app import promote_global_admin as cli

    _client, engine, factory = auth_test_environment
    user_id = create_owner(factory)
    monkeypatch.setattr(cli, "engine", engine)
    monkeypatch.setattr(sys, "argv", ["promote_global_admin", str(user_id)])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli.main() == 1
    monkeypatch.setenv("DATABASE_URL", str(engine.url))
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    assert cli.main() == 1
    with factory() as db:
        assert not db.get(User, user_id).is_global_admin
    monkeypatch.setattr("builtins.input", lambda _prompt: f"PROMOTE {user_id}")
    assert cli.main() == 0
    with factory() as db:
        assert db.get(User, user_id).is_global_admin
    assert cli.main() == 1


def test_global_admin_promotion_rejects_missing_or_inactive_user(auth_test_environment):
    from app.promote_global_admin import promote_global_admin

    _client, _engine, factory = auth_test_environment
    user_id = create_owner(factory)
    with factory() as db:
        db.get(User, user_id).is_active = False
        db.commit()
        for invalid_id in (user_id, 99999):
            with pytest.raises(ValueError):
                promote_global_admin(db, invalid_id)
        assert not db.get(User, user_id).is_global_admin


def test_argon2id_hash_and_password_verification():
    password_hash = hash_password("a sufficiently long password")

    assert password_hash.startswith("$argon2id$")
    assert password_hash != "a sufficiently long password"
    assert verify_password("a sufficiently long password", password_hash)
    assert not verify_password("incorrect password", password_hash)
    assert not verify_password("password", "not-a-valid-hash")
    with pytest.raises(ValueError, match="at least 12"):
        hash_password("too short")


def test_login_sets_httponly_session_cookie_and_persists_only_token_hash(
    auth_test_environment,
):
    client, _engine, test_sessionmaker = auth_test_environment
    create_owner(test_sessionmaker)
    pre_auth_csrf = csrf_for_login(client)

    response = login(client, pre_auth_csrf)

    assert response.status_code == 200
    result = response.json()
    cookie = response.cookies.get(settings.cookie_name)
    csrf_cookie = response.cookies.get("barmanager_csrf")
    assert cookie
    assert csrf_cookie == result["csrf_token"]
    assert result["csrf_token"] != pre_auth_csrf
    assert response.cookies.get(settings.cookie_name).startswith(cookie)
    assert settings.cookie_name in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert (
        "secure" in response.headers["set-cookie"].lower()
    ) is settings.cookie_secure

    with test_sessionmaker() as db:
        auth_session = db.scalar(select(AuthSession))
        assert auth_session is not None
        assert auth_session.token_hash == token_hash(cookie)
        assert cookie not in auth_session.token_hash
        assert auth_session.csrf_token_hash == token_hash(result["csrf_token"])
        assert db.scalar(select(AuthLoginAttempt.id)) is None

    session_response = client.get("/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["user"]["email"] == "owner@example.test"


def test_login_rejects_bad_credentials_and_untrusted_or_missing_origin(
    auth_test_environment,
):
    client, _engine, test_sessionmaker = auth_test_environment
    create_owner(test_sessionmaker)
    csrf_token = csrf_for_login(client)

    wrong_password = login(client, csrf_token, password="wrong password value")
    assert wrong_password.status_code == 401
    assert wrong_password.json()["detail"] == "invalid email or password"

    wrong_origin = client.post(
        "/auth/login",
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf_token},
        json={"email": "owner@example.test", "password": "correct horse battery"},
    )
    assert wrong_origin.status_code == 403

    no_origin = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": csrf_token},
        json={"email": "owner@example.test", "password": "correct horse battery"},
    )
    assert no_origin.status_code == 403

    wrong_csrf = client.post(
        "/auth/login",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "invalid"},
        json={"email": "owner@example.test", "password": "correct horse battery"},
    )
    assert wrong_csrf.status_code == 403


def test_authenticated_mutation_requires_csrf_and_allowed_origin(
    auth_test_environment,
):
    client, _engine, test_sessionmaker = auth_test_environment
    create_owner(test_sessionmaker)
    pre_auth_csrf = csrf_for_login(client)
    login_response = login(client, pre_auth_csrf)
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]

    assert client.post("/protected").status_code == 403
    assert client.post(
        "/protected",
        headers={"X-CSRF-Token": csrf_token},
    ).status_code == 403
    response = client.post(
        "/protected",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_login_rate_limit_is_recorded_without_plain_email_or_ip(
    auth_test_environment,
):
    client, _engine, test_sessionmaker = auth_test_environment
    csrf_token = csrf_for_login(client)

    for _ in range(settings.login_attempt_limit):
        assert login(client, csrf_token).status_code == 401
    limited = login(client, csrf_token)
    assert limited.status_code == 429
    assert limited.headers["retry-after"]

    with test_sessionmaker() as db:
        attempts = db.scalars(select(AuthLoginAttempt)).all()
        assert len(attempts) == settings.login_attempt_limit
        assert all("owner@example.test" not in row.email_key for row in attempts)
        assert all("testclient" not in row.source_key for row in attempts)


def test_csrf_rotation_logout_revocation_and_idempotent_expired_logout(
    auth_test_environment,
):
    client, _engine, test_sessionmaker = auth_test_environment
    user_id = create_owner(test_sessionmaker)
    pre_auth_csrf = csrf_for_login(client)
    login_response = login(client, pre_auth_csrf)
    assert login_response.status_code == 200
    old_csrf = login_response.json()["csrf_token"]

    refreshed_csrf_response = client.get("/auth/csrf")
    assert refreshed_csrf_response.status_code == 200
    fresh_csrf = refreshed_csrf_response.json()["csrf_token"]
    assert fresh_csrf != old_csrf

    bad_logout = client.post(
        "/auth/logout",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": old_csrf},
    )
    assert bad_logout.status_code == 403

    logout_response = client.post(
        "/auth/logout",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": fresh_csrf},
    )
    assert logout_response.status_code == 200
    assert logout_response.json() == {"logged_out": True}
    assert client.get("/auth/session").status_code == 401
    with test_sessionmaker() as db:
        auth_session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
        assert auth_session is not None and auth_session.revoked_at is not None

    second_pre_auth_csrf = csrf_for_login(client)
    second_login = login(client, second_pre_auth_csrf)
    assert second_login.status_code == 200
    with test_sessionmaker() as db:
        auth_session = db.scalar(
            select(AuthSession)
            .where(AuthSession.user_id == user_id)
            .order_by(AuthSession.id.desc())
        )
        assert auth_session is not None
        auth_session.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        db.commit()

    assert client.get("/auth/session").status_code == 401
    expired_csrf_response = client.get("/auth/csrf")
    expired_csrf = expired_csrf_response.json()["csrf_token"]
    expired_logout = client.post(
        "/auth/logout",
        headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": expired_csrf},
    )
    assert expired_logout.status_code == 200


def test_bootstrap_owner_creates_user_bar_and_membership_atomically(
    auth_test_environment,
):
    _client, _engine, test_sessionmaker = auth_test_environment

    with test_sessionmaker() as db:
        user_id, bar_id = bootstrap_owner(
            db,
            "  OWNER@EXAMPLE.TEST ",
            "a bootstrap password long enough",
            "Bar Uno",
        )
        db.commit()

    with test_sessionmaker() as db:
        user = db.get(User, user_id)
        membership = db.scalar(
            select(UserBarMembership).where(
                UserBarMembership.user_id == user_id,
                UserBarMembership.bar_id == bar_id,
            )
        )
        assert user is not None
        assert user.email == "owner@example.test"
        assert verify_password("a bootstrap password long enough", user.password_hash)
        assert membership is not None
        assert membership.role == MembershipRole.owner
        assert db.get(Bar, bar_id).name == "Bar Uno"


def test_bootstrap_refuses_second_user_and_reuses_legacy_bar_without_renaming(
    auth_test_environment,
):
    _client, _engine, test_sessionmaker = auth_test_environment
    with test_sessionmaker() as db:
        db.add(Bar(id=-1, name="Bar Legacy"))
        db.commit()
        user_id, bar_id = bootstrap_owner(
            db,
            "owner@example.test",
            "a bootstrap password long enough",
            "Different display name",
        )
        db.commit()
        assert bar_id == -1
        with pytest.raises(BootstrapError, match="users already exist"):
            bootstrap_owner(
                db,
                "second@example.test",
                "another valid bootstrap password",
                "Second Bar",
            )
        db.rollback()

    with test_sessionmaker() as db:
        assert db.scalar(select(User.id)) == user_id
        assert db.get(Bar, -1).name == "Bar Legacy"
        assert db.scalar(select(func.count(UserBarMembership.id))) == 1


def test_bootstrap_cli_does_not_echo_password(auth_test_environment, monkeypatch, capsys):
    _client, engine, _test_sessionmaker = auth_test_environment
    monkeypatch.setattr(bootstrap_owner_module, "engine", engine)
    answers = iter(
        [
            "owner@example.test",
            "a cli password that is long enough",
            "a cli password that is long enough",
            "CLI Bar",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(
        "getpass.getpass",
        lambda _prompt: next(answers),
    )

    assert bootstrap_owner_module.main() == 0
    output = capsys.readouterr()
    assert "Bootstrap complete" in output.out
    assert "a cli password that is long enough" not in output.out
    assert "a cli password that is long enough" not in output.err


def test_production_settings_require_secret_origins_and_secure_cookies(
    monkeypatch,
):
    from app.settings import _load_settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "s" * 40)
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "https://bar.example")
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    production = _load_settings()
    assert production.cookie_secure is True
    assert production.allowed_origins == ("https://bar.example",)

    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="cannot be disabled"):
        _load_settings()

    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.delenv("AUTH_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="AUTH_ALLOWED_ORIGINS"):
        _load_settings()


def test_pre_auth_csrf_token_has_a_short_expiry():
    from app.security import create_pre_auth_csrf_token, verify_pre_auth_csrf_token

    issued_at = 1_800_000_000
    csrf_token = create_pre_auth_csrf_token(issued_at)
    assert verify_pre_auth_csrf_token(csrf_token, issued_at)
    assert verify_pre_auth_csrf_token(
        csrf_token,
        issued_at + settings.pre_auth_csrf_ttl_seconds,
    )
    assert not verify_pre_auth_csrf_token(
        csrf_token,
        issued_at + settings.pre_auth_csrf_ttl_seconds + 1,
    )
    assert not verify_pre_auth_csrf_token(csrf_token, issued_at - 1)


def test_auth_migration_0011_only_adds_session_tables_on_sqlite(tmp_path):
    database = tmp_path / "auth-migration.db"
    engine = create_engine(f"sqlite:///{database}")
    try:
        metadata = MetaData()
        for source_table in Base.metadata.sorted_tables:
            source_table.to_metadata(metadata)
        metadata.remove(metadata.tables["auth_sessions"])
        metadata.remove(metadata.tables["auth_login_attempts"])
        metadata.create_all(engine)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text("INSERT INTO alembic_version VALUES ('20261111_0010')")
            )

        backend_dir = Path(__file__).resolve().parents[1]
        config = Config(str(backend_dir / "alembic.ini"))
        config.set_main_option("script_location", str(backend_dir / "alembic"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
        operational_tables = {
            "products",
            "sale_lines",
            "expense_categories",
            "category_rules",
            "transactions",
            "documents",
            "daily_cash_closures",
            "invoices",
            "payments",
            "invoice_payment_links",
            "cash_closure_intakes",
        }
        before = {
            table: [
                (
                    column["name"],
                    str(column["type"]),
                    column["nullable"],
                    column["default"],
                )
                for column in inspect(engine).get_columns(table)
            ]
            for table in operational_tables
        }

        command.upgrade(config, "20261111_0011")

        inspector = inspect(engine)
        assert {"auth_sessions", "auth_login_attempts"}.issubset(
            set(inspector.get_table_names())
        )
        assert {
            table: [
                (
                    column["name"],
                    str(column["type"]),
                    column["nullable"],
                    column["default"],
                )
                for column in inspector.get_columns(table)
            ]
            for table in operational_tables
        } == before
        assert {
            column["name"]
            for column in inspector.get_columns("auth_sessions")
        } == {
            "id",
            "user_id",
            "token_hash",
            "csrf_token_hash",
            "created_at",
            "expires_at",
            "revoked_at",
        }
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "20261111_0011"
    finally:
        engine.dispose()


def test_auth_migration_0011_on_temporary_postgresql_16_if_configured():
    import os

    database_url = os.getenv("TEST_POSTGRESQL_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRESQL_URL is not configured.")

    from sqlalchemy import create_engine

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            version = int(
                connection.execute(text("SHOW server_version_num")).scalar_one()
            )
            assert version // 10000 == 16

        backend_dir = Path(__file__).resolve().parents[1]
        config = Config(str(backend_dir / "alembic.ini"))
        config.set_main_option("script_location", str(backend_dir / "alembic"))
        config.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(config, "20261111_0010")
        before = {
            table: [
                (
                    column["name"],
                    str(column["type"]),
                    column["nullable"],
                    column["default"],
                )
                for column in inspect(engine).get_columns(table)
            ]
            for table in (
                "products",
                "sale_lines",
                "expense_categories",
                "category_rules",
                "transactions",
                "documents",
                "daily_cash_closures",
                "invoices",
                "payments",
                "invoice_payment_links",
                "cash_closure_intakes",
            )
        }
        command.upgrade(config, "20261111_0011")
        inspector = inspect(engine)
        assert {"auth_sessions", "auth_login_attempts"}.issubset(
            set(inspector.get_table_names())
        )
        assert {
            table: [
                (
                    column["name"],
                    str(column["type"]),
                    column["nullable"],
                    column["default"],
                )
                for column in inspector.get_columns(table)
            ]
            for table in before
        } == before
    finally:
        engine.dispose()
