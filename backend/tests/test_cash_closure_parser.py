"""Test del parser delle chiusure di cassa su TESTO SIMULATO (nessun OCR eseguito)."""

import datetime as dt
from decimal import Decimal

import pytest

from app.routers import documents as documents_router
from app.services.cash_closure_parser import ClosureExtraction

LAYOUT_A = """CHIUSURA GIORNALIERA
DEL GIORNO 14/07/2026
NUM. CHIUSURA 201
TOTALE GIORNALIERO 945,80
CONTANTI 320,50
POS 625,30
IVA 10% 85,89
RESTO 5,00
DOCUMENTI COMMERCIALI 118
"""

LAYOUT_B = """RAPPORTO Z N. 55
Data: 2026-07-15
CORRISPETTIVI 1.124,20
CASH 404,20
PAGAMENTI ELETTRONICI 720,00
SCONTRINI EMESSI 139
"""


def extract(text):
    return ClosureExtraction(text).to_result()


def test_layout_a_and_alternate_labels():
    r = extract(LAYOUT_A)
    assert r["date"] == dt.date(2026, 7, 14)
    assert r["closure_number"] == "201"
    assert r["total_amount"] == Decimal("945.80")
    assert r["cash_amount"] == Decimal("320.50")
    assert r["card_amount"] == Decimal("625.30")
    assert r["receipts_count"] == 118
    assert r["diagnostics"]["second_read"] == "not_needed"


def test_layout_b_iso_date_and_rapporto_z():
    r = extract(LAYOUT_B)
    assert r["date"] == dt.date(2026, 7, 15)
    assert r["closure_number"] == "55"
    assert r["total_amount"] == Decimal("1124.20")
    assert r["cash_amount"] == Decimal("404.20")
    assert r["card_amount"] == Decimal("720.00")


def test_generic_total_ignores_vat_change_and_subtotals():
    text = "TOTALE 100,00\nIVA 22% 18,03\nRESTO 5,00\nSUBTOTALE 99,00\nCONTANTI 40,00\nCARTE 60,00\n"
    assert extract(text)["total_amount"] == Decimal("100.00")


def test_conflicting_totals_are_not_resolved_to_first():
    text = (
        "DATA 14/07/2026\nNUM. CHIUSURA 7\nTOTALE GIORNALIERO 100,00\nTOTALE INCASSI 120,00\n"
    )
    r = extract(text)
    assert r["total_amount"] is None
    assert "total_amount" in r["diagnostics"]["unresolved_fields"]


def test_date_ambiguity_and_malformed():
    assert extract("STAMPA 01/01/26 14/07/26\nNUM. CHIUSURA 1")["date"] is None
    assert extract("DATA 14/13/2026")["date"] is None
    assert extract("DEL GIORNO 14/07/2026\nSTAMPA 01/01/2026")["date"] == dt.date(2026, 7, 14)


def test_closure_number_not_taken_from_date_and_malformed_rejected():
    r = extract("RAPPORTO Z 14/07/2026\nTOTALE GIORNALIERO 10,00")
    assert r["closure_number"] is None
    for bad in ("2O1", "20l", "201A"):
        assert extract(f"NUM. CHIUSURA {bad}")["closure_number"] is None


@pytest.mark.parametrize("bad", ["945,805", "945,8", "1.25,50", "1250.50", "-10,00", "n/d"])
def test_malformed_amounts_never_become_values(bad):
    r = extract(f"AMMONTARE GIORNO {bad}")
    assert r["total_amount"] is None


def test_missing_cash_is_none_not_zero():
    r = extract("DATA 14/07/2026\nNUM. CHIUSURA 3\nTOTALE GIORNALIERO 50,00\n")
    assert r["cash_amount"] is None and r["card_amount"] is None


def test_explicit_zero_is_kept():
    r = extract("AMMONTARE GIORNO 10,00\nCONTANTI 0,00\nPOS 10,00")
    assert r["cash_amount"] == Decimal("0.00")


def test_other_payments_are_recorded_not_accounted():
    text = LAYOUT_A.replace("POS 625,30", "POS 600,30\nBUONI PASTO 25,00")
    r = extract(text)
    assert r["card_amount"] == Decimal("600.30")
    assert r["diagnostics"]["other_payments_total"] == Decimal("25.00")
    assert documents_router.build_cash_closure_warnings(r) == []


def test_mismatch_without_explanation_warns():
    text = LAYOUT_A.replace("POS 625,30", "POS 600,30")
    r = extract(text)
    warnings = documents_router.build_cash_closure_warnings(r)
    assert any("non coincide" in w for w in warnings)


def test_second_read_confirms_and_conflicts():
    first = LAYOUT_A.replace("320,50", "320,5")  # malformato
    e = ClosureExtraction(first)
    assert e.needs_second_read()
    e.merge_text(LAYOUT_A, "alt")
    assert e.to_result()["cash_amount"] == Decimal("320.50")

    e2 = ClosureExtraction("DATA 14/07/2026\nNUM. CHIUSURA 3\nTOTALE GIORNALIERO 100,00\nCONTANTI 40,00\nPOS 50,00")
    assert e2.needs_second_read()
    e2.merge_text("DATA 14/07/2026\nNUM. CHIUSURA 3\nTOTALE GIORNALIERO 100,00\nCONTANTI 40,00\nPOS 80,00", "alt")
    r2 = e2.to_result()
    assert r2["card_amount"] != Decimal("80.00")
    assert r2["total_amount"] == Decimal("100.00")


def test_second_read_conflict_on_closure_number_is_unresolved():
    base = "DATA 14/07/2026\nTOTALE GIORNALIERO 10,00\nCONTANTI 10,00\nPOS 0,00\n"
    e = ClosureExtraction(base + "NUM. CHIUSURA 12")
    e.merge_text(base + "NUM. CHIUSURA 17", "alt")
    r = e.to_result()
    assert r["closure_number"] is None
    assert "closure_number" in r["diagnostics"]["unresolved_fields"]


def test_clean_document_does_not_need_second_read():
    assert not ClosureExtraction(LAYOUT_A).needs_second_read()


def test_unavailable_second_read_is_flagged():
    e = ClosureExtraction("DATA 14/07/2026\nNUM. CHIUSURA 3\n")
    assert e.needs_second_read()
    e.mark_second_read_unavailable()
    assert e.to_result()["diagnostics"]["second_read"] != "not_needed"


def test_extract_daily_cash_closure_runs_alternates_only_when_needed(monkeypatch):
    calls = []

    def alternates(content, ext):
        calls.append(1)
        yield "alt", LAYOUT_A

    monkeypatch.setattr(documents_router, "extract_alternate_texts", alternates)
    monkeypatch.setattr(documents_router, "extract_text_from_document", lambda c, e: LAYOUT_A)
    assert documents_router.extract_daily_cash_closure(b"x", "png")["total_amount"] == Decimal("945.80")
    assert calls == []

    monkeypatch.setattr(
        documents_router, "extract_text_from_document", lambda c, e: LAYOUT_A.replace("320,50", "32O,50")
    )
    r = documents_router.extract_daily_cash_closure(b"x", "png")
    assert calls == [1]
    assert r["cash_amount"] == Decimal("320.50")
