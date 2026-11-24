import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import config
from app.routers import documents
from test_document_tenant_scope import document_environment


class FakeDB:
    def __init__(self, intake):
        self.intake = intake

    def scalar(self, _query):
        return self.intake


@pytest.fixture
def recovery_environment(tmp_path, monkeypatch):
    directory = tmp_path / "documents"
    directory.mkdir()

    monkeypatch.setattr(config, "UPLOAD_DOCUMENTS_DIR", str(directory))
    monkeypatch.setattr(documents, "UPLOAD_DOCUMENTS_DIR", str(directory))

    return directory


def make_intake(content, bar_id=1):
    filename = "original.png"
    document = SimpleNamespace(
        bar_id=bar_id,
        stored_filename=filename,
        file_url=f"/uploads/documents/{filename}",
    )
    return SimpleNamespace(
        bar_id=bar_id,
        source_sha256=hashlib.sha256(content).hexdigest(),
        document=document,
    )


def test_restores_missing_original(recovery_environment):
    content = b"original-cash-photo"
    intake = make_intake(content)

    restored = documents.restore_missing_cash_document(
        FakeDB(intake),
        bar_id=1,
        source_sha256=intake.source_sha256,
        content=content,
    )

    assert restored is True
    assert (recovery_environment / "original.png").read_bytes() == content


def test_existing_file_is_not_overwritten(recovery_environment):
    content = b"original-cash-photo"
    intake = make_intake(content)
    destination = recovery_environment / "original.png"
    destination.write_bytes(b"existing-content")

    restored = documents.restore_missing_cash_document(
        FakeDB(intake),
        bar_id=1,
        source_sha256=intake.source_sha256,
        content=content,
    )

    assert restored is False
    assert destination.read_bytes() == b"existing-content"


def test_different_content_is_rejected(recovery_environment):
    content = b"original-cash-photo"
    intake = make_intake(content)

    restored = documents.restore_missing_cash_document(
        FakeDB(intake),
        bar_id=1,
        source_sha256=intake.source_sha256,
        content=b"different-photo",
    )

    assert restored is False
    assert not (recovery_environment / "original.png").exists()


def test_other_bar_document_is_not_restored(recovery_environment):
    content = b"original-cash-photo"
    intake = make_intake(content, bar_id=2)

    restored = documents.restore_missing_cash_document(
        FakeDB(intake),
        bar_id=1,
        source_sha256=intake.source_sha256,
        content=content,
    )

    assert restored is False
    assert not (recovery_environment / "original.png").exists()


def test_symlink_is_not_overwritten(recovery_environment, tmp_path):
    content = b"original-cash-photo"
    intake = make_intake(content)
    target = tmp_path / "protected.txt"
    target.write_bytes(b"protected")

    (recovery_environment / "original.png").symlink_to(target)

    restored = documents.restore_missing_cash_document(
        FakeDB(intake),
        bar_id=1,
        source_sha256=intake.source_sha256,
        content=content,
    )

    assert restored is False
    assert target.read_bytes() == b"protected"


