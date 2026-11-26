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
    with _test_sessionmaker() as db:
        user = db.scalar(
            select(User).where(User.email == "owner@example.test")
        )
        assert user is not None
        assert verify_password(
            "a cli password that is long enough",
            user.password_hash,
        )
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


def test_auth_migration_0011_only_adds_session_tables_on_sqlite(tmp_path, monkeypatch):
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

        monkeypatch.delenv("DATABASE_URL", raising=False)
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


def test_login_from_second_tab_with_existing_session(auth_test_environment):
    """A second-tab login must work while another tab is authenticated."""
    client, _engine, factory = auth_test_environment
    create_owner(factory)

    first_csrf = csrf_for_login(client)
    first_login = login(client, first_csrf)
    assert first_login.status_code == 200

    # Both browser tabs share the authentication cookies.
    # Requesting a login token must not rotate the active session token.
    first_session_csrf = first_login.json()["csrf_token"]

    second_csrf_response = client.get("/auth/login-csrf")
    assert second_csrf_response.status_code == 200
    second_csrf = second_csrf_response.json()["csrf_token"]

    assert client.cookies.get("barmanager_csrf") == first_session_csrf

    protected_response = client.post(
        "/protected",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": first_session_csrf,
        },
    )
    assert protected_response.status_code == 200

    second_login = login(client, second_csrf)

    assert second_login.status_code == 200, (
        f"Second-tab login failed: {second_login.status_code} "
        f"{second_login.json()}"
    )



def test_multitab_session_csrf_rotation_invalidates_stale_token(
    auth_test_environment,
):
    """Verify stale CSRF rejection after another tab rotates the token."""
    client, _engine, factory = auth_test_environment
    create_owner(factory)

    first_login = login(client, csrf_for_login(client))
    assert first_login.status_code == 200

    first_token = first_login.json()["csrf_token"]

    second_response = client.get("/auth/csrf")
    assert second_response.status_code == 200

    second_token = second_response.json()["csrf_token"]
    assert second_token != first_token

    stale_request = client.post(
        "/protected",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": first_token,
        },
    )
    assert stale_request.status_code == 403

    fresh_request = client.post(
        "/protected",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": second_token,
        },
    )
    assert fresh_request.status_code == 200



def test_session_id_identifies_login_and_changes_on_new_login(
    auth_test_environment,
):
    client, _engine, factory = auth_test_environment
    create_owner(factory)

    first_login = login(client, csrf_for_login(client))
    assert first_login.status_code == 200

    first_id = first_login.json()["session_id"]
    assert isinstance(first_id, int)

    current = client.get("/auth/session")
    assert current.status_code == 200
    assert current.json()["session_id"] == first_id

    pre_auth = client.get("/auth/login-csrf")
    assert pre_auth.status_code == 200

    second_login = login(
        client,
        pre_auth.json()["csrf_token"],
    )
    assert second_login.status_code == 200

    second_id = second_login.json()["session_id"]
    assert second_id != first_id

    current = client.get("/auth/session")
    assert current.status_code == 200
    assert current.json()["session_id"] == second_id

    assert "token" not in current.json()
    assert "token_hash" not in current.json()



def test_expected_session_id_rejects_mismatched_mutations(
    auth_test_environment,
):
    client, _engine, factory = auth_test_environment
    create_owner(factory)

    response = login(client, csrf_for_login(client))
    assert response.status_code == 200

    session_id = response.json()["session_id"]
    csrf = response.json()["csrf_token"]

    headers = {
        "Origin": ALLOWED_ORIGIN,
        "X-CSRF-Token": csrf,
        "X-Expected-Session-ID": str(session_id),
    }

    valid = client.post("/protected", headers=headers)
    assert valid.status_code == 200

    wrong = client.post(
        "/protected",
        headers={
            **headers,
            "X-Expected-Session-ID": str(session_id + 1),
        },
    )
    assert wrong.status_code == 409
    assert wrong.json()["detail"] == "authenticated session changed"

    malformed = client.post(
        "/protected",
        headers={
            **headers,
            "X-Expected-Session-ID": "invalid",
        },
    )
    assert malformed.status_code == 409


@pytest.mark.parametrize(
    "email_ages,other_ages,expected",
    [
        ([0, 0, 0], [], 901),
        ([660, 660, 660], [], 241),
        ([800, 700, 600, 500], [], 201),
        ([800, 800, 800], [100, 100, 100, 100, 100], 801),
        ([901, 901, 901], [], None),
        ([900, 900, 900], [], 1),
        ([100, 100], [], None),
        ([], [300, 300, 300, 300, 300], 601),
    ],
)
def test_login_rate_limit_residual_time(
    auth_test_environment,
    monkeypatch,
    email_ages,
    other_ages,
    expected,
):
    from fastapi import HTTPException
    from app.routers.auth import _check_login_rate_limit

    from dataclasses import replace
    from importlib import import_module

    auth_module = import_module("app.routers.auth")

    test_settings = replace(
        settings,
        login_attempt_limit=3,
        login_source_attempt_limit=5,
        login_attempt_window_seconds=900,
    )

    monkeypatch.setattr(auth_module, "settings", test_settings)

    _, _, test_sessionmaker = auth_test_environment

    now = dt.datetime(2026, 11, 24, 10, 0, tzinfo=dt.timezone.utc)

    with test_sessionmaker() as db:
        for age in email_ages:
            db.add(AuthLoginAttempt(
                email_key="a" * 64,
                source_key="b" * 64,
                attempted_at=now - dt.timedelta(seconds=age),
            ))

        for age in other_ages:
            db.add(AuthLoginAttempt(
                email_key="c" * 64,
                source_key="b" * 64,
                attempted_at=now - dt.timedelta(seconds=age),
            ))

        db.commit()

        if expected is None:
            _check_login_rate_limit(
                db, "a" * 64, "b" * 64, now
            )
        else:
            with pytest.raises(HTTPException) as exc:
                _check_login_rate_limit(
                    db, "a" * 64, "b" * 64, now
                )

            assert exc.value.status_code == 429
            assert int(exc.value.headers["Retry-After"]) == expected


