"""Scenari della FUTURA politica AUTO_SAVE / SAVE_FOR_REVIEW / REJECT (Fase 3).

Nessuna di queste regole è implementata: non esiste `classify_closure`, né lo stato
"Da verificare", né colonne nullable. I test sono saltati e descrivono SOLO il
comportamento desiderato, in attesa di decisione. Non fanno parte del comportamento
attuale, documentato in test_cash_closure_parser.py.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Fase 3 non implementata: politica in attesa di decisione")

HEAD = "DATA 03/11/2026\nNUM. CHIUSURA 5\n"


def _classify(text):
    from app.services.cash_closure_policy import classify_closure  # noqa: non esiste ancora

    return classify_closure(text)


def test_auto_save_complete_and_coherent():
    assert _classify(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPOS 200,00") == "AUTO_SAVE"


def test_auto_save_reliable_total_without_breakdown_keeps_missing_not_zero():
    # Atteso: contabilizzato col solo totale; cash/card salvati come NULL, non 0.00.
    assert _classify(HEAD + "TOTALE GIORNALIERO 200,00") == "AUTO_SAVE"


def test_save_for_review_when_breakdown_present_but_unreadable():
    assert _classify(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 1O0,00\nPOS 100,00") == "SAVE_FOR_REVIEW"


def test_save_for_review_when_payments_exceed_total():
    assert _classify(HEAD + "TOTALE GIORNALIERO 150,00\nCONTANTI 100,00\nPOS 100,00") == "SAVE_FOR_REVIEW"


def test_save_for_review_when_total_chosen_only_by_arithmetic():
    text = HEAD + "TOTALE GIORNALIERO 200,00\nTOTALE INCASSI 230,00\nCONTANTI 100,00\nPOS 100,00"
    assert _classify(text) == "SAVE_FOR_REVIEW"


def test_reject_when_required_fields_missing_or_unresolved():
    assert _classify("TOTALE GIORNALIERO 200,00") == "REJECT"
