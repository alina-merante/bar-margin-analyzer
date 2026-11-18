import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.bar_context import require_financial_permissions
from app.models import MembershipRole
from app.permissions import DelegablePermission


def make_context(role, permissions=(), is_global_admin=False):
    return SimpleNamespace(
        role=role,
        user=SimpleNamespace(is_global_admin=is_global_admin),
        membership=SimpleNamespace(
            permissions=[
                SimpleNamespace(permission=permission.value)
                for permission in permissions
            ]
        ),
    )


def test_owner_can_access_financial_data():
    context = make_context(MembershipRole.owner)
    require_financial_permissions(
        context,
        DelegablePermission.ANALYTICS_VIEW,
        DelegablePermission.PROFIT_VIEW,
    )


@pytest.mark.parametrize("role", [
    MembershipRole.staff,
    MembershipRole.manager,
])
def test_non_owner_denied_without_grants(role):
    context = make_context(role)

    with pytest.raises(HTTPException) as error:
        require_financial_permissions(
            context,
            DelegablePermission.PROFIT_VIEW,
        )

    assert error.value.status_code == 403


def test_explicit_grants_are_required_together():
    context = make_context(
        MembershipRole.staff,
        [DelegablePermission.ANALYTICS_VIEW],
    )

    with pytest.raises(HTTPException) as error:
        require_financial_permissions(
            context,
            DelegablePermission.ANALYTICS_VIEW,
            DelegablePermission.PROFIT_VIEW,
        )

    assert error.value.status_code == 403


def test_staff_can_access_only_granted_data():
    context = make_context(
        MembershipRole.staff,
        [
            DelegablePermission.ANALYTICS_VIEW,
            DelegablePermission.REVENUE_VIEW,
        ],
    )

    require_financial_permissions(
        context,
        DelegablePermission.ANALYTICS_VIEW,
        DelegablePermission.REVENUE_VIEW,
    )

    with pytest.raises(HTTPException) as error:
        require_financial_permissions(
            context,
            DelegablePermission.PROFIT_VIEW,
        )

    assert error.value.status_code == 403


def test_all_analytics_routes_have_permission_checks():
    path = Path(__file__).resolve().parents[1] / "app/routers/analytics.py"
    tree = ast.parse(path.read_text())

    expected = {
        "top_products",
        "bottom_products",
        "pnl",
        "pnl_trend",
        "insights",
        "pnl_ytd",
        "overview",
        "expenses_by_category",
        "expenses_by_supplier",
        "invoices_summary",
        "payments_by_method",
    }

    checked = set()

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in expected:
            continue

        assert node.body, f"{node.name}: funzione vuota"
        first = node.body[0]

        assert isinstance(first, ast.Expr), node.name
        assert isinstance(first.value, ast.Call), node.name
        assert isinstance(first.value.func, ast.Name), node.name
        assert first.value.func.id == "require_financial_permissions", node.name

        checked.add(node.name)

    assert checked == expected


def test_profit_endpoints_require_profit_permission():
    path = Path(__file__).resolve().parents[1] / "app/routers/analytics.py"
    tree = ast.parse(path.read_text())

    profit_endpoints = {
        "pnl", "pnl_trend", "insights", "pnl_ytd", "overview"
    }

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in profit_endpoints:
            first = node.body[0].value
            permissions = {
                ast.unparse(argument)
                for argument in first.args[1:]
            }
            assert "DelegablePermission.PROFIT_VIEW" in permissions, node.name



def test_global_admin_can_access_financial_data():
    context = make_context(
        MembershipRole.staff,
        is_global_admin=True,
    )

    require_financial_permissions(
        context,
        DelegablePermission.ANALYTICS_VIEW,
        DelegablePermission.PROFIT_VIEW,
    )
