import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    Document,
    MembershipPermission,
    UserBarMembership,
)

from test_document_tenant_scope import (
    document_environment,
    headers,
    upload,
)
from test_operational_tenant_scope import (
    login,
    select_bar,
    ALLOWED_ORIGIN,
)


def set_permissions(factory, user_id, bar_id, permissions):
    with factory() as db:
        membership = db.scalar(
            select(UserBarMembership).where(
                UserBarMembership.user_id == user_id,
                UserBarMembership.bar_id == bar_id,
            )
        )
        assert membership is not None

        for existing in list(membership.permissions):
            db.delete(existing)

        db.flush()

        for permission in permissions:
            db.add(
                MembershipPermission(
                    membership_id=membership.id,
                    permission=permission,
                )
            )

        db.commit()


def test_staff_view_own_cannot_read_owner_document(
    document_environment,
):
    client, factory, ids, root, app = document_environment

    owner_csrf = login(client, "owner@example.test")
    assert select_bar(
        client, ids["bar_one"], owner_csrf
    ).status_code == 200

    owner_doc = upload(client, owner_csrf, b"owner-private").json()

    set_permissions(
        factory,
        ids["staff"],
        ids["bar_one"],
        ["documents.view_own"],
    )

    with TestClient(app) as staff:
        staff_csrf = login(staff, "staff@example.test")
        assert select_bar(
            staff, ids["bar_one"], staff_csrf
        ).status_code == 200

        response = staff.get("/documents")
        assert response.status_code == 200
        assert owner_doc["id"] not in {
            row["id"] for row in response.json()
        }

        assert staff.get(
            owner_doc["file_url"]
        ).status_code == 404


def test_staff_view_all_can_read_owner_document(
    document_environment,
):
    client, factory, ids, root, app = document_environment

    owner_csrf = login(client, "owner@example.test")
    assert select_bar(
        client, ids["bar_one"], owner_csrf
    ).status_code == 200

    owner_doc = upload(client, owner_csrf, b"owner-visible").json()

    set_permissions(
        factory,
        ids["staff"],
        ids["bar_one"],
        ["documents.view_all"],
    )

    with TestClient(app) as staff:
        staff_csrf = login(staff, "staff@example.test")
        assert select_bar(
            staff, ids["bar_one"], staff_csrf
        ).status_code == 200

        response = staff.get("/documents")
        assert response.status_code == 200
        assert owner_doc["id"] in {
            row["id"] for row in response.json()
        }

        downloaded = staff.get(owner_doc["file_url"])
        assert downloaded.status_code == 200
        assert downloaded.content == b"owner-visible"


def test_staff_without_read_permissions_is_denied(
    document_environment,
):
    client, factory, ids, root, app = document_environment

    owner_csrf = login(client, "owner@example.test")
    assert select_bar(
        client, ids["bar_one"], owner_csrf
    ).status_code == 200

    owner_doc = upload(client, owner_csrf).json()

    set_permissions(
        factory,
        ids["staff"],
        ids["bar_one"],
        [],
    )

    with TestClient(app) as staff:
        staff_csrf = login(staff, "staff@example.test")
        assert select_bar(
            staff, ids["bar_one"], staff_csrf
        ).status_code == 200

        assert staff.get("/documents").status_code == 403
        assert staff.get(
            owner_doc["file_url"]
        ).status_code == 403


def test_staff_view_all_cannot_read_other_bar(
    document_environment,
):
    client, factory, ids, root, app = document_environment

    owner_csrf = login(client, "owner@example.test")
    assert select_bar(
        client, ids["bar_two"], owner_csrf
    ).status_code == 200

    other_doc = upload(client, owner_csrf, b"other-bar").json()

    set_permissions(
        factory,
        ids["staff"],
        ids["bar_one"],
        ["documents.view_all"],
    )

    with TestClient(app) as staff:
        staff_csrf = login(staff, "staff@example.test")
        assert select_bar(
            staff, ids["bar_one"], staff_csrf
        ).status_code == 200

        assert staff.get(
            other_doc["file_url"]
        ).status_code == 404

        response = staff.get("/documents")
        assert response.status_code == 200
        assert other_doc["id"] not in {
            row["id"] for row in response.json()
        }
