import sys

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import Bar, MembershipPermission, MembershipRole, User, UserBarMembership
from app.permissions import DelegablePermission


@pytest.fixture
def tenant_session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def create_user(session: Session, email: str = "owner@example.test") -> User:
    user = User(email=email, password_hash="hashed-password")
    session.add(user)
    session.flush()
    return user


def test_multiple_bars_and_global_normalized_user_email(tenant_session):
    first_bar = Bar(name="Bar Uno")
    second_bar = Bar(name="Bar Due")
    tenant_session.add_all([first_bar, second_bar])
    tenant_session.commit()

    user = create_user(tenant_session, "  OWNER@EXAMPLE.TEST ")
    tenant_session.commit()

    assert user.email == "owner@example.test"
    assert tenant_session.scalars(select(Bar)).all() == [first_bar, second_bar]

    tenant_session.add(User(email="Owner@example.test", password_hash="other-hash"))
    with pytest.raises(IntegrityError):
        tenant_session.commit()


def test_tenant_models_are_registered_in_shared_metadata():
    assert {
        "bars",
        "users",
        "user_bar_memberships",
    }.issubset(Base.metadata.tables)


def test_user_can_have_different_roles_in_multiple_bars(tenant_session):
    user = create_user(tenant_session)
    first_bar = Bar(name="Bar Uno")
    second_bar = Bar(name="Bar Due")
    tenant_session.add_all([first_bar, second_bar])
    tenant_session.flush()
    tenant_session.add_all(
        [
            UserBarMembership(
                user=user,
                bar=first_bar,
                role=MembershipRole.owner,
            ),
            UserBarMembership(
                user=user,
                bar=second_bar,
                role=MembershipRole.staff,
            ),
        ]
    )
    tenant_session.commit()

    assert {membership.role for membership in user.memberships} == {
        MembershipRole.owner,
        MembershipRole.staff,
    }


def test_duplicate_user_bar_membership_is_rejected(tenant_session):
    user = create_user(tenant_session)
    bar = Bar(name="Bar Uno")
    tenant_session.add(bar)
    tenant_session.flush()
    tenant_session.add(
        UserBarMembership(user=user, bar=bar, role=MembershipRole.owner)
    )
    tenant_session.commit()
    tenant_session.add(
        UserBarMembership(user=user, bar=bar, role=MembershipRole.manager)
    )

    with pytest.raises(IntegrityError):
        tenant_session.commit()


def test_database_rejects_invalid_membership_role(tenant_session):
    user = create_user(tenant_session)
    bar = Bar(name="Bar Uno")
    tenant_session.add(bar)
    tenant_session.flush()

    with pytest.raises(IntegrityError):
        tenant_session.execute(
            text(
                "INSERT INTO user_bar_memberships (user_id, bar_id, role) "
                "VALUES (:user_id, :bar_id, 'admin')"
            ),
            {"user_id": user.id, "bar_id": bar.id},
        )


@pytest.mark.parametrize(
    ("user_id", "bar_id"),
    [(999, 999), (None, 999), (999, None)],
)
def test_membership_foreign_keys_are_enforced(tenant_session, user_id, bar_id):
    with pytest.raises(IntegrityError):
        tenant_session.execute(
            text(
                "INSERT INTO user_bar_memberships (user_id, bar_id, role) "
                "VALUES (:user_id, :bar_id, 'staff')"
            ),
            {"user_id": user_id, "bar_id": bar_id},
        )


def test_permissions_are_scoped_to_membership_and_default_to_deny(tenant_session):
    user = create_user(tenant_session)
    first = UserBarMembership(user=user, bar=Bar(name="Uno"), role=MembershipRole.staff)
    second = UserBarMembership(user=user, bar=Bar(name="Due"), role=MembershipRole.staff)
    tenant_session.add_all([first, second])
    tenant_session.flush()
    assert not user.is_global_admin
    assert first.permissions == []
    assert second.permissions == []

    first.permissions.append(MembershipPermission(permission=DelegablePermission.INVOICES_UPLOAD))
    second.permissions.append(MembershipPermission(permission=DelegablePermission.COSTS_VIEW))
    tenant_session.commit()
    tenant_session.expire_all()

    assert [grant.permission for grant in first.permissions] == ["invoices.upload"]
    assert [grant.permission for grant in second.permissions] == ["costs.view"]


def test_unknown_or_cash_closure_approval_permissions_are_rejected(tenant_session):
    membership = UserBarMembership(
        user=create_user(tenant_session), bar=Bar(name="Uno"), role=MembershipRole.staff
    )
    tenant_session.add(membership)
    tenant_session.commit()
    membership_id = membership.id
    assert "cash_closures.approve" not in {item.value for item in DelegablePermission}
    for code in ("cash_closures.approve", "is_global_admin", "unknown.permission"):
        with pytest.raises(ValueError):
            MembershipPermission(permission=code)
        with pytest.raises(IntegrityError):
            tenant_session.execute(
                text("INSERT INTO membership_permissions (membership_id, permission) VALUES (:id, :code)"),
                {"id": membership_id, "code": code},
            )
        tenant_session.rollback()


def test_permission_uniqueness_and_foreign_key(tenant_session):
    membership = UserBarMembership(
        user=create_user(tenant_session), bar=Bar(name="Uno"), role=MembershipRole.staff
    )
    tenant_session.add(membership)
    tenant_session.flush()
    tenant_session.add(MembershipPermission(membership=membership, permission="invoices.upload"))
    tenant_session.commit()
    tenant_session.add(MembershipPermission(membership=membership, permission="invoices.upload"))
    with pytest.raises(IntegrityError):
        tenant_session.commit()
    tenant_session.rollback()
    with pytest.raises(IntegrityError):
        tenant_session.execute(
            text("INSERT INTO membership_permissions (membership_id, permission) VALUES (99999, 'invoices.upload')")
        )
