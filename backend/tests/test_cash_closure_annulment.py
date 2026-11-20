from fastapi.testclient import TestClient
import hashlib
import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    AdminAudit,
    CashClosureIntake,
    DailyCashClosure,
    Document,
)
from test_document_tenant_scope import (
    document_environment,
    headers,
    login,
    select_bar,
)


def create_approved_closure(factory, bar_id, suffix):
    with factory() as db:
        document = Document(
            bar_id=bar_id,
            month="2026-11",
            original_filename=f"{suffix}.png",
            stored_filename=f"{suffix}.png",
            section="cash",
            document_type="PNG",
            category="Immagine",
            result="Test OCR",
            file_url=f"/uploads/documents/{suffix}.png",
            preview_url=f"/uploads/documents/{suffix}.png",
        )
        db.add(document)
        db.flush()

        closure = DailyCashClosure(
            bar_id=bar_id,
            document_id=document.id,
            date=dt.date(2026, 11, 20),
            closure_number=suffix,
            total_amount=Decimal("150.00"),
        )
        db.add(closure)
        db.flush()

        intake = CashClosureIntake(
            bar_id=bar_id,
            document_id=document.id,
            closure_id=closure.id,
            source_sha256=hashlib.sha256(suffix.encode("utf-8")).hexdigest(),
            classification="SAVE_FOR_REVIEW",
            status="approved",
            ocr_values={},
            anomalies=[],
        )
        db.add(intake)
        db.commit()

        return intake.id, closure.id, document.id


def audit_count(db):
    return db.scalar(
        select(func.count()).select_from(AdminAudit).where(
            AdminAudit.action == "cash_closure.annul"
        )
    )


