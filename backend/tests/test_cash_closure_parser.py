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


# ---------------------------------------------------------------- Fase 2: anomalie (testo simulato)

HEAD = "DATA 03/11/2026\nNUM. CHIUSURA 5\n"


def _unresolved(result):
    return set(result["diagnostics"]["unresolved_fields"])


def test_unrecognised_cash_is_none_and_flagged_malformed():
    e = ClosureExtraction(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 1O0,00\nPOS 100,00")
    r = e.to_result()
    assert r["cash_amount"] is None and "cash_amount" in _unresolved(r)
    assert "cash_amount:malformed" in r["diagnostics"]["anomalies"]
    assert e.needs_second_read()


def test_absent_cash_line_is_none_and_not_malformed():
    r = extract(HEAD + "TOTALE GIORNALIERO 200,00\nPOS 200,00")
    assert r["cash_amount"] is None and "cash_amount" in _unresolved(r)
    assert "cash_amount:malformed" not in r["diagnostics"]["anomalies"]


def test_zero_read_is_distinguished_from_missing_and_unreadable():
    zero = extract(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 0,00\nPOS 200,00")
    missing = extract(HEAD + "TOTALE GIORNALIERO 200,00\nPOS 200,00")
    unreadable = extract(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 2O0,00\nPOS 200,00")
    assert zero["cash_amount"] == Decimal("0.00") and "cash_amount" not in _unresolved(zero)
    assert missing["cash_amount"] is None and unreadable["cash_amount"] is None
    assert missing["diagnostics"]["fields"]["cash_amount"]["status"] == "missing"
    assert unreadable["diagnostics"]["fields"]["cash_amount"]["status"] == "malformed"


def test_ambiguous_cash_amounts_are_conflict_not_first_value():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nCASH 150,00\nPOS 200,00")
    assert r["cash_amount"] != Decimal("100.00") or "cash_amount" not in _unresolved(r)
    status = r["diagnostics"]["fields"]["cash_amount"]["status"]
    assert status in {"ambiguous", "ok"}
    if r["cash_amount"] is not None:
        assert "cash_amount:resolved_among_alternatives" in r["diagnostics"]["anomalies"]


def test_multiple_dates_unlabeled_conflict_and_labeled_wins():
    assert extract("14/07/2026\n21/07/2026\nNUM. CHIUSURA 1")["date"] is None
    assert extract("DEL GIORNO 14/07/2026\n21/07/2026\nNUM. CHIUSURA 1")["date"] == dt.date(2026, 7, 14)


def test_malformed_closure_number_is_flagged():
    r = extract("DATA 03/11/2026\nNUM. CHIUSURA 2O1\nTOTALE GIORNALIERO 10,00")
    assert r["closure_number"] is None
    assert r["diagnostics"]["fields"]["closure_number"]["status"] == "malformed"


def test_total_with_wrong_label_is_never_used():
    text = HEAD + "GRAN TOTALE 45.210,00\nTOTALE PARZIALE 99,00\nIVA 10% 18,00\nRESTO 5,00\nTOTALE GIORNALIERO 200,00"
    assert extract(text)["total_amount"] == Decimal("200.00")
    only_wrong = HEAD + "GRAN TOTALE 45.210,00\nTOTALE PARZIALE 99,00\nIVA 10% 18,00\nRESTO 5,00"
    r = extract(only_wrong)
    assert r["total_amount"] is None and "total_amount" in _unresolved(r)


def test_first_and_second_read_disagree_on_amount_is_unresolved_not_first():
    base = HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 100,00\n"
    e = ClosureExtraction(base + "POS 100,00\n")
    assert not e.needs_second_read()
    f = ClosureExtraction(base + "POS 190,00\n")  # incoerente col totale -> seconda lettura
    assert f.needs_second_read()
    f.merge_text(base + "POS 150,00\n", "alt")
    assert f.to_result()["card_amount"] is None
    assert "card_amount" in _unresolved(f.to_result())


def test_candidate_lost_by_degraded_second_read_is_still_flagged():
    full = HEAD + "TOTALE GIORNALIERO 200,00\nTOTALE INCASSI 230,00\nCONTANTI 100,00\nPOS 100,00"
    degraded = HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 100,00\nPOS 100,00"
    e = ClosureExtraction(full)
    e.merge_text(degraded, "alt")
    r = e.to_result()
    assert r["total_amount"] == Decimal("200.00")
    assert "total_amount:resolved_among_alternatives" in r["diagnostics"]["anomalies"]
    assert any("total_amount" in w for w in documents_router.build_cash_closure_warnings(r))


def test_z_number_label_requires_number_marker():
    assert extract("Z N. 41\nDATA 03/11/2026")["closure_number"] == "41"
    assert extract("Z 41\nDATA 03/11/2026")["closure_number"] is None


# ------------------------------------------------ Fase 2: caratterizzazione contabile (nessuna regola nuova)


def test_two_different_pos_values_are_not_summed_and_not_double_counted():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPOS 120,00\nPOS 80,00")
    assert r["card_amount"] is None  # decisione: sommare più terminali richiede autorizzazione
    assert "card_amount" in _unresolved(r)


def test_carte_and_bancomat_different_values_are_not_summed():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nCARTE 120,00\nBANCOMAT 80,00")
    assert r["card_amount"] is None


def test_aggregate_electronic_wins_over_detail_without_double_count():
    r = extract(
        HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPAGAMENTI ELETTRONICI 200,00\nPOS 120,00\nBANCOMAT 80,00"
    )
    assert r["card_amount"] == Decimal("200.00")


def test_meal_vouchers_and_tickets_never_become_cash_or_card():
    r = extract(HEAD + "TOTALE GIORNALIERO 270,00\nCONTANTI 100,00\nBUONI PASTO 50,00\nPOS 120,00")
    assert r["cash_amount"] == Decimal("100.00") and r["card_amount"] == Decimal("120.00")
    assert r["diagnostics"]["other_payments_total"] == Decimal("50.00")
    assert documents_router.build_cash_closure_warnings(r) == []


def test_buoni_pasto_and_ticket_with_different_amounts_are_not_summed_and_gap_is_flagged():
    # Stessa categoria con importi discordanti: ignorata (sommarla sarebbe una nuova
    # regola). La differenza resta segnalata, mai attribuita ai contanti.
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nBUONI PASTO 50,00\nTICKET 30,00\nPOS 120,00")
    assert r["cash_amount"] == Decimal("100.00") and r["card_amount"] == Decimal("120.00")
    assert r["diagnostics"]["other_payments_total"] == Decimal("0.00")
    assert "payments:total_mismatch" in r["diagnostics"]["anomalies"]


def test_vouchers_without_electronic_line_do_not_invent_card():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nBUONI PASTO 50,00")
    assert r["card_amount"] is None


def test_accounting_difference_is_distinct_from_missing_information():
    diff = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 200,00\nPOS 200,00")
    missing = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 200,00")
    assert diff["cash_amount"] is not None and diff["card_amount"] is not None
    assert "payments:total_mismatch" in diff["diagnostics"]["anomalies"]
    assert missing["card_amount"] is None
    assert "payments:incomplete" in missing["diagnostics"]["anomalies"]


# ------------------------------------------------------------------ Passaggio 51: casi A–F
# Descrivono il comportamento ATTUALE dell'estrazione (parser + avvisi). Gli scenari
# desiderati in futuro sono in test_cash_closure_future_policy.py (tutti skip).


def _anomalies(result):
    return set(result["diagnostics"]["anomalies"])


def test_case_a_complete_and_coherent_has_no_anomalies_and_no_second_read():
    e = ClosureExtraction(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPOS 200,00\nSCONTRINI 40")
    r = e.to_result()
    assert not e.needs_second_read()
    assert r["diagnostics"]["anomalies"] == [] and r["diagnostics"]["unresolved_fields"] == []
    assert documents_router.build_cash_closure_warnings(r) == []


def test_case_b_reliable_total_without_breakdown_keeps_total_and_marks_breakdown_missing():
    e = ClosureExtraction(HEAD + "TOTALE GIORNALIERO 200,00")
    r = e.to_result()
    assert r["total_amount"] == Decimal("200.00")
    assert r["cash_amount"] is None and r["card_amount"] is None  # mai zero
    assert {"cash_amount", "card_amount"} <= _unresolved(r)
    assert r["diagnostics"]["fields"]["cash_amount"]["status"] == "missing"
    assert not e.needs_second_read()  # nessuna seconda lettura inutile
    assert _anomalies(r) == set()


def test_case_c_unreadable_breakdown_triggers_second_read_and_is_not_zero():
    e = ClosureExtraction(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 1O0,00\nPOS 1OO,00")
    r = e.to_result()
    assert e.needs_second_read()
    assert r["cash_amount"] is None and r["card_amount"] is None
    assert {"cash_amount:malformed", "card_amount:malformed"} <= _anomalies(r)


def test_case_c_second_read_recovers_unreadable_breakdown_only_if_confirmed_by_text():
    bad = HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 1O0,00\nPOS 100,00"
    good = HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 100,00\nPOS 100,00"
    e = ClosureExtraction(bad)
    e.merge_text(good, "alt")
    assert e.to_result()["cash_amount"] == Decimal("100.00")
    # Se la seconda lettura non vede il campo, il valore resta irrisolto: non si deduce
    # per differenza (total - card), che sarebbe un valore inventato.
    e2 = ClosureExtraction(bad)
    e2.merge_text(HEAD + "TOTALE GIORNALIERO 200,00\nPOS 100,00", "alt")
    assert e2.to_result()["cash_amount"] is None


def test_case_d_unrecognised_extra_payment_method_is_a_difference_not_an_ocr_error():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPOS 100,00\nSTORNI 20,00")
    assert (r["cash_amount"], r["card_amount"]) == (Decimal("100.00"), Decimal("100.00"))
    assert "payments:total_mismatch" in _anomalies(r)
    assert r["total_amount"] == Decimal("300.00")  # nessun valore modificato
    assert any("non coincide" in w for w in documents_router.build_cash_closure_warnings(r))


def test_case_d_recognised_other_payment_explains_the_difference():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPOS 100,00\nBONIFICI 100,00")
    assert "payments:total_mismatch" not in _anomalies(r)
    assert r["diagnostics"]["other_payments_total"] == Decimal("100.00")


def test_case_d_aggregate_and_identical_detail_are_not_double_counted():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPAGAMENTI ELETTRONICI 200,00\nPOS 200,00")
    assert r["card_amount"] == Decimal("200.00")
    assert r["diagnostics"]["anomalies"] == []


def test_case_d_aggregate_with_partial_detail_lines_raises_no_false_anomaly():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPAGAMENTI ELETTRONICI 200,00\nPOS 120,00")
    assert r["card_amount"] == Decimal("200.00")
    assert r["diagnostics"]["anomalies"] == []
    assert documents_router.build_cash_closure_warnings(r) == []


def test_case_d_two_distinct_pos_lines_are_not_an_aggregate_total():
    r = extract(HEAD + "TOTALE GIORNALIERO 300,00\nCONTANTI 100,00\nPOS 120,00\nPOS 80,00")
    assert r["card_amount"] is None  # 200 sarebbe una somma non autorizzata
    assert "card_amount:ambiguous" in _anomalies(r)


def test_case_d_cash_plus_card_above_total_is_flagged_never_corrected():
    r = extract(HEAD + "TOTALE GIORNALIERO 150,00\nCONTANTI 100,00\nPOS 100,00")
    assert (r["total_amount"], r["cash_amount"], r["card_amount"]) == (
        Decimal("150.00"), Decimal("100.00"), Decimal("100.00"),
    )
    assert "payments:total_mismatch" in _anomalies(r)


def test_case_e_alternative_totals_arithmetic_pick_is_flagged_not_proof():
    r = extract(HEAD + "TOTALE GIORNALIERO 200,00\nTOTALE INCASSI 230,00\nCONTANTI 100,00\nPOS 100,00")
    assert r["total_amount"] == Decimal("200.00")
    assert "total_amount:resolved_among_alternatives" in _anomalies(r)
    assert r["diagnostics"]["fields"]["total_amount"]["competing"] == ["200.00", "230.00"]


def test_case_e_alternative_totals_without_breakdown_stay_unresolved():
    r = extract(HEAD + "TOTALE GIORNALIERO 200,00\nTOTALE INCASSI 230,00")
    assert r["total_amount"] is None and "total_amount" in _unresolved(r)


def test_case_e_alternative_totals_with_no_matching_breakdown_stay_unresolved():
    r = extract(HEAD + "TOTALE GIORNALIERO 200,00\nTOTALE INCASSI 230,00\nCONTANTI 100,00\nPOS 90,00")
    assert r["total_amount"] is None


def test_case_f_explicit_zero_is_distinct_from_missing_unreadable_and_ambiguous():
    zero = extract(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 0,00\nPOS 200,00")
    missing = extract(HEAD + "TOTALE GIORNALIERO 200,00\nPOS 200,00")
    unreadable = extract(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 0,O0\nPOS 200,00")
    ambiguous = extract(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 0,00\nCASH 50,00\nPOS 100,00")
    statuses = {
        name: res["diagnostics"]["fields"]["cash_amount"]["status"]
        for name, res in (("zero", zero), ("missing", missing), ("unreadable", unreadable), ("ambiguous", ambiguous))
    }
    assert zero["cash_amount"] == Decimal("0.00") and statuses["zero"] == "ok"
    assert missing["cash_amount"] is None and statuses["missing"] == "missing"
    assert unreadable["cash_amount"] is None and statuses["unreadable"] == "malformed"
    assert ambiguous["cash_amount"] is None and statuses["ambiguous"] == "ambiguous"


def test_case_f_all_zero_closure_is_read_as_zeros():
    r = extract(HEAD + "TOTALE GIORNALIERO 0,00\nCONTANTI 0,00\nPOS 0,00")
    assert (r["total_amount"], r["cash_amount"], r["card_amount"]) == (Decimal("0.00"),) * 3
    assert r["diagnostics"]["anomalies"] == []


def test_case_f_zero_chosen_by_arithmetic_among_alternatives_is_flagged():
    r = extract(HEAD + "TOTALE GIORNALIERO 200,00\nCONTANTI 0,00\nCASH 50,00\nPOS 200,00")
    assert r["cash_amount"] == Decimal("0.00")
    assert "cash_amount:resolved_among_alternatives" in _anomalies(r)
