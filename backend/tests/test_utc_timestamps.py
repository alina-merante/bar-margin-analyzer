import datetime as dt
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import DailyCashClosure, Document
from app.routers import documents as documents_router
from app.routers.analytics import overview
from app.time_utils import to_utc_iso


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'utc_timestamps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_document(**overrides):
    values = dict(
        month="2026-09",
        original_filename="cash.pdf",
        stored_filename="cash.pdf",
        section="cash",
        document_type="PDF",
        category="Documento PDF",
        result="ok",
        file_url="/uploads/documents/cash.pdf",
        preview_url="/uploads/documents/cash.pdf",
    )
    values.update(overrides)
    return Document(**values)


def test_naive_datetime_is_labeled_utc_without_shifting():
    assert to_utc_iso(dt.datetime(2026, 9, 30, 23, 30)) == "2026-09-30T23:30:00+00:00"


def test_aware_non_utc_datetime_is_normalized_to_utc():
    rome = dt.timezone(dt.timedelta(hours=2))

    assert (
        to_utc_iso(dt.datetime(2026, 10, 1, 1, 30, tzinfo=rome))
        == "2026-09-30T23:30:00+00:00"
    )


def test_aware_utc_datetime_is_unchanged():
    assert (
        to_utc_iso(dt.datetime(2026, 9, 30, 23, 30, tzinfo=dt.timezone.utc))
        == "2026-09-30T23:30:00+00:00"
    )


def test_none_stays_none():
    assert to_utc_iso(None) is None


def test_microseconds_are_preserved():
    assert (
        to_utc_iso(dt.datetime(2026, 9, 30, 14, 41, 40, 512236))
        == "2026-09-30T14:41:40.512236+00:00"
    )


def test_serialized_value_parses_to_the_same_instant():
    parsed = dt.datetime.fromisoformat(to_utc_iso(dt.datetime(2026, 9, 30, 23, 30)))

    assert parsed == dt.datetime(2026, 9, 30, 23, 30, tzinfo=dt.timezone.utc)


def test_document_dict_serializes_created_at_as_explicit_utc(db):
    db.add(make_document(created_at=dt.datetime(2026, 9, 30, 23, 30, 5, 123456)))
    db.commit()

    result = documents_router.list_documents(month="2026-09", db=db)

    assert result[0]["created_at"] == "2026-09-30T23:30:05.123456+00:00"


def test_legacy_naive_row_in_database_is_read_as_utc_and_not_rewritten(db):
    db.execute(
        text(
            "INSERT INTO documents (month, original_filename, stored_filename, section, "
            "document_type, category, result, file_url, preview_url, status, created_at) "
            "VALUES ('2026-09', 'old.pdf', 'old.pdf', 'other', 'PDF', 'Documento PDF', "
            "'ok', '/u/old.pdf', '/u/old.pdf', 'Elaborato', '2026-09-30 14:41:40.512236')"
        )
    )
    db.commit()

    result = documents_router.list_documents(month="2026-09", db=db)
    stored = db.execute(text("SELECT created_at FROM documents")).scalar_one()

    assert result[0]["created_at"] == "2026-09-30T14:41:40.512236+00:00"
    assert stored == "2026-09-30 14:41:40.512236"


def test_overview_latest_cash_closure_uploaded_at_is_explicit_utc(db):
    db.add(
        DailyCashClosure(
            date=dt.date(2026, 9, 30),
            total_amount=Decimal("100.00"),
            created_at=dt.datetime(2026, 9, 30, 23, 30),
        )
    )
    db.commit()

    result = overview(month="2026-09", db=db)

    assert result["latest_cash_closure_date"] == "2026-09-30"
    assert result["latest_cash_closure_uploaded_at"] == "2026-09-30T23:30:00+00:00"


def test_overview_without_cash_closures_returns_none_for_uploaded_at(db):
    result = overview(month="2026-09", db=db)

    assert result["latest_cash_closure_uploaded_at"] is None
