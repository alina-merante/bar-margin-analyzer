from decimal import Decimal

import pytest

from app.routers.finance import (
    extract_invoice_from_text,
    merge_extracted_invoice,
    normalize_extracted_invoice,
    pick_best_vat,
)


def test_pick_best_vat_uses_amount_after_tax_rate():
    assert pick_best_vat("IVA 16,67% 60,00 EUR", Decimal("420.00")) == "60.00"


@pytest.mark.parametrize("ai_extracted", [None, {}, {"vat": ""}])
def test_merge_uses_heuristic_vat_when_ai_vat_is_missing(ai_extracted):
    heuristic = {
        "supplier": "Supplier A",
        "invoice_number": "INV-1",
        "total": "420.00",
        "vat": "60.00",
    }

    result = merge_extracted_invoice(ai_extracted, heuristic)

    assert result["vat"] == "60.00"


def test_merge_preserves_explicit_zero_ai_vat():
    heuristic = {
        "supplier": "Supplier A",
        "invoice_number": "INV-1",
        "total": "420.00",
        "vat": "60.00",
    }

    result = merge_extracted_invoice({"vat": "0"}, heuristic)

    assert result["vat"] == "0"


def test_merge_prefers_valid_ai_issue_date():
    result = merge_extracted_invoice(
        {"issue_date": "2026-08-12"},
        {"issue_date": "2026-08-10"},
    )

    assert result["issue_date"] == "2026-08-12"


def test_merge_falls_back_to_valid_heuristic_issue_date_when_ai_date_is_invalid():
    result = merge_extracted_invoice(
        {"issue_date": "2026-02-30"},
        {"issue_date": "12/08/2026"},
    )

    assert result["issue_date"] == "2026-08-12"


def test_merge_uses_heuristic_issue_date_when_ai_result_is_absent():
    result = merge_extracted_invoice(
        None,
        {"issue_date": "2026-08-12"},
    )

    assert result["issue_date"] == "2026-08-12"


def test_merge_leaves_issue_date_missing_when_both_sources_are_invalid():
    result = merge_extracted_invoice(
        {"issue_date": "not a date"},
        {"issue_date": "2026-02-30"},
    )

    assert result["issue_date"] is None


def test_normalization_keeps_gross_total_and_vat_inside_total():
    result = normalize_extracted_invoice(
        {
            "supplier": "Supplier A",
            "invoice_number": "INV-1",
            "issue_date": "2026-07-02",
            "due_date": "2026-07-10",
            "total": "420.00",
            "vat": "60.00",
        }
    )

    assert result["total"] == Decimal("420.00")
    assert result["vat"] == Decimal("60.00")


def test_normalization_does_not_invent_issue_date_or_due_date():
    result = normalize_extracted_invoice(
        {
            "supplier": "Supplier A",
            "invoice_number": "INV-1",
            "issue_date": "invalid",
            "due_date": "",
            "total": "420.00",
            "vat": "60.00",
        }
    )

    assert result["issue_date"] is None
    assert result["due_date"] is None


def test_invoice_without_vat_information_does_not_invent_vat():
    result = extract_invoice_from_text("TOTALE FATTURA 420,00 EUR")

    assert result["total"] == "420.00"
    assert result["vat"] == "0"


def test_ocr_extracts_explicit_due_date():
    result = extract_invoice_from_text("Data scadenza: 31/07/2026")

    assert result["due_date"] == "31/07/2026"


def test_explicit_due_date_wins_over_different_delivery_date():
    result = extract_invoice_from_text(
        "Scadenza: 31/07/2026\nData consegna: 02/08/2026"
    )

    assert result["due_date"] == "31/07/2026"
    assert result["delivery_date"] == "02/08/2026"


def test_ocr_explicit_payment_deadline_is_a_due_date():
    result = extract_invoice_from_text("Pagamento entro: 31/07/2026")

    assert result["due_date"] == "31/07/2026"


def test_delivery_date_alone_is_not_a_due_date():
    result = extract_invoice_from_text("Data consegna: 31/07/2026")

    assert result["delivery_date"] == "31/07/2026"
    assert result["due_date"] is None


def test_generic_date_at_document_tail_is_not_a_due_date():
    result = extract_invoice_from_text(
        "Fornitore Alfa\nNumero fattura F-123\nTotale 420,00 EUR\n"
        "Pagamento con bonifico\n31/07/2026"
    )

    assert result["due_date"] is None


@pytest.mark.parametrize("label", ["Data ordine", "Data emissione", "Data stampa"])
def test_order_issue_and_print_dates_are_not_due_dates(label):
    result = extract_invoice_from_text(f"{label}: 31/07/2026")

    assert result["due_date"] is None


def test_vergnano_generic_date_is_not_promoted_to_due_date():
    result = extract_invoice_from_text(
        "Casa del Caffè Vergnano S.p.A.\nFattura n. 000123\nData: 31/07/2026"
    )

    assert result["issue_date"] == "31/07/2026"
    assert result["due_date"] is None