def test_owner_can_annul_and_history_is_preserved(document_environment):
    client, factory, ids, _root, _app = document_environment

    intake_id, closure_id, document_id = create_approved_closure(
        factory, ids["bar_one"], "ANNUL-OWNER"
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    response = client.post(
        f"/cash-closures/review/{intake_id}/annul",
        headers=headers(csrf),
        json={"reason": "  Errore nei corrispettivi  "},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "annulled"

    with factory() as db:
        intake = db.get(CashClosureIntake, intake_id)
        closure = db.get(DailyCashClosure, closure_id)

        assert intake.status == "annulled"
        assert closure.annulled_at is not None
        assert closure.annulment_reason == "Errore nei corrispettivi"
        assert db.get(Document, document_id) is not None

        audit = db.scalar(
            select(AdminAudit).where(
                AdminAudit.action == "cash_closure.annul"
            )
        )
        assert audit is not None
        assert audit.changes["closure_id"] == closure_id
        assert audit.changes["reason"] == "Errore nei corrispettivi"

    repeated = client.post(
        f"/cash-closures/review/{intake_id}/annul",
        headers=headers(csrf),
        json={"reason": "Secondo annullamento"},
    )

    assert repeated.status_code == 409

    with factory() as db:
        assert audit_count(db) == 1


def test_staff_with_review_permission_cannot_annul(document_environment):
    client, factory, ids, _root, _app = document_environment

    intake_id, closure_id, _document_id = create_approved_closure(
        factory, ids["bar_one"], "ANNUL-STAFF"
    )

    csrf = login(client, "staff@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    response = client.post(
        f"/cash-closures/review/{intake_id}/annul",
        headers=headers(csrf),
        json={"reason": "Tentativo dipendente"},
    )

    assert response.status_code == 403, response.text

    with factory() as db:
        assert db.get(CashClosureIntake, intake_id).status == "approved"
        assert db.get(DailyCashClosure, closure_id).annulled_at is None
        assert audit_count(db) == 0


def test_annulment_requires_csrf(document_environment):
    client, factory, ids, _root, _app = document_environment

    intake_id, closure_id, _document_id = create_approved_closure(
        factory, ids["bar_one"], "ANNUL-CSRF"
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    response = client.post(
        f"/cash-closures/review/{intake_id}/annul",
        headers={"Origin": headers(csrf)["Origin"]},
        json={"reason": "Tentativo senza CSRF"},
    )

    assert response.status_code in (401, 403), response.text

    with factory() as db:
        assert db.get(DailyCashClosure, closure_id).annulled_at is None
        assert audit_count(db) == 0


def test_owner_cannot_annul_other_bar_closure(document_environment):
    client, factory, ids, _root, _app = document_environment

    intake_id, closure_id, _document_id = create_approved_closure(
        factory, ids["bar_two"], "ANNUL-OTHER-BAR"
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    response = client.post(
        f"/cash-closures/review/{intake_id}/annul",
        headers=headers(csrf),
        json={"reason": "Tentativo altro bar"},
    )

    assert response.status_code == 404, response.text

    with factory() as db:
        assert db.get(CashClosureIntake, intake_id).status == "approved"
        assert db.get(DailyCashClosure, closure_id).annulled_at is None
        assert audit_count(db) == 0


def test_annulment_requires_nonblank_reason(document_environment):
    client, factory, ids, _root, _app = document_environment

    intake_id, closure_id, _document_id = create_approved_closure(
        factory, ids["bar_one"], "ANNUL-REASON"
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    response = client.post(
        f"/cash-closures/review/{intake_id}/annul",
        headers=headers(csrf),
        json={"reason": "   "},
    )

    assert response.status_code == 422, response.text

    with factory() as db:
        assert db.get(CashClosureIntake, intake_id).status == "approved"
        assert db.get(DailyCashClosure, closure_id).annulled_at is None
        assert audit_count(db) == 0


def test_annulment_updates_financial_kpis_and_preserves_history(
    document_environment,
):
    client, factory, ids, _root, _app = document_environment
    bar_id = ids["bar_one"]

    intake_id, closure_id, document_id = create_approved_closure(
        factory, bar_id, "ANNUL-KPI"
    )

    with factory() as db:
        annulled_closure = db.get(DailyCashClosure, closure_id)
        annulled_closure.total_amount = Decimal("200.00")
        annulled_closure.date = dt.date(2026, 11, 20)
        annulled_closure.created_at = dt.datetime(2026, 11, 20, 12)

        active_closure = DailyCashClosure(
            bar_id=bar_id,
            date=dt.date(2026, 11, 19),
            closure_number="ACTIVE-KPI",
            total_amount=Decimal("150.00"),
            created_at=dt.datetime(2026, 11, 19, 12),
        )
        db.add(active_closure)
        db.commit()
        active_closure_id = active_closure.id

    csrf = login(client, "owner@example.test")
    assert select_bar(client, bar_id, csrf).status_code == 200

    def get_pnl():
        response = client.get("/analytics/pnl?month=2026-11")
        assert response.status_code == 200, response.text
        return response.json()

    def get_overview():
        response = client.get("/analytics/overview?month=2026-11")
        assert response.status_code == 200, response.text
        return response.json()

    before = get_pnl()
    assert before["revenue"] == 350
    assert before["expenses"] == 0
    assert before["profit"] == 350

    overview_before = get_overview()
    assert overview_before["latest_cash_closure_date"] == "2026-11-20"

    response = client.post(
        f"/cash-closures/review/{intake_id}/annul",
        headers=headers(csrf),
        json={"reason": "Importo errato: annullamento KPI"},
    )
    assert response.status_code == 200, response.text

    after = get_pnl()
    assert after["revenue"] == 150
    assert after["expenses"] == 0
    assert after["profit"] == 150

    overview_after = get_overview()
    assert overview_after["pnl_summary"]["revenue"] == 150
    assert overview_after["pnl_summary"]["profit"] == 150
    assert overview_after["latest_cash_closure_date"] == "2026-11-19"

    with factory() as db:
        annulled = db.get(DailyCashClosure, closure_id)
        active = db.get(DailyCashClosure, active_closure_id)
        intake = db.get(CashClosureIntake, intake_id)

        assert annulled is not None
        assert annulled.total_amount == Decimal("200.00")
        assert annulled.annulled_at is not None
        assert annulled.annulment_reason == (
            "Importo errato: annullamento KPI"
        )
        assert active is not None
        assert active.annulled_at is None
        assert intake.status == "annulled"
        assert db.get(Document, document_id) is not None
        assert audit_count(db) == 1


def test_cash_closure_history_owner_and_annulment(document_environment):
    client, factory, ids, _root, _app = document_environment

    first_id, first_closure_id, _ = create_approved_closure(
        factory, ids["bar_one"], "HISTORY-ONE"
    )
    second_id, second_closure_id, _ = create_approved_closure(
        factory, ids["bar_one"], "HISTORY-TWO"
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    before = client.get("/cash-closures/history")
    assert before.status_code == 200, before.text

    before_by_id = {item["id"]: item for item in before.json()}
    assert first_id in before_by_id
    assert second_id in before_by_id
    assert before_by_id[first_id]["status"] == "approved"
    assert before_by_id[first_id]["can_annul"] is True

    annul = client.post(
        f"/cash-closures/review/{first_id}/annul",
        headers=headers(csrf),
        json={"reason": "Errore verificato nello storico"},
    )
    assert annul.status_code == 200, annul.text

    after = client.get("/cash-closures/history")
    assert after.status_code == 200, after.text

    after_by_id = {item["id"]: item for item in after.json()}
    assert after_by_id[first_id]["status"] == "annulled"
    assert after_by_id[first_id]["can_annul"] is False
    assert after_by_id[first_id]["annulment_reason"] == (
        "Errore verificato nello storico"
    )
    assert after_by_id[first_id]["annulled_at"] is not None
    assert after_by_id[second_id]["status"] == "approved"
    assert after_by_id[second_id]["can_annul"] is True

    with factory() as db:
        assert db.get(DailyCashClosure, first_closure_id) is not None
        assert db.get(DailyCashClosure, second_closure_id) is not None


def test_cash_closure_history_month_filter(document_environment):
    client, factory, ids, _root, _app = document_environment

    november_id, _, _ = create_approved_closure(
        factory, ids["bar_one"], "HISTORY-NOV"
    )
    october_id, october_closure_id, _ = create_approved_closure(
        factory, ids["bar_one"], "HISTORY-OCT"
    )

    with factory() as db:
        db.get(DailyCashClosure, october_closure_id).date = (
            dt.date(2026, 10, 20)
        )
        db.commit()

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    response = client.get("/cash-closures/history?month=2026-11")
    assert response.status_code == 200, response.text

    returned_ids = {item["id"] for item in response.json()}
    assert november_id in returned_ids
    assert october_id not in returned_ids

    invalid = client.get("/cash-closures/history?month=2026-13")
    assert invalid.status_code == 422


def test_cash_closure_history_isolated_between_bars(document_environment):
    client, factory, ids, _root, _app = document_environment

    own_id, _, _ = create_approved_closure(
        factory, ids["bar_one"], "HISTORY-OWN"
    )
    foreign_id, _, _ = create_approved_closure(
        factory, ids["bar_two"], "HISTORY-FOREIGN"
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    response = client.get("/cash-closures/history")
    assert response.status_code == 200, response.text

    returned_ids = {item["id"] for item in response.json()}
    assert own_id in returned_ids
    assert foreign_id not in returned_ids


def test_cash_closure_history_granular_read_permissions(
    document_environment,
):
    _fixture_client, factory, ids, _root, app = document_environment
    bar_id = ids["bar_one"]

    own_id, _, own_document_id = create_approved_closure(
        factory, bar_id, "HISTORY-STAFF"
    )
    other_id, _, other_document_id = create_approved_closure(
        factory, bar_id, "HISTORY-OWNER"
    )

    with factory() as db:
        db.get(Document, own_document_id).created_by_user_id = ids["staff"]
        db.get(Document, other_document_id).created_by_user_id = ids["owner"]
        db.commit()

    client = TestClient(app)
    csrf = login(client, "staff@example.test")
    assert select_bar(client, bar_id, csrf).status_code == 200

    staff_response = client.get("/cash-closures/history")
    assert staff_response.status_code == 200, staff_response.text

    staff_items = {
        item["id"]: item for item in staff_response.json()
    }
    assert own_id in staff_items
    assert other_id not in staff_items
    assert staff_items[own_id]["can_annul"] is False

    client.close()
    client = TestClient(app)
    csrf = login(client, "manager@example.test")
    assert select_bar(client, bar_id, csrf).status_code == 200

    manager_response = client.get("/cash-closures/history")
    assert manager_response.status_code == 200, manager_response.text

    manager_items = {
        item["id"]: item for item in manager_response.json()
    }
    assert own_id in manager_items
    assert other_id in manager_items
    assert all(
        item["can_annul"] is False
        for item in manager_items.values()
    )

    client.close()
    client = TestClient(app)

    csrf = login(client, "owner@example.test")
    assert select_bar(client, bar_id, csrf).status_code == 200

    owner_response = client.get("/cash-closures/history")
    assert owner_response.status_code == 200, owner_response.text

    owner_items = {
        item["id"]: item for item in owner_response.json()
    }
    assert own_id in owner_items
    assert other_id in owner_items
    assert owner_items[own_id]["can_annul"] is True
    assert owner_items[other_id]["can_annul"] is True

    client.close()