def test_upload_restores_original_without_new_records(
    document_environment, monkeypatch
):
    from sqlalchemy import select
    from app.models import CashClosureIntake, Document
    from test_document_tenant_scope import (
        headers, login, select_bar, upload,
    )

    client, factory, ids, root, _app = document_environment

    extracted = {
        "date": __import__("datetime").date(2023, 9, 26),
        "closure_number": "25",
        "total_amount": __import__("decimal").Decimal("303.50"),
        "cash_amount": __import__("decimal").Decimal("200.00"),
        "card_amount": __import__("decimal").Decimal("103.50"),
        "receipts_count": 25,
        "diagnostics": {
            "anomalies": [],
            "total_label": "explicit",
            "fields": {
                "date": {"status": "ok"},
                "closure_number": {"status": "ok"},
                "total_amount": {"status": "ok"},
            },
        },
    }

    monkeypatch.setattr(
        documents,
        "extract_daily_cash_closure",
        lambda *_args: extracted,
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    content = b"cash-closure-original-photo"

    first = upload(client, csrf, content, "cash")
    assert first.status_code == 200, first.text
    original = first.json()

    with factory() as db:
        before_documents = len(db.scalars(select(Document)).all())
        before_intakes = len(db.scalars(select(CashClosureIntake)).all())

    destination = root / "documents" / original["stored_filename"]
    assert destination.is_file()
    destination.unlink()

    assert client.get(original["file_url"]).status_code == 404

    restored = upload(client, csrf, content, "cash")
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_original"] is True
    assert restored.json()["id"] == original["id"]

    assert destination.read_bytes() == content
    assert client.get(original["file_url"]).content == content

    with factory() as db:
        assert len(db.scalars(select(Document)).all()) == before_documents
        assert len(db.scalars(select(CashClosureIntake)).all()) == before_intakes

    duplicate = upload(client, csrf, content, "cash")
    assert duplicate.status_code == 409


def test_approved_closure_recovery_preserves_accounting(
    document_environment, monkeypatch
):
    import datetime as dt
    from decimal import Decimal
    from sqlalchemy import select
    from app.models import CashClosureIntake, DailyCashClosure, Document
    from test_document_tenant_scope import login, select_bar, upload, headers

    client, factory, ids, root, _app = document_environment

    extracted = {
        "date": dt.date(2023, 9, 26),
        "closure_number": "25",
        "total_amount": Decimal("303.50"),
        "cash_amount": Decimal("200.00"),
        "card_amount": Decimal("103.50"),
        "receipts_count": 25,
        "diagnostics": {
            "anomalies": [],
            "total_label": "explicit",
            "fields": {
                "date": {"status": "ok"},
                "closure_number": {"status": "ok"},
                "total_amount": {"status": "ok"},
            },
        },
    }

    monkeypatch.setattr(
        documents, "extract_daily_cash_closure",
        lambda *_args: extracted,
    )

    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    content = b"approved-closure-original-photo"
    first = upload(client, csrf, content, "cash")
    assert first.status_code == 200, first.text
    original = first.json()

    with factory() as db:
        intake = db.scalars(select(CashClosureIntake)).one()
        intake_id = intake.id

    verification = client.post(
        f"/cash-closures/review/{intake_id}/verify",
        headers=headers(csrf),
    )
    assert verification.status_code == 200, verification.text

    approval = client.post(
        f"/cash-closures/review/{intake_id}/approve",
        headers=headers(csrf),
    )
    assert approval.status_code == 200, approval.text

    with factory() as db:
        before = db.scalars(select(DailyCashClosure)).one()
        closure_id = before.id
        amount = before.total_amount
        document_id = before.document_id

    destination = root / "documents" / original["stored_filename"]
    destination.unlink()

    restored = upload(client, csrf, content, "cash")
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_original"] is True
    assert restored.json()["id"] == original["id"]
    assert destination.read_bytes() == content

    with factory() as db:
        closure = db.get(DailyCashClosure, closure_id)
        assert closure.total_amount == amount
        assert closure.document_id == document_id
        assert len(db.scalars(select(DailyCashClosure)).all()) == 1
        assert len(db.scalars(select(CashClosureIntake)).all()) == 1
        assert len(db.scalars(select(Document)).all()) == 1


def test_recovery_cannot_access_another_bar(
    document_environment, monkeypatch
):
    import datetime as dt
    from decimal import Decimal
    from sqlalchemy import select
    from app.models import CashClosureIntake, Document
    from test_document_tenant_scope import login, select_bar, upload

    client, factory, ids, root, _app = document_environment

    extracted = {
        "date": dt.date(2023, 9, 26),
        "closure_number": "25",
        "total_amount": Decimal("303.50"),
        "cash_amount": Decimal("200.00"),
        "card_amount": Decimal("103.50"),
        "receipts_count": 25,
        "diagnostics": {
            "anomalies": [],
            "total_label": "explicit",
            "fields": {
                "date": {"status": "ok"},
                "closure_number": {"status": "ok"},
                "total_amount": {"status": "ok"},
            },
        },
    }

    monkeypatch.setattr(
        documents, "extract_daily_cash_closure",
        lambda *_args: extracted,
    )

    csrf = login(client, "owner@example.test")

    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    content = b"original-photo-bar-one"
    first = upload(client, csrf, content, "cash")
    assert first.status_code == 200, first.text
    original = first.json()

    destination = root / "documents" / original["stored_filename"]
    destination.unlink()

    assert select_bar(client, ids["bar_two"], csrf).status_code == 200

    response = upload(client, csrf, content, "cash")
    assert response.status_code in (200, 409), response.text

    assert not destination.exists()
    assert client.get(original["file_url"]).status_code == 404

    with factory() as db:
        original_document = db.get(Document, original["id"])
        assert original_document.bar_id == ids["bar_one"]

        original_intake = db.scalar(
            select(CashClosureIntake).where(
                CashClosureIntake.document_id == original["id"]
            )
        )
        assert original_intake.bar_id == ids["bar_one"]
