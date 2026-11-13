"""Deterministic cash-closure classification scenarios."""

HEAD = "DATA 03/11/2026\nNUM. CHIUSURA 5\n"


def _classify(text):
    from app.services.cash_closure_policy import classify_closure

    return classify_closure(text)


def test_complete_and_coherent_requires_review():
    assert _classify(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPOS 200,00") == "SAVE_FOR_REVIEW"


def test_reliable_total_without_breakdown_requires_review():
    assert _classify(HEAD + "TOTALE GIORNALIERO 200,00") == "SAVE_FOR_REVIEW"


def test_save_for_review_when_breakdown_present_but_unreadable():
    assert _classify(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 1O0,00\nPOS 100,00") == "SAVE_FOR_REVIEW"


def test_save_for_review_when_payments_exceed_total():
    assert _classify(HEAD + "TOTALE GIORNALIERO 150,00\nCONTANTI 100,00\nPOS 100,00") == "SAVE_FOR_REVIEW"


def test_save_for_review_when_total_chosen_only_by_arithmetic():
    text = HEAD + "TOTALE GIORNALIERO 200,00\nTOTALE INCASSI 230,00\nCONTANTI 100,00\nPOS 100,00"
    assert _classify(text) == "SAVE_FOR_REVIEW"


def test_reject_when_required_fields_missing_or_unresolved():
    assert _classify("TOTALE GIORNALIERO 200,00") == "REJECT"


def test_save_for_review_when_core_values_are_missing_but_closure_evidence_exists():
    assert _classify("NUM. CHIUSURA 5\nTOTALE GIORNALIERO 200,00") == "SAVE_FOR_REVIEW"


def test_save_for_review_when_total_uses_generic_label():
    assert _classify(HEAD + "TOTALE 200,00") == "SAVE_FOR_REVIEW"


def test_explicit_zeros_are_reliable_values():
    assert (
        _classify(
            HEAD
            + "TOTALE GIORNALIERO 0,00\nCONTANTI 0,00\nPOS 0,00"
        )
        == "SAVE_FOR_REVIEW"
    )


def test_missing_diagnostics_never_certify_an_automatic_save():
    import datetime as dt
    from decimal import Decimal

    from app.services.cash_closure_policy import classify_closure

    assert classify_closure(
        {
            "date": dt.date(2026, 11, 3),
            "closure_number": "5",
            "total_amount": Decimal("200.00"),
        }
    ) == "SAVE_FOR_REVIEW"


def test_management_report_requires_specific_coherent_evidence():
    text = (
        "DATA 26/09/2023\nNUMERO SCONTRINI 25\n"
        "TOTALE SCONTRINI 303,50\nCONTANTI 255,50\nNUMERO AZZERAMENTI 10"
    )
    assert _classify(text) == "SAVE_FOR_REVIEW"
    for unrelated in (
        "FOTO VACANZE\nDATA 26/09/2023\nCONTANTI 255,50",
        "FATTURA\nDATA 26/09/2023\nTOTALE 303,50",
        "DATA 26/09/2023\nSCONTRINI 25",
    ):
        assert _classify(unrelated) == "REJECT"
