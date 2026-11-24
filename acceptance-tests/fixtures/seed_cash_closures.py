from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


from test_database import get_test_engine


fixtures = [
    ("AT-CASH-A", date(2026, 11, 23), "1375", "550", "825", 186),
    ("AT-CASH-B", date(2026, 11, 24), "880", "330", "550", 120),
    ("AT-CASH-C", date(2026, 10, 23), "660", "260", "400", 90),
]

engine = get_test_engine()

with engine.begin() as conn:

    assert conn.execute(
        text("SELECT current_database()")
    ).scalar_one() == "bar_margin_analyzer_pwa_test"

    bar_id = conn.execute(text("""
        SELECT id FROM bars
        WHERE name = 'Bar Demo PWA'
        AND is_active = true
    """)).scalar_one()

    assert bar_id == 4

    count = conn.execute(text("""
        SELECT count(*) FROM daily_cash_closures
        WHERE bar_id = :bar_id
    """), {"bar_id": bar_id}).scalar_one()

    assert count == 0, "Chiusure gia presenti: inserimento interrotto"

    existing = conn.execute(text("""
        SELECT count(*) FROM documents
        WHERE bar_id = :bar_id
        AND original_filename LIKE 'AT-CASH-%'
    """), {"bar_id": bar_id}).scalar_one()

    assert existing == 0, "Fixture gia presenti"

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for number, day, total, cash, card, receipts in fixtures:

        total = Decimal(total)
        cash = Decimal(cash)
        card = Decimal(card)

        assert total == cash + card

        filename = f"{number}.png"

        params = {
            "bar_id": bar_id,
            "month": day.strftime("%Y-%m"),
            "filename": filename,
            "number": number,
            "date": day,
            "total": total,
            "cash": cash,
            "card": card,
            "receipts": receipts,
            "now": now,
            "sha": hashlib.sha256(number.encode()).hexdigest(),
            "url": f"/uploads/documents/{filename}",
        }

        document_id = conn.execute(text("""
            INSERT INTO documents (
                bar_id, month, original_filename,
                stored_filename, section, document_type,
                category, result, file_url, preview_url,
                status, created_at
            ) VALUES (
                :bar_id, :month, :filename,
                :filename, 'Chiusure di cassa', 'PNG',
                'Immagine', 'Acceptance test',
                :url, :url, 'processed', :now
            )
            RETURNING id
        """), params).scalar_one()

        params["document_id"] = document_id

        closure_id = conn.execute(text("""
            INSERT INTO daily_cash_closures (
                bar_id, document_id, date,
                closure_number, total_amount,
                cash_amount, card_amount,
                receipts_count, created_at
            ) VALUES (
                :bar_id, :document_id, :date,
                :number, :total,
                :cash, :card,
                :receipts, :now
            )
            RETURNING id
        """), params).scalar_one()

        params["closure_id"] = closure_id

        intake_id = conn.execute(text("""
            INSERT INTO cash_closure_intakes (
                bar_id, document_id, closure_id,
                source_sha256, classification, status,
                date, closure_number, total_amount,
                cash_amount, card_amount,
                ocr_values, anomalies,
                created_at, updated_at
            ) VALUES (
                :bar_id, :document_id, :closure_id,
                :sha, 'SAVE_FOR_REVIEW', 'approved',
                :date, :number, :total,
                :cash, :card,
                CAST('{}' AS JSON), CAST('[]' AS JSON),
                :now, :now
            )
            RETURNING id
        """), params).scalar_one()

        print(
            number,
            "document:", document_id,
            "closure:", closure_id,
            "intake:", intake_id,
            "total:", total
        )

print("INSERIMENTO COMPLETATO")
