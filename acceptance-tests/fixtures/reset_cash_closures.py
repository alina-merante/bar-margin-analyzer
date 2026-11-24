from sqlalchemy import text, inspect, Table, MetaData
from test_database import get_test_engine

engine = get_test_engine()

reason = "AT-CASH - Annullamento di prova"

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

    row = conn.execute(text("""
        SELECT
            c.id AS closure_id,
            i.id AS intake_id,
            d.id AS document_id,
            c.annulled_at,
            c.annulment_reason,
            c.annulled_by_user_id,
            i.status
        FROM daily_cash_closures c
        JOIN cash_closure_intakes i
            ON i.closure_id = c.id
            AND i.bar_id = c.bar_id
            AND i.document_id = c.document_id
        JOIN documents d
            ON d.id = c.document_id
            AND d.bar_id = c.bar_id
        WHERE c.bar_id = :bar_id
            AND c.closure_number = 'AT-CASH-A'
            AND d.original_filename = 'AT-CASH-A.png'
            AND c.total_amount = 1375
            AND c.cash_amount = 550
            AND c.card_amount = 825
            AND c.date = '2026-11-23'
        FOR UPDATE OF c, i
    """), {"bar_id": bar_id}).mappings().one()

    assert row["closure_id"] == 1
    assert row["intake_id"] == 2
    assert row["document_id"] == 2

    if row["status"] == "approved":
        assert row["annulled_at"] is None
        assert row["annulment_reason"] is None
        assert row["annulled_by_user_id"] is None

        print("Fixture gia approvata: nessuna modifica.")

    else:
        assert row["status"] == "annulled"
        assert row["annulled_at"] is not None
        assert row["annulment_reason"] == reason

        inspector = inspect(conn)

        candidates = []

        for name in inspector.get_table_names():
            if "audit" not in name:
                continue

            columns = {
                c["name"]
                for c in inspector.get_columns(name)
            }

            if {"action", "bar_id", "changes", "actor_id"} <= columns:
                candidates.append(name)

        assert len(candidates) == 1, "Tabella audit non univoca"

        audit = Table(
            candidates[0],
            MetaData(),
            autoload_with=conn
        )

        events = conn.execute(
            audit.select().where(
                audit.c.bar_id == bar_id,
                audit.c.action == "cash_closure.annul"
            ).with_for_update()
        ).mappings().all()

        matching = [
            event for event in events
            if isinstance(event["changes"], dict)
            and event["changes"].get("closure_id") == 1
            and event["changes"].get("intake_id") == 2
            and event["changes"].get("document_id") == 2
            and event["changes"].get("reason") == reason
            and event["actor_id"] == row["annulled_by_user_id"]
        ]

        assert len(matching) == 1, "Evento audit non univoco"

        event = matching[0]

        pk = list(audit.primary_key.columns)
        assert len(pk) == 1

        deleted = conn.execute(
            audit.delete().where(
                pk[0] == event[pk[0].name],
                audit.c.bar_id == bar_id
            )
        )

        assert deleted.rowcount == 1

        result = conn.execute(text("""
            UPDATE daily_cash_closures
            SET annulled_at = NULL,
                annulled_by_user_id = NULL,
                annulment_reason = NULL
            WHERE id = 1
                AND bar_id = :bar_id
                AND closure_number = 'AT-CASH-A'
        """), {"bar_id": bar_id})

        assert result.rowcount == 1

        result = conn.execute(text("""
            UPDATE cash_closure_intakes
            SET status = 'approved',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 2
                AND closure_id = 1
                AND document_id = 2
                AND bar_id = :bar_id
                AND status = 'annulled'
        """), {"bar_id": bar_id})

        assert result.rowcount == 1

        print("AT-CASH-A: annullata -> approvata")
        print("Evento audit sintetico rimosso: 1")

    total = conn.execute(text("""
        SELECT COALESCE(SUM(total_amount), 0)
        FROM daily_cash_closures
        WHERE bar_id = :bar_id
            AND date >= '2026-11-01'
            AND date < '2026-12-01'
            AND annulled_at IS NULL
    """), {"bar_id": bar_id}).scalar_one()

    assert total == 2255, "Totale contabile inatteso"

    print("Ricavi novembre:", total)

print("RIPRISTINO COMPLETATO")
