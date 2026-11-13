import datetime as dt
import importlib
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import sessionmaker

from app import config
from app.database import Base, get_db
from app.models import (
    AuthSession, Bar, CashClosureIntake, DailyCashClosure, Document, Invoice, InvoiceStatus,
    Payment, Transaction, User, UserBarMembership,
)
from app.routers import documents, finance
from app.services.document_ocr import DocumentReadError
from test_operational_tenant_scope import ALLOWED_ORIGIN, login, seed_bars, select_bar


@pytest.fixture
def document_environment(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(config, "UPLOAD_BASE_PATH", str(root))
    for kind in ("documents", "previews", "invoices"):
        directory = root / kind
        directory.mkdir(parents=True)
        monkeypatch.setattr(config, f"UPLOAD_{kind.upper()}_DIR", str(directory))
    monkeypatch.setattr(documents, "UPLOAD_PREVIEWS_DIR", str(root / "previews"))
    monkeypatch.setattr(finance, "UPLOAD_INVOICES_DIR", str(root / "invoices"))

    engine = create_engine(f"sqlite:///{tmp_path / 'documents.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    ids = seed_bars(factory)
    app = importlib.import_module("app.main").app

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, factory, ids, root, app
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def headers(csrf):
    return {"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf}


def upload(client, csrf, content=b"image", section="other", **extra):
    return client.post(
        "/documents/upload",
        headers=headers(csrf),
        files={"file": ("source.png", content, "image/png")},
        data={"month": "2026-07", "section": section, **extra},
    )


def test_upload_download_switch_legacy_traversal_and_cache(document_environment):
    client, factory, ids, root, _app = document_environment
    assert client.get("/documents").status_code == 401
    for path in (
        "/uploads/documents/anything.png",
        "/uploads/previews/anything.png",
        "/uploads/invoices/anything.pdf",
    ):
        response = client.get(path)
        assert response.status_code == 401
        assert "no-store" in response.headers["cache-control"]
    csrf = login(client, "owner@example.test")
    assert client.get("/documents").status_code == 409
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    first = upload(client, csrf, b"one").json()
    assert client.get(first["file_url"]).content == b"one"
    response = client.get(first["preview_url"])
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]

    assert select_bar(client, ids["bar_two"], csrf).status_code == 200
    second = upload(client, csrf, b"two").json()
    assert client.get(first["file_url"]).status_code == 404
    assert client.delete(f"/documents/{first['id']}", headers=headers(csrf)).status_code == 404
    assert [row["id"] for row in client.get("/documents").json()] == [second["id"]]

    with factory() as db:
        legacy = Document(
            bar_id=None, month="2026-07", original_filename="legacy.png",
            stored_filename="legacy.png", section="other", document_type="PNG",
            category="image", result="legacy", file_url="/uploads/documents/legacy.png",
            preview_url="/uploads/documents/legacy.png",
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id
    (root / "documents" / "legacy.png").write_bytes(b"legacy")
    assert client.get("/uploads/documents/legacy.png").status_code == 404
    assert client.delete(f"/documents/{legacy_id}", headers=headers(csrf)).status_code == 404
    assert client.get("/uploads/documents/%2e%2e%2flegacy.png").status_code == 404
    assert client.get("/uploads/documents/%5c..%5clegacy.png").status_code == 404
    assert client.get("/uploads/other/legacy.png").status_code == 404

    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert client.get(first["file_url"]).content == b"one"
    assert client.get(second["file_url"]).status_code == 404
    assert upload(client, csrf, bar_id=str(ids["bar_two"])).status_code == 422
    with factory() as db:
        assert db.get(Document, first["id"]).bar_id == ids["bar_one"]
        assert db.get(Document, second["id"]).bar_id == ids["bar_two"]


def test_stale_tab_cannot_upload_pay_or_download_other_bar(document_environment):
    client, factory, ids, root, app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    uploaded = upload(client, csrf, b"private-document").json()
    (root / "invoices" / "invoice.pdf").write_bytes(b"private-invoice")
    with factory() as db:
        db.add(Invoice(
            bar_id=ids["bar_one"], supplier="A", invoice_number="A-1",
            issue_date=dt.date(2026, 7, 1), due_date=dt.date(2026, 7, 2),
            total=Decimal("10"), vat=Decimal("0"), status=InvoiceStatus.pending,
            file_url="/uploads/invoices/invoice.pdf",
        ))
        db.commit()

    with TestClient(app) as second_tab:
        second_tab.cookies.update(client.cookies)
        assert select_bar(second_tab, ids["bar_two"], csrf).status_code == 200

        assert upload(client, csrf, b"stale-upload").status_code == 409
        payment = client.post(
            "/payments",
            headers=headers(csrf),
            json={
                "date": "2026-07-05",
                "amount": "5.00",
                "method": "cash",
                "counterparty": "Supplier",
                "reference": "stale-tab",
            },
        )
        assert payment.status_code == 409
        assert client.get(uploaded["file_url"]).status_code == 409
        assert client.get("/uploads/invoices/invoice.pdf").status_code == 409
        assert second_tab.get(uploaded["file_url"]).status_code == 404

    with factory() as db:
        assert db.query(Document).count() == 1
        assert db.query(Payment).count() == 0


def test_upload_revalidates_bar_before_persisting(document_environment, monkeypatch):
    client, factory, ids, root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    def switch_bar_during_ocr(_content, _extension):
        with factory() as db:
            auth_session = db.query(AuthSession).one()
            auth_session.active_bar_id = ids["bar_two"]
            db.commit()
        return {
            "date": dt.date(2026, 7, 14),
            "closure_number": "201",
            "total_amount": Decimal("100"),
            "cash_amount": Decimal("60"),
            "card_amount": Decimal("40"),
            "receipts_count": None,
            "diagnostics": {},
        }

    monkeypatch.setattr(documents, "extract_daily_cash_closure", switch_bar_during_ocr)
    monkeypatch.setattr(
        documents.cash_closure_policy, "classify_closure",
        lambda _data: documents.cash_closure_policy.SAVE_FOR_REVIEW,
    )
    response = upload(client, csrf, b"cash-document", "cash")
    assert response.status_code == 409
    with factory() as db:
        assert db.query(Document).count() == 0
        assert db.query(CashClosureIntake).count() == 0
    assert list((root / "documents").iterdir()) == []


def test_payment_revalidates_bar_before_commit(document_environment, monkeypatch):
    client, factory, ids, _root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    original_revalidate = finance.revalidate_active_bar_context

    def switch_bar_before_commit(request, db, bar_id, *, lock=False):
        db.execute(update(AuthSession).values(active_bar_id=ids["bar_two"]))
        return original_revalidate(request, db, bar_id, lock=lock)

    monkeypatch.setattr(
        finance, "revalidate_active_bar_context", switch_bar_before_commit
    )
    response = client.post(
        "/payments",
        headers=headers(csrf),
        json={
            "date": "2026-07-05",
            "amount": "5.00",
            "method": "cash",
            "counterparty": "Supplier",
            "reference": "mid-request-switch",
        },
    )
    assert response.status_code == 409
    with factory() as db:
        assert db.query(Payment).count() == 0
        assert db.query(AuthSession).one().active_bar_id == ids["bar_one"]


def test_ocr_review_correction_approval_and_deduplication(document_environment, monkeypatch):
    client, factory, ids, _root, _app = document_environment
    monkeypatch.setattr(
        documents, "extract_text_from_document",
        lambda content, extension: "NUM. CHIUSURA 201\nDATA 14-07-26",
    )
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    first = upload(client, csrf, b"same-source", "cash")
    assert first.status_code == 200, first.text
    assert first.json()["cash_closure_classification"] == "SAVE_FOR_REVIEW"
    assert upload(client, csrf, b"same-source", "cash").status_code == 409
    review_one = client.get("/cash-closures/review").json()[0]
    assert review_one["document"]["id"] == first.json()["id"]

    assert select_bar(client, ids["bar_two"], csrf).status_code == 200
    second = upload(client, csrf, b"same-source", "cash")
    assert second.status_code == 200, second.text
    review_two = client.get("/cash-closures/review").json()[0]
    assert client.get(f"/cash-closures/review/{review_one['id']}").status_code == 404
    assert client.patch(
        f"/cash-closures/review/{review_one['id']}", headers=headers(csrf),
        json={"total_amount": "100.00"},
    ).status_code == 404
    assert client.post(
        f"/cash-closures/review/{review_one['id']}/approve", headers=headers(csrf)
    ).status_code == 404

    correction = {
        "total_amount": "100.00", "cash_amount": "60.00",
        "card_amount": "40.00", "receipts_count": 25,
    }
    for bar, intake in ((ids["bar_two"], review_two), (ids["bar_one"], review_one)):
        assert select_bar(client, bar, csrf).status_code == 200
        assert client.patch(
            f"/cash-closures/review/{intake['id']}", headers=headers(csrf),
            json={"receipts_count": -1},
        ).status_code == 422
        assert client.patch(
            f"/cash-closures/review/{intake['id']}", headers=headers(csrf),
            json={**correction, "bar_id": ids["bar_two"]},
        ).status_code == 422
        corrected = client.patch(
            f"/cash-closures/review/{intake['id']}", headers=headers(csrf), json=correction
        )
        assert corrected.status_code == 200, corrected.text
        approved = client.post(
            f"/cash-closures/review/{intake['id']}/approve", headers=headers(csrf)
        )
        assert approved.status_code == 200, approved.text
        assert client.post(
            f"/cash-closures/review/{intake['id']}/approve", headers=headers(csrf)
        ).json()["closure_id"] == approved.json()["closure_id"]
        with factory() as db:
            row = db.get(CashClosureIntake, intake["id"])
            closure = db.get(DailyCashClosure, row.closure_id)
            assert row.bar_id == row.document.bar_id == closure.bar_id == bar
            assert closure.document_id == row.document_id
            assert closure.receipts_count == 25
    with factory() as db:
        assert len(db.scalars(select(DailyCashClosure)).all()) == 2
        assert len(db.scalars(select(CashClosureIntake)).all()) == 2


def test_reprocess_preview_confirmation_preserves_history_and_tenant_scope(
    document_environment, monkeypatch
):
    client, factory, ids, root, _app = document_environment
    old_text = "NUM. CHIUSURA 10\nDATA 14-07-2026"
    new_text = (
        "Data: 26/09/2023\nNumero scontrini: 25\nTotale scontrini: 303,50\n"
        "Totale fatture: 5,50\nPagamenti contanti: 255,50\nNumero azzeramenti: 10"
    )
    ocr = {"text": old_text}
    monkeypatch.setattr(documents, "extract_text_from_document", lambda *_args: ocr["text"])
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    upload_response = upload(client, csrf, b"original-image", "cash")
    assert upload_response.status_code == 200
    document_id = upload_response.json()["id"]
    duplicate = upload(client, csrf, b"original-image", "cash")
    assert duplicate.status_code == 409
    assert "non è stato rielaborato" in duplicate.json()["detail"]
    review = client.get("/cash-closures/review").json()[0]
    url = f"/cash-closures/review/{review['id']}"
    assert client.patch(
        url, headers=headers(csrf),
        json={"closure_number": "MANUALE", "total_amount": "400.00", "receipts_count": 24},
    ).status_code == 200
    ocr["text"] = new_text
    assert client.post(f"{url}/reprocess/preview").status_code == 403
    assert client.post(f"{url}/reprocess/preview", headers={
        "X-CSRF-Token": csrf, "Origin": "https://evil.example"
    }).status_code == 403

    preview_response = client.post(f"{url}/reprocess/preview", headers=headers(csrf))
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["previous"]["closure_number"] == "MANUALE"
    assert preview["previous"]["total_amount"] == "400.00"
    assert preview["previous"]["receipts_count"] == 24
    assert preview["proposed"]["closure_number"] is None
    assert preview["proposed"]["total_amount"] is None
    assert preview["proposed"]["receipts_total"] == "303.50"
    assert preview["proposed"]["receipts_count"] == 25
    assert client.get(url).json()["closure_number"] == "MANUALE"

    payload = {key: preview[key] for key in ("review_version", "extraction_version")}
    assert client.post(f"{url}/reprocess", json=payload).status_code == 403
    assert select_bar(client, ids["bar_two"], csrf).status_code == 200
    assert client.post(f"{url}/reprocess/preview", headers=headers(csrf)).status_code == 404
    assert client.post(f"{url}/reprocess", headers=headers(csrf), json=payload).status_code == 404
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    ocr["text"] = old_text
    changed = client.post(f"{url}/reprocess", headers=headers(csrf), json=payload)
    assert changed.status_code == 409
    assert client.get(url).json()["closure_number"] == "MANUALE"
    ocr["text"] = new_text
    confirmed = client.post(f"{url}/reprocess", headers=headers(csrf), json=payload)
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result["id"] == review["id"]
    assert result["document"]["id"] == document_id
    assert result["document"]["month"] == "2023-09"
    assert result["status"] == "pending"
    assert result["classification"] == "SAVE_FOR_REVIEW"
    assert result["closure_number"] is None and result["total_amount"] is None
    assert result["receipts_count"] == 25 and result["receipts_total"] == "303.50"
    refreshed = client.get("/cash-closures/review").json()[0]
    assert refreshed["id"] == review["id"]
    assert refreshed["document"]["id"] == document_id
    assert refreshed["receipts_total"] == "303.50" and refreshed["total_amount"] is None
    previous = result["ocr_values"]["reprocessing_history"][0]
    assert previous["previous_values"]["closure_number"] == "MANUALE"
    assert previous["previous_values"]["total_amount"] == "400.00"
    assert previous["previous_values"]["receipts_count"] == 24
    assert previous["previous_ocr"]["review_receipts_count"] == 24
    assert previous["user_id"] is not None
    assert client.post(f"{url}/reprocess", headers=headers(csrf), json=payload).status_code == 409
    assert client.post(f"{url}/approve", headers=headers(csrf)).status_code == 422
    with factory() as db:
        intake = db.get(CashClosureIntake, review["id"])
        assert (root / "documents" / intake.document.stored_filename).read_bytes() == b"original-image"
        assert db.scalars(select(DailyCashClosure)).all() == []
    assert client.patch(
        url, headers=headers(csrf), json={"closure_number": "123", "total_amount": "309.00"}
    ).status_code == 200
    refreshed = client.get(url).json()
    assert refreshed["receipts_total"] == "303.50"
    assert refreshed["total_amount"] == "309.00"
    assert refreshed["status"] == "pending"
    assert client.post(f"{url}/approve", headers=headers(csrf)).status_code == 200
    assert client.post(f"{url}/reprocess/preview", headers=headers(csrf)).status_code == 409
    assert client.post(f"{url}/reprocess", headers=headers(csrf), json=payload).status_code == 409


def test_reprocess_refuses_stale_preview_and_modified_original(document_environment, monkeypatch):
    client, factory, ids, root, _app = document_environment
    monkeypatch.setattr(
        documents, "extract_text_from_document",
        lambda *_args: "NUM. CHIUSURA 201\nDATA 14-07-26",
    )
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert upload(client, csrf, b"source", "cash").status_code == 200
    intake_id = client.get("/cash-closures/review").json()[0]["id"]
    url = f"/cash-closures/review/{intake_id}"
    preview = client.post(f"{url}/reprocess/preview", headers=headers(csrf)).json()
    payload = {key: preview[key] for key in ("review_version", "extraction_version")}
    assert client.patch(url, headers=headers(csrf), json={"total_amount": "123.00"}).status_code == 200
    assert client.post(f"{url}/reprocess", headers=headers(csrf), json=payload).status_code == 409
    assert client.get(url).json()["total_amount"] == "123.00"

    with factory() as db:
        filename = db.get(CashClosureIntake, intake_id).document.stored_filename
    path = root / "documents" / filename
    path.write_bytes(b"modified")
    assert client.post(f"{url}/reprocess/preview", headers=headers(csrf)).status_code == 409
    path.unlink()
    assert client.post(f"{url}/reprocess/preview", headers=headers(csrf)).status_code == 404
    target = root / "outside.png"
    target.write_bytes(b"source")
    path.symlink_to(target)
    assert client.post(f"{url}/reprocess/preview", headers=headers(csrf)).status_code == 404
    assert client.get(url).json()["total_amount"] == "123.00"


def test_reprocess_refuses_duplicate_result_generic_image_and_rejected_review(
    document_environment, monkeypatch
):
    client, _factory, ids, _root, _app = document_environment
    ocr = {"text": "NUM. CHIUSURA 201\nDATA 14-07-26"}
    monkeypatch.setattr(documents, "extract_text_from_document", lambda *_args: ocr["text"])
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert upload(client, csrf, b"first", "cash").status_code == 200
    first = client.get("/cash-closures/review").json()[0]
    ocr["text"] = "NUM. CHIUSURA 202\nDATA 14-07-26"
    assert upload(client, csrf, b"second", "cash").status_code == 200
    second = next(item for item in client.get("/cash-closures/review").json() if item["id"] != first["id"])
    url = f"/cash-closures/review/{second['id']}"
    ocr["text"] = "NUM. CHIUSURA 201\nDATA 14-07-26"
    preview = client.post(f"{url}/reprocess/preview", headers=headers(csrf)).json()
    payload = {key: preview[key] for key in ("review_version", "extraction_version")}
    assert client.post(f"{url}/reprocess", headers=headers(csrf), json=payload).status_code == 409
    assert client.get(url).json()["closure_number"] == "202"
    ocr["text"] = "Una fotografia generica senza chiusura"
    assert client.post(f"{url}/reprocess/preview", headers=headers(csrf)).status_code == 422
    assert client.get(url).json()["closure_number"] == "202"
    assert client.post(f"{url}/reject", headers=headers(csrf)).status_code == 200
    assert client.post(f"{url}/reprocess/preview", headers=headers(csrf)).status_code == 409
    assert client.post(f"{url}/reprocess", headers=headers(csrf), json=payload).status_code == 409


def test_complete_ocr_requires_review_and_errors_do_not_create_duplicates(document_environment, monkeypatch):
    client, factory, ids, _root, _app = document_environment
    text = (
        "NUM. CHIUSURA 201\nDATA 14-07-26 23:45\n"
        "CORRISP, GIORNALIERO 945,80\nAMMONTARE GIORNO 945,80\n"
        "DOCUM. DI VENDITA 118\nPAGAM, ELETTRONICI 625,30\nAMMONTARE 320,50"
    )
    monkeypatch.setattr(documents, "extract_text_from_document", lambda *_args: text)
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    response = upload(client, csrf, b"auto", "cash")
    assert response.status_code == 200, response.text
    assert response.json()["cash_closure_classification"] == "SAVE_FOR_REVIEW"
    assert upload(client, csrf, b"auto", "cash").status_code == 409
    with factory() as db:
        intake = db.scalar(select(CashClosureIntake))
        assert intake.status == "pending"
        assert intake.closure is None
        assert intake.bar_id == intake.document.bar_id == ids["bar_one"]
        assert db.scalars(select(DailyCashClosure)).all() == []
    def fail_ocr(*_args):
        raise DocumentReadError("invalid")
    monkeypatch.setattr(documents, "extract_daily_cash_closure", fail_ocr)
    assert upload(client, csrf, b"bad", "cash").status_code == 422
    with factory() as db:
        assert len(db.scalars(select(Document)).all()) == 1


def test_file_invoice_preview_symlink_and_inconsistent_links(document_environment):
    client, factory, ids, root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    doc = upload(client, csrf).json()
    filename = doc["stored_filename"]
    stem = filename.rsplit(".", 1)[0]
    preview = f"/uploads/previews/{stem}_1.png"
    (root / "previews" / f"{stem}_1.png").write_bytes(b"preview")
    (root / "invoices" / "invoice.pdf").write_bytes(b"invoice")
    with factory() as db:
        document = db.get(Document, doc["id"])
        document.preview_url = preview
        db.add(Invoice(
            bar_id=ids["bar_one"], supplier="A", invoice_number="1",
            issue_date=dt.date(2026, 7, 1), due_date=dt.date(2026, 7, 2),
            total=Decimal("10"), vat=Decimal("0"), status=InvoiceStatus.pending,
            file_url="/uploads/invoices/invoice.pdf",
        ))
        db.commit()
    assert client.get(preview).content == b"preview"
    assert client.get("/uploads/invoices/invoice.pdf").content == b"invoice"
    assert client.get("/invoices").json()[0]["file_url"] == "/uploads/invoices/invoice.pdf"
    assert select_bar(client, ids["bar_two"], csrf).status_code == 200
    assert client.get(preview).status_code == 404
    assert client.get("/uploads/invoices/invoice.pdf").status_code == 404
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    with factory() as db:
        db.add(Transaction(
            bar_id=ids["bar_two"], document_id=doc["id"], date=dt.date(2026, 7, 1),
            description="bad link", counterparty="test", amount=Decimal("1"),
        ))
        db.commit()
    assert client.delete(f"/documents/{doc['id']}", headers=headers(csrf)).status_code == 409

    (root / "documents" / filename).unlink()
    (root / "documents" / filename).symlink_to(root / "invoices" / "invoice.pdf")
    assert client.get(doc["file_url"]).status_code == 404


def test_invoice_legacy_and_conflicting_references_fail_closed(document_environment):
    client, factory, ids, root, _app = document_environment
    (root / "invoices" / "shared.pdf").write_bytes(b"private")
    (root / "invoices" / "legacy.pdf").write_bytes(b"legacy")
    with factory() as db:
        for index, (bar_id, url) in enumerate((
            (ids["bar_one"], "/uploads/invoices/shared.pdf"),
            (ids["bar_two"], "/uploads/invoices/shared.pdf"),
            (None, "/uploads/invoices/legacy.pdf"),
            (ids["bar_one"], "/etc/passwd"),
        )):
            db.add(Invoice(
                bar_id=bar_id, supplier="A", invoice_number=str(index),
                issue_date=dt.date(2026, 7, 1), due_date=dt.date(2026, 7, 2),
                total=Decimal("10"), vat=Decimal("0"), status=InvoiceStatus.pending,
                file_url=url,
            ))
        db.commit()
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert client.get("/uploads/invoices/shared.pdf").status_code == 404
    assert client.get("/uploads/invoices/legacy.pdf").status_code == 404
    assert all(row["file_url"] != "/etc/passwd" for row in client.get("/invoices").json())


@pytest.mark.parametrize("foreign_bar", [False, True])
def test_inconsistent_intake_closure_link_is_hidden_and_not_deleted(
    document_environment, foreign_bar
):
    client, factory, ids, _root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    first = upload(client, csrf, b"first").json()
    second = upload(client, csrf, b"second").json()
    with factory() as db:
        closure = DailyCashClosure(
            bar_id=ids["bar_two"] if foreign_bar else ids["bar_one"],
            document_id=second["id"], date=dt.date(2026, 7, 1),
            closure_number="broken", total_amount=Decimal("10"),
        )
        db.add(closure)
        db.flush()
        intake = CashClosureIntake(
            bar_id=ids["bar_one"], document_id=first["id"], closure_id=closure.id,
            source_sha256="b" * 64, classification="SAVE_FOR_REVIEW",
            status="approved", ocr_values={}, anomalies=[],
        )
        db.add(intake)
        db.commit()
        intake_id = intake.id
        closure_id = closure.id
    assert client.get(f"/cash-closures/review/{intake_id}").status_code == 404
    assert client.post(
        f"/cash-closures/review/{intake_id}/approve", headers=headers(csrf)
    ).status_code == 404
    assert client.delete(f"/documents/{first['id']}", headers=headers(csrf)).status_code == 409
    with factory() as db:
        assert db.get(CashClosureIntake, intake_id) is not None
        assert db.get(DailyCashClosure, closure_id) is not None


def test_new_invoice_attachment_is_served_without_document_record(document_environment, monkeypatch):
    client, factory, ids, _root, _app = document_environment
    monkeypatch.setattr(finance, "extract_invoice_from_xml", lambda _content: {})
    monkeypatch.setattr(finance, "normalize_extracted_invoice", lambda _value: {
        "supplier": "Supplier", "invoice_number": "INV-1",
        "issue_date": dt.date(2026, 7, 1), "due_date": dt.date(2026, 7, 2),
        "total": Decimal("10"), "vat": Decimal("2"),
    })
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    response = client.post(
        "/invoices/extract", headers=headers(csrf),
        files={"file": ("invoice.xml", b"<invoice/>", "application/xml")},
    )
    assert response.status_code == 200, response.text
    url = response.json()["file_url"]
    attachment = client.get(url)
    assert attachment.status_code == 200
    assert attachment.content == b"<invoice/>"
    assert attachment.headers["content-disposition"].startswith("attachment")
    with factory() as db:
        assert db.scalars(select(Document)).all() == []
        assert db.scalar(select(Invoice)).bar_id == ids["bar_one"]
    assert select_bar(client, ids["bar_two"], csrf).status_code == 200
    assert client.get(url).status_code == 404


def test_staff_can_review_but_mutations_require_csrf_and_origin(document_environment, monkeypatch):
    client, _factory, ids, _root, _app = document_environment
    monkeypatch.setattr(
        documents, "extract_text_from_document",
        lambda *_args: "NUM. CHIUSURA 201\nDATA 14-07-26",
    )
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    csrf = login(client, "staff@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert upload(client, csrf, b"review", "cash").status_code == 200
    review = client.get("/cash-closures/review").json()[0]
    url = f"/cash-closures/review/{review['id']}"
    assert client.patch(url, json={"total_amount": "100"}).status_code == 403
    assert client.patch(
        url, headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
        json={"total_amount": "100"},
    ).status_code == 403
    assert client.post(f"{url}/approve").status_code == 403
    assert client.patch(url, headers=headers(csrf), json={"total_amount": "100"}).status_code == 200
    assert client.post(f"{url}/approve", headers=headers(csrf)).status_code == 403


def test_month_filter_uses_closure_date_and_correction_updates_document_and_dashboard(
    document_environment,
):
    client, factory, ids, _root, _app = document_environment
    with factory() as db:
        intakes = []
        for index, (bar, date) in enumerate((
            (ids["bar_one"], dt.date(2023, 9, 26)),
            (ids["bar_one"], dt.date(2026, 11, 3)),
            (ids["bar_one"], None),
            (ids["bar_one"], dt.date(2025, 11, 3)),
            (ids["bar_two"], dt.date(2026, 11, 4)),
        )):
            doc = Document(
                bar_id=bar, month="2026-11", original_filename=f"{index}.png",
                stored_filename=f"{index}.png", section="cash", document_type="PNG",
                category="Immagine", result="OCR", status="Da verificare",
                file_url=f"/uploads/documents/{index}.png", preview_url="",
            )
            db.add(doc)
            db.flush()
            intake = CashClosureIntake(
                bar_id=bar, document_id=doc.id, source_sha256=f"{index:064x}",
                status="pending", classification="SAVE_FOR_REVIEW", date=date,
                closure_number=str(index + 1), total_amount=Decimal("100.00"),
                ocr_values={}, anomalies=[],
            )
            db.add(intake)
            db.flush()
            intakes.append((intake.id, doc.id))
        db.commit()
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    ids_for = lambda month: {
        row["id"] for row in client.get("/cash-closures/review", params={"month": month}).json()
    }
    assert ids_for("2026-11") == {intakes[1][0]}
    assert ids_for("2025-11") == {intakes[3][0]}
    assert ids_for("2023-09") == {intakes[0][0]}
    september_history = client.get("/documents?month=2023-09").json()
    old_history = next(row for row in september_history if row["id"] == intakes[0][1])
    assert old_history["effective_date"] == "2023-09-26"
    assert intakes[0][1] not in {row["id"] for row in client.get("/documents?month=2026-11").json()}
    assert client.get("/cash-closures/review?month=2026-13").status_code == 422
    all_ids = {row["id"] for row in client.get("/cash-closures/review").json()}
    assert all_ids == {intakes[i][0] for i in range(4)}
    undated_url = f"/cash-closures/review/{intakes[2][0]}"
    dated = client.patch(undated_url, headers=headers(csrf), json={"date": "2023-09-10"})
    assert dated.json()["document"]["month"] == "2023-09"
    assert ids_for("2023-09") == {intakes[0][0], intakes[2][0]}
    cleared = client.patch(undated_url, headers=headers(csrf), json={"date": None})
    assert cleared.json()["date"] is None
    assert cleared.json()["document"]["month"] == "2023-09"
    assert ids_for("2023-09") == {intakes[0][0]}
    assert intakes[2][0] in {row["id"] for row in client.get("/cash-closures/review").json()}
    assert client.get("/analytics/pnl?month=2024-01").json()["revenue"] == 0

    url = f"/cash-closures/review/{intakes[0][0]}"
    corrected = client.patch(url, headers=headers(csrf), json={"date": "2024-01-03"})
    assert corrected.status_code == 200
    assert corrected.json()["document"]["month"] == "2024-01"
    assert ids_for("2023-09") == set()
    assert ids_for("2024-01") == {intakes[0][0]}
    assert intakes[0][1] in {row["id"] for row in client.get("/documents?month=2024-01").json()}
    assert intakes[0][1] not in {row["id"] for row in client.get("/documents?month=2026-11").json()}
    assert client.get("/analytics/pnl?month=2024-01").json()["revenue"] == 0
    assert client.post(f"{url}/approve", headers=headers(csrf)).status_code == 200
    assert ids_for("2024-01") == set()
    assert client.get("/analytics/pnl?month=2024-01").json()["revenue"] == 100
    assert client.get("/analytics/pnl?month=2026-11").json()["revenue"] == 0
    assert client.patch(url, headers=headers(csrf), json={"date": "2026-11-01"}).status_code == 409
    with factory() as db:
        assert db.get(Document, intakes[0][1]).month == "2024-01"
    assert select_bar(client, ids["bar_two"], csrf).status_code == 200
    assert ids_for("2026-11") == {intakes[4][0]}
    assert client.get(url).status_code == 404


def test_approved_legacy_history_uses_closure_date_without_changing_document(document_environment):
    client, factory, ids, _root, _app = document_environment
    with factory() as db:
        doc = Document(
            bar_id=ids["bar_one"], month="2026-11", original_filename="legacy.png",
            stored_filename="legacy.png", section="cash", document_type="PNG",
            category="Immagine", result="OCR", status="Elaborato",
            file_url="/uploads/documents/legacy.png", preview_url="",
        )
        db.add(doc)
        db.flush()
        db.add(DailyCashClosure(
            bar_id=ids["bar_one"], document_id=doc.id, date=dt.date(2023, 9, 26),
            closure_number="legacy", total_amount=Decimal("100.00"),
        ))
        db.commit()
        doc_id = doc.id
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert doc_id in {row["id"] for row in client.get("/documents?month=2023-09").json()}
    assert doc_id not in {row["id"] for row in client.get("/documents?month=2026-11").json()}
    with factory() as db:
        assert db.get(Document, doc_id).month == "2026-11"


@pytest.mark.parametrize("role,global_admin,allowed", [
    ("staff", False, False),
    ("manager", False, False),
    ("staff", True, True),
])
def test_approval_is_restricted_to_owner_or_global_admin_in_active_bar(
    document_environment, monkeypatch, role, global_admin, allowed
):
    client, factory, ids, _root, _app = document_environment
    with factory() as db:
        db.get(User, ids[role]).is_global_admin = global_admin
        db.commit()
    monkeypatch.setattr(
        documents, "extract_text_from_document",
        lambda *_args: "NUM. CHIUSURA 201\nDATA 14-07-26",
    )
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    csrf = login(client, f"{role}@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert upload(client, csrf, b"review", "cash").status_code == 200
    review = client.get("/cash-closures/review").json()[0]
    assert review["can_approve"] is allowed
    url = f"/cash-closures/review/{review['id']}"
    assert client.patch(url, headers=headers(csrf), json={"total_amount": "100"}).status_code == 200
    assert client.post(f"{url}/approve", headers=headers(csrf)).status_code == (200 if allowed else 403)
    if global_admin:
        assert select_bar(client, ids["bar_two"], csrf).status_code == 403


@pytest.mark.parametrize("change", ["switch", "revoke"])
def test_context_change_during_ocr_rejects_upload(document_environment, monkeypatch, change):
    client, factory, ids, _root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    def switch_during_ocr(*_args):
        with factory() as db:
            if change == "switch":
                session = db.scalar(select(AuthSession).where(AuthSession.user_id == ids["owner"]))
                session.active_bar_id = ids["bar_two"]
            else:
                membership = db.scalar(select(UserBarMembership).where(
                    UserBarMembership.user_id == ids["owner"],
                    UserBarMembership.bar_id == ids["bar_one"],
                ))
                db.delete(membership)
            db.commit()
        return "NUM. CHIUSURA 201\nDATA 14-07-26"

    monkeypatch.setattr(documents, "extract_text_from_document", switch_during_ocr)
    monkeypatch.setattr(documents, "extract_alternate_texts", lambda *_args: iter(()))
    response = upload(client, csrf, b"race", "cash")
    assert response.status_code == (409 if change == "switch" else 403)
    with factory() as db:
        assert db.scalars(select(Document)).all() == []
        assert db.scalars(select(CashClosureIntake)).all() == []


def test_context_change_during_preview_rolls_back_file_and_document(document_environment, monkeypatch):
    client, factory, ids, root, _app = document_environment
    csrf = login(client, "owner@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200

    def switch_during_preview(**_kwargs):
        with factory() as db:
            session = db.scalar(select(AuthSession).where(AuthSession.user_id == ids["owner"]))
            session.active_bar_id = ids["bar_two"]
            db.commit()
        return None

    monkeypatch.setattr(documents, "create_text_preview_image", switch_during_preview)
    response = client.post(
        "/documents/upload", headers=headers(csrf),
        files={"file": ("notes.txt", b"private", "text/plain")},
        data={"month": "2026-07"},
    )
    assert response.status_code == 409
    assert list((root / "documents").iterdir()) == []
    with factory() as db:
        assert db.scalars(select(Document)).all() == []


def test_roles_csrf_revocation_and_inactive_bar(document_environment):
    client, factory, ids, _root, app = document_environment
    csrf = login(client, "staff@example.test")
    assert select_bar(client, ids["bar_one"], csrf).status_code == 200
    assert client.post("/documents/upload", files={"file": ("a.png", b"a")},
                       data={"month": "2026-07"}).status_code == 403
    assert client.post("/documents/upload", headers={"X-CSRF-Token": csrf},
                       files={"file": ("a.png", b"a")}, data={"month": "2026-07"}).status_code == 403
    doc = upload(client, csrf).json()
    assert client.get(doc["file_url"]).status_code == 200
    assert client.delete(f"/documents/{doc['id']}", headers=headers(csrf)).status_code == 403
    assert client.post("/payments", headers=headers(csrf), json={}).status_code == 403
    with TestClient(app) as manager:
        manager_csrf = login(manager, "manager@example.test")
        assert select_bar(manager, ids["bar_one"], manager_csrf).status_code == 200
        assert manager.get(doc["file_url"]).status_code == 200
        assert manager.delete(f"/documents/{doc['id']}", headers=headers(manager_csrf)).status_code == 200
        assert manager.get(doc["file_url"]).status_code == 404
        assert (_root / "documents" / doc["stored_filename"]).is_file()

    doc = upload(client, csrf, b"another").json()
    with factory() as db:
        membership = db.scalar(select(UserBarMembership).where(
            UserBarMembership.user_id == ids["staff"],
            UserBarMembership.bar_id == ids["bar_one"],
        ))
        db.delete(membership)
        db.commit()
    assert client.get("/documents").status_code == 403
    assert client.get(doc["file_url"]).status_code == 403
    with TestClient(app) as owner:
        owner_csrf = login(owner, "owner@example.test")
        assert select_bar(owner, ids["bar_one"], owner_csrf).status_code == 200
        with factory() as db:
            db.get(Bar, ids["bar_one"]).is_active = False
            db.commit()
        assert owner.get(doc["file_url"]).status_code == 403
        assert upload(owner, owner_csrf).status_code == 403