@pytest.fixture
def replaced_browser_session(auth_test_environment):
    client, engine, factory = auth_test_environment

    create_owner(factory)

    with factory() as db:
        second_user = User(
            email="second@example.test",
            password_hash=hash_password(
                "correct horse battery"
            ),
        )
        db.add(second_user)
        db.commit()

    first = login(client, csrf_for_login(client))
    assert first.status_code == 200

    pre_auth = client.get("/auth/login-csrf")
    assert pre_auth.status_code == 200

    second = login(
        client,
        pre_auth.json()["csrf_token"],
        email="second@example.test",
    )

    assert second.status_code == 200

    old = first.json()
    current = second.json()

    assert old["session_id"] != current["session_id"]
    assert old["user"]["id"] != current["user"]["id"]

    return client, factory, old, current


def test_bound_session_read_accepts_current_identity(
    replaced_browser_session,
):
    client, factory, old, current = replaced_browser_session

    response = client.get(
        "/auth/session",
        headers={
            "X-Expected-Session-ID": str(
                current["session_id"]
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["user"] == current["user"]
    assert response.json()["session_id"] == current["session_id"]


def test_bound_session_read_rejects_previous_identity(
    replaced_browser_session,
):
    client, factory, old, current = replaced_browser_session

    response = client.get(
        "/auth/session",
        headers={
            "X-Expected-Session-ID": str(
                old["session_id"]
            ),
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "authenticated session changed"
    )
    assert "user" not in response.json()

    assert client.get("/auth/session").json()[
        "session_id"
    ] == current["session_id"]


def test_bound_csrf_rejects_previous_session_without_rotation(
    replaced_browser_session,
):
    client, factory, old, current = replaced_browser_session

    original_cookie = client.cookies.get(
        "barmanager_csrf"
    )

    response = client.get(
        "/auth/csrf",
        headers={
            "X-Expected-Session-ID": str(
                old["session_id"]
            ),
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "authenticated session changed"
    )

    assert "csrf_token" not in response.json()
    assert "set-cookie" not in response.headers

    assert client.cookies.get(
        "barmanager_csrf"
    ) == original_cookie

    with factory() as db:
        session = db.get(
            AuthSession,
            current["session_id"],
        )

        assert session.csrf_token_hash == token_hash(
            current["csrf_token"]
        )

    valid = client.get(
        "/auth/csrf",
        headers={
            "X-Expected-Session-ID": str(
                current["session_id"]
            ),
        },
    )

    assert valid.status_code == 200
    assert valid.json()["csrf_token"] != original_cookie


def test_bound_logout_cannot_revoke_replacement_session(
    replaced_browser_session,
):
    client, factory, old, current = replaced_browser_session

    original_cookie = client.cookies.get(
        settings.cookie_name
    )

    response = client.post(
        "/auth/logout",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": current["csrf_token"],
            "X-Expected-Session-ID": str(
                old["session_id"]
            ),
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "authenticated session changed"
    )

    assert "set-cookie" not in response.headers

    assert client.cookies.get(
        settings.cookie_name
    ) == original_cookie

    with factory() as db:
        session = db.get(
            AuthSession,
            current["session_id"],
        )

        assert session.revoked_at is None

    active = client.get("/auth/session")

    assert active.status_code == 200
    assert active.json()["user"] == current["user"]

    valid_logout = client.post(
        "/auth/logout",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": current["csrf_token"],
            "X-Expected-Session-ID": str(
                current["session_id"]
            ),
        },
    )

    assert valid_logout.status_code == 200
    assert client.get("/auth/session").status_code == 401

    with factory() as db:
        assert db.get(
            AuthSession,
            current["session_id"],
        ).revoked_at is not None


def test_bound_mutation_rejects_replaced_session(
    replaced_browser_session,
):
    client, factory, old, current = replaced_browser_session

    headers = {
        "Origin": ALLOWED_ORIGIN,
        "X-CSRF-Token": current["csrf_token"],
        "X-Expected-Session-ID": str(
            old["session_id"]
        ),
    }

    response = client.post(
        "/protected",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "authenticated session changed"
    )

    headers["X-Expected-Session-ID"] = str(
        current["session_id"]
    )

    valid = client.post(
        "/protected",
        headers=headers,
    )

    assert valid.status_code == 200


def test_bound_csrf_rejects_expired_session(
    auth_test_environment,
):
    client, engine, factory = auth_test_environment

    create_owner(factory)

    response = login(client, csrf_for_login(client))
    assert response.status_code == 200

    session_id = response.json()["session_id"]

    with factory() as db:
        session = db.get(AuthSession, session_id)

        session.expires_at = (
            dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(seconds=1)
        )

        db.commit()

    headers = {
        "X-Expected-Session-ID": str(session_id),
    }

    for endpoint in ("/auth/session", "/auth/csrf"):
        expired = client.get(
            endpoint,
            headers=headers,
        )

        assert expired.status_code == 401
        assert "csrf_token" not in expired.json()
        assert "set-cookie" not in expired.headers
