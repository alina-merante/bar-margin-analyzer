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


def test_invoice_without_vat_information_does_not_invent_vat():
    result = extract_invoice_from_text("TOTALE FATTURA 420,00 EUR")

    assert result["total"] == "420.00"
    assert result["vat"] == "0"
