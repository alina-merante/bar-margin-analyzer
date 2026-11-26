import datetime as dt
from decimal import Decimal

from app.models import CashClosureIntake, DailyCashClosure, Document
from test_document_tenant_scope import (
    document_environment,
    headers,
    login,
    select_bar,
)



def create_test_document(factory, bar_id, filename):
    with factory() as db:
        document = Document(
            bar_id=bar_id,
            month="2026-11",
            original_filename=filename,
            stored_filename=filename,
            section="cash",
            document_type="PNG",
            category="Immagine",
            result="Test",
            file_url=f"/uploads/documents/{filename}",
            preview_url=f"/uploads/documents/{filename}",
        )
        db.add(document)
        db.commit()
        return document.id



def test_approved_closure_document_cannot_be_deleted(document_environment):
    client, factory, ids, _root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    document_id = create_test_document(factory, ids["bar_one"], "approved.png")

    with factory() as db:
        closure = DailyCashClosure(
            bar_id=ids["bar_one"],
            document_id=document_id,
            date=dt.date(2026, 11, 19),
            closure_number="APPROVED-1",
            total_amount=Decimal("100.00"),
        )
        db.add(closure)
        db.flush()

        intake = CashClosureIntake(
            bar_id=ids["bar_one"],
            document_id=document_id,
            closure_id=closure.id,
            source_sha256="c" * 64,
            classification="SAVE_FOR_REVIEW",
            status="approved",
            ocr_values={},
            anomalies=[],
        )
        db.add(intake)
        db.commit()
        closure_id = closure.id
        intake_id = intake.id

    response = client.delete(
        f"/documents/{document_id}",
        headers=headers(csrf),
    )
    assert response.status_code == 409

    with factory() as db:
        assert db.get(Document, document_id) is not None
        assert db.get(DailyCashClosure, closure_id) is not None
        assert db.get(CashClosureIntake, intake_id) is not None


def test_indirect_approved_closure_link_cannot_be_deleted(document_environment):
    client, factory, ids, _root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    source_id = create_test_document(factory, ids["bar_one"], "source.png")
    linked_id = create_test_document(factory, ids["bar_one"], "linked.png")

    with factory() as db:
        closure = DailyCashClosure(
            bar_id=ids["bar_one"],
            document_id=linked_id,
            date=dt.date(2026, 11, 18),
            closure_number="APPROVED-2",
            total_amount=Decimal("200.00"),
        )
        db.add(closure)
        db.flush()

        intake = CashClosureIntake(
            bar_id=ids["bar_one"],
            document_id=source_id,
            closure_id=closure.id,
            source_sha256="d" * 64,
            classification="SAVE_FOR_REVIEW",
            status="approved",
            ocr_values={},
            anomalies=[],
        )
        db.add(intake)
        db.commit()
        closure_id = closure.id
        intake_id = intake.id

    response = client.delete(
        f"/documents/{linked_id}",
        headers=headers(csrf),
    )
    assert response.status_code == 409

    with factory() as db:
        assert db.get(Document, linked_id) is not None
        assert db.get(DailyCashClosure, closure_id) is not None
        assert db.get(CashClosureIntake, intake_id) is not None
