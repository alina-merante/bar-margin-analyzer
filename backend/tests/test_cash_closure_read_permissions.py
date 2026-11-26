from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.cash_closures import (
    cash_closure_read_scope,
    check_cash_closure_read_access,
)


def make_context(permissions, user_id=10, role="staff"):
    return SimpleNamespace(
        role=role,
        user=SimpleNamespace(
            id=user_id,
            is_global_admin=False,
        ),
        membership=SimpleNamespace(
            permissions=[
                SimpleNamespace(permission=value)
                for value in permissions
            ]
        ),
    )


def make_intake(created_by):
    return SimpleNamespace(
        document=SimpleNamespace(
            created_by_user_id=created_by
        )
    )


def test_view_own_allows_own_closure():
    context = make_context(["cash_closures.view_own"])
    check_cash_closure_read_access(context, make_intake(10))


def test_view_own_denies_colleague_closure():
    context = make_context(["cash_closures.view_own"])

    with pytest.raises(HTTPException) as exc:
        check_cash_closure_read_access(context, make_intake(20))

    assert exc.value.status_code == 404


def test_view_all_allows_colleague_closure():
    context = make_context(["cash_closures.view_all"])
    check_cash_closure_read_access(context, make_intake(20))


def test_no_read_permission_is_denied():
    context = make_context(["cash_closures.edit"])

    with pytest.raises(HTTPException) as exc:
        cash_closure_read_scope(context)

    assert exc.value.status_code == 403


def test_view_all_takes_precedence():
    context = make_context([
        "cash_closures.view_own",
        "cash_closures.view_all",
    ])

    assert cash_closure_read_scope(context) == "all"
