"""Fase 2: test multi-layout con Tesseract/Poppler REALI su documenti SINTETICI.

I documenti sono generati con Pillow per simulare registratori diversi (etichette,
ordine, dimensioni, orientamento, qualità). NON sono scontrini reali: i risultati
dimostrano il comportamento della pipeline, non l'accuratezza su registratori reali.

Criterio di superamento ("nessun errore silenzioso"): per ogni campo il valore
estratto è uguale all'atteso, oppure è assente (None) E il campo è segnalato in
`diagnostics["unresolved_fields"]`. Un valore sbagliato non è mai accettabile.
"""

import datetime as dt
import io
import random
import shutil
import sys
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, "/workspaces/bar-margin-analyzer/backend")

from app.database import Base
from app.models import CashClosureIntake, DailyCashClosure, Document
from app.routers import cash_closures, documents as documents_router
from test_documents_cash_month import _test_context, upload_for_test

pytesseract = pytest.importorskip("pytesseract")

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
FIELDS = ("date", "closure_number", "total_amount", "cash_amount", "card_amount", "receipts_count")


def _tesseract_ready():
    try:
        return shutil.which("tesseract") is not None and "ita" in pytesseract.get_languages()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _tesseract_ready() or shutil.which("pdftoppm") is None,
    reason="Tesseract (ita) o Poppler non disponibili",
)


def render(
    lines,
    size=(1000, 900),
    font_size=40,
    font="DejaVuSansMono.ttf",
    x=40,
    y=40,
    rotate=0,
    blur=0.0,
    noise=0.0,
    contrast=None,
    shadow=False,
):
    """Riga = testo oppure (etichetta, valore) con il valore allineato a destra."""
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    pil_font = ImageFont.truetype(FONT_DIR + font, font_size)
    gap = int(font_size * 1.6)
    for index, line in enumerate(lines):
        if isinstance(line, tuple):
            draw.text((x, y + index * gap), line[0], fill=0, font=pil_font)
            width = draw.textlength(line[1], font=pil_font)
            draw.text((size[0] - x - width, y + index * gap), line[1], fill=0, font=pil_font)
        else:
            draw.text((x, y + index * gap), line, fill=0, font=pil_font)
    pixels = image.load()
    if shadow:
        for px in range(size[0]):
            factor = 0.55 + 0.45 * px / size[0]
            for py in range(size[1]):
                pixels[px, py] = int(pixels[px, py] * factor)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        rng = random.Random(1)
        pixels = image.load()
        for _ in range(int(size[0] * size[1] * noise)):
            pixels[rng.randrange(size[0]), rng.randrange(size[1])] = rng.choice((0, 255))
    if contrast:
        image = image.point(lambda value: int(255 - (255 - value) * contrast))
    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor=255)
    return image


def to_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def extract(image):
    return documents_router.extract_daily_cash_closure(to_png(image), "png")


def assert_no_silent_error(result, expected):
    unresolved = set(result["diagnostics"]["unresolved_fields"])
    for field in FIELDS:
        actual = result[field]
        if actual is not None:
            assert actual == expected[field], (
                f"{field}: ottenuto {actual!r}, atteso {expected[field]!r} (errore NON segnalato)"
            )
        else:
            assert field in unresolved, f"{field} assente ma non segnalato come irrisolto"


def expected(date, number, total, cash, card, receipts):
    return {
        "date": date,
        "closure_number": number,
        "total_amount": Decimal(total) if total else None,
        "cash_amount": Decimal(cash) if cash else None,
        "card_amount": Decimal(card) if card else None,
        "receipts_count": receipts,
    }


D = dt.date(2026, 11, 3)

# (id, immagine, atteso, campi che DEVONO essere letti esattamente)
LAYOUTS = {
    "A_totale_in_fondo_con_iva_subtotale_resto": (
        lambda: render(
            [
                "BAR CENTRALE SRL", "RAPPORTO Z N. 0345", "DATA 03/11/2026 ORA 22:41",
                "SUBTOTALE 410,00", "IVA 10% 37,27", "IMPONIBILE 372,73", "CONTANTI 180,50",
                "POS 229,50", "RESTO 12,00", "TOTALE GIORNALIERO 410,00", "SCONTRINI EMESSI 64",
            ]
        ),
        expected(D, "0345", "410.00", "180.50", "229.50", 64),
        set(FIELDS),
    ),
    "B_orizzontale_cash_e_buoni_pasto": (
        lambda: render(
            [
                "CHIUSURA FISCALE", "N. CHIUSURA 77", "DEL GIORNO 2026-11-03",
                "CORRISPETTIVI 1.284,60", "CASH 604,10", "PAGAMENTI ELETTRONICI 580,50",
                "BUONI PASTO 100,00", "DOCUMENTI COMMERCIALI 151",
            ],
            size=(1600, 700), font="DejaVuSans.ttf", font_size=38,
        ),
        expected(D, "77", "1284.60", "604.10", "580.50", 151),
        set(FIELDS),
    ),
    "C_ruotato_90_bancomat_ticket_zero": (
        lambda: render(
            [
                "AZZERAMENTO 0912", "Data chiusura 03.11.2026", "TOTALE INCASSI 530,20",
                "CONTANTE 130,20", "BANCOMAT 400,00", "TICKET 0,00", "SCONTRINI 41",
            ],
            size=(1000, 800), font_size=42, rotate=90,
        ),
        expected(D, "0912", "530.20", "130.20", "400.00", 41),
        set(FIELDS),
    ),
    "D_valori_incolonnati_a_destra_grassetto": (
        lambda: render(
            [
                ("REPORT Z", "N. 18"), ("DEL GIORNO", "03/11/2026"), ("TOTALE VENDITE", "758,90"),
                ("CONTANTI", "258,90"), ("CARTE DI CREDITO", "500,00"), ("DOCUMENTI DI VENDITA", "93"),
            ],
            size=(1100, 800), font="DejaVuSans-Bold.ttf",
        ),
        expected(D, "18", "758.90", "258.90", "500.00", 93),
        set(FIELDS),
    ),
    "E_foto_ombra_sfocata_rumorosa_capovolta": (
        lambda: render(
            [
                "CHIUSURA GIORNALIERA", "NUM. CHIUSURA 204", "DEL GIORNO 03/11/2026",
                "AMMONTARE GIORNO 640,40", "AMMONTARE 220,40", "PAGAM. ELETTRONICI 420,00",
                "DOCUM. DI VENDITA 77",
            ],
            size=(1000, 800), font_size=42, shadow=True, blur=1.0, noise=0.01, contrast=0.8, rotate=180,
        ),
        expected(D, "204", "640.40", "220.40", "420.00", 77),
        # Immagine volutamente molto degradata: i campi principali devono essere
        # letti; il numero documenti può restare irrisolto, mai errato.
        {"date", "closure_number", "total_amount", "cash_amount", "card_amount"},
    ),
    "F_importi_simili_e_data_di_stampa": (
        lambda: render(
            [
                "STAMPA 04/11/2026", "DEL GIORNO 03/11/2026", "NUM. CHIUSURA 310",
                "TOTALE PARZIALE 450,00", "TOTALE GIORNALIERO 454,00", "CONTANTI 154,00",
                "POS 300,00", "IVA 10% 41,27",
            ],
            size=(1000, 800), font_size=42,
        ),
        expected(D, "310", "454.00", "154.00", "300.00", None),
        {"date", "closure_number", "total_amount", "cash_amount", "card_amount"},
    ),
    "G_totale_generico_con_gran_totale_progressivo": (
        lambda: render(
            [
                "Z N. 41", "DATA 03/11/2026", "GRAN TOTALE PROGRESSIVO 45.210,00",
                "TOTALE 200,00", "CONTANTI 120,00", "CARTE 80,00",
            ],
            size=(1000, 700), font_size=42,
        ),
        expected(D, "41", "200.00", "120.00", "80.00", None),
        {"date", "closure_number", "total_amount", "cash_amount", "card_amount"},
    ),
}


@pytest.mark.parametrize("layout_id", list(LAYOUTS))
def test_synthetic_layout_values_and_no_silent_errors(layout_id):
    build, wanted, must_read = LAYOUTS[layout_id]
    result = extract(build())
    assert_no_silent_error(result, wanted)
    for field in must_read:
        assert result[field] == wanted[field], f"{layout_id}: {field} non letto correttamente"


def test_multipage_pdf_with_fields_split_across_pages():
    page1 = render(["RAPPORTO Z N. 52", "DATA 03/11/2026", "SUBTOTALE 99,00"])
    page2 = render(["TOTALE GIORNALIERO 320,00", "CONTANTI 120,00", "POS 200,00", "SCONTRINI 28"])
    buffer = BytesIO()
    page1.save(buffer, format="PDF", save_all=True, append_images=[page2])
    result = documents_router.extract_daily_cash_closure(buffer.getvalue(), "pdf")
    assert_no_silent_error(result, expected(D, "52", "320.00", "120.00", "200.00", 28))
    assert result["total_amount"] == Decimal("320.00")


# ---------------------------------------------------------------- anomalie (OCR reale)


def test_real_ocr_missing_cash_is_none_and_flagged_not_zero():
    result = extract(
        render(["NUM. CHIUSURA 88", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00", "POS 200,00"])
    )
    assert result["total_amount"] == Decimal("200.00")
    assert result["card_amount"] == Decimal("200.00")
    assert result["cash_amount"] is None
    assert "cash_amount" in result["diagnostics"]["unresolved_fields"]
    assert any("Contanti non rilevati" in w for w in documents_router.build_cash_closure_warnings(result))


def test_real_ocr_explicit_zero_cash_is_zero_not_missing():
    result = extract(
        render(["NUM. CHIUSURA 89", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00", "CONTANTI 0,00", "POS 200,00"])
    )
    assert result["cash_amount"] == Decimal("0.00")
    assert "cash_amount" not in result["diagnostics"]["unresolved_fields"]
    assert documents_router.build_cash_closure_warnings(result) == []


def test_real_ocr_multiple_conflicting_dates_not_guessed():
    result = extract(
        render(["NUM. CHIUSURA 90", "14/07/2026", "21/07/2026", "TOTALE GIORNALIERO 200,00", "CONTANTI 100,00", "POS 100,00"])
    )
    assert result["date"] is None
    assert "date" in result["diagnostics"]["unresolved_fields"]


def test_real_ocr_conflicting_totals_unresolvable_are_not_guessed():
    # Nessuna coppia contanti+POS conferma uno dei due totali: nessuna scelta.
    result = extract(
        render(
            [
                "NUM. CHIUSURA 91", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00",
                "TOTALE INCASSI 230,00", "CONTANTI 100,00", "POS 90,00",
            ]
        )
    )
    assert result["total_amount"] is None
    assert "total_amount" in result["diagnostics"]["unresolved_fields"]


def test_real_ocr_total_chosen_among_alternatives_is_flagged_not_silent():
    # 200,00 è coerente con contanti+POS, ma 230,00 resta un candidato valido
    # (potrebbe includere un metodo di pagamento non letto): la scelta va segnalata.
    result = extract(
        render(
            [
                "NUM. CHIUSURA 91", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00",
                "TOTALE INCASSI 230,00", "CONTANTI 100,00", "POS 100,00",
            ]
        )
    )
    assert result["total_amount"] == Decimal("200.00")
    assert "total_amount:resolved_among_alternatives" in result["diagnostics"]["anomalies"]
    warnings = documents_router.build_cash_closure_warnings(result)
    assert any("total_amount" in w and "230.00" in w for w in warnings)


def test_real_ocr_clean_document_does_not_trigger_second_read():
    result = extract(LAYOUTS["A_totale_in_fondo_con_iva_subtotale_resto"][0]())
    assert result["diagnostics"]["second_read"] == "not_needed"


def test_real_ocr_degraded_document_triggers_second_read():
    result = extract(LAYOUTS["E_foto_ombra_sfocata_rumorosa_capovolta"][0]())
    assert result["diagnostics"]["second_read"] != "not_needed"


# ---------------------------------------------------- upload end-to-end (DB temporaneo)


@pytest.fixture
def upload_env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/phase2.db")
    Base.metadata.create_all(engine)
    monkeypatch.chdir(tmp_path)
    return engine


def _upload_png(session, image):
    import asyncio

    return asyncio.run(
        upload_for_test(
            file=UploadFile(file=BytesIO(to_png(image)), filename="closure.png"),
            month="2026-11",
            section="cash",
            db=session,
        )
    )


def test_upload_missing_cash_is_flagged_and_saved_as_null(upload_env):
    image = render(["NUM. CHIUSURA 88", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00", "POS 200,00"])
    with Session(upload_env) as session:
        payload = _upload_png(session, image)
        closure = session.scalars(select(CashClosureIntake)).one()
        assert session.scalars(select(DailyCashClosure)).all() == []
    assert "cash_amount" in payload["extraction"]["unresolved_fields"]
    assert any("Contanti non rilevati" in w for w in payload["warnings"])
    assert closure.total_amount == Decimal("200.00")
    assert closure.cash_amount is None


def test_upload_conflicting_total_is_staged_for_review(upload_env):
    image = render(
        ["NUM. CHIUSURA 91", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00", "TOTALE INCASSI 230,00", "POS 100,00"]
    )
    with Session(upload_env) as session:
        payload = _upload_png(session, image)
        intake = session.scalars(select(CashClosureIntake)).one()
        assert payload["status"] == "Da verificare"
        assert intake.status == "pending"
        assert intake.total_amount is None
        assert session.scalars(select(DailyCashClosure)).all() == []
        assert len(session.scalars(select(Document)).all()) == 1


def test_upload_same_closure_twice_is_conflict(upload_env):
    image = render(
        ["NUM. CHIUSURA 92", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00", "CONTANTI 100,00", "POS 100,00"]
    )
    with Session(upload_env) as session:
        _upload_png(session, image)
        with pytest.raises(HTTPException) as error:
            _upload_png(session, image)
        assert error.value.status_code == 409
        assert session.scalars(select(DailyCashClosure)).all() == []
        assert len(session.scalars(select(CashClosureIntake)).all()) == 1


def test_upload_same_total_other_number_is_saved_with_duplicate_warning(upload_env):
    first = render(
        ["NUM. CHIUSURA 92", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00", "CONTANTI 100,00", "POS 100,00"]
    )
    second = render(
        ["NUM. CHIUSURA 93", "DATA 03/11/2026", "TOTALE GIORNALIERO 200,00", "CONTANTI 100,00", "POS 100,00"]
    )
    with Session(upload_env) as session:
        _upload_png(session, first)
        intake = session.scalars(select(CashClosureIntake)).one()
        context = _test_context(session)
        cash_closures.approve_cash_closure_review(
            intake.id, _auth_session=context.auth_session, context=context, db=session
        )
        payload = _upload_png(session, second)
        assert len(session.scalars(select(DailyCashClosure)).all()) == 1
        assert len(session.scalars(select(CashClosureIntake)).all()) == 2
    assert any("stesso totale" in w for w in payload["warnings"])


# ------------------------------------------- Passaggio 51: casi B–F con Tesseract reale (sintetici)

H51 = ["NUM. CHIUSURA 120", "DATA 03/11/2026"]


def test_real_case_b_total_only_has_no_breakdown_and_no_second_read():
    result = extract(render(H51 + ["TOTALE GIORNALIERO 200,00", "SCONTRINI EMESSI 31"]))
    assert result["total_amount"] == Decimal("200.00")
    assert result["cash_amount"] is None and result["card_amount"] is None
    assert {"cash_amount", "card_amount"} <= set(result["diagnostics"]["unresolved_fields"])
    assert result["diagnostics"]["second_read"] == "not_needed"


def test_real_case_c_obscured_cash_amount_is_never_zero_or_deduced():
    # L'importo dei contanti è coperto da una macchia nera (illeggibile davvero). Il valore
    # 100,00 sarebbe deducibile per differenza (200 - 100), ma non va inventato.
    image = render(H51 + ["TOTALE GIORNALIERO 200,00", "CONTANTI 100,00", "POS 100,00"])
    ImageDraw.Draw(image).rectangle((250, 40 + 3 * 64 - 4, 430, 40 + 3 * 64 + 52), fill=0)
    result = extract(image)
    assert result["total_amount"] == Decimal("200.00")
    assert result["card_amount"] == Decimal("100.00")
    assert result["cash_amount"] is None
    assert "cash_amount" in result["diagnostics"]["unresolved_fields"]
    assert result["diagnostics"]["second_read"] != "not_needed"
    assert "payments:incomplete" in result["diagnostics"]["anomalies"]


def test_real_case_d_two_pos_lines_are_not_summed_or_taken_as_aggregate():
    result = extract(render(H51 + ["TOTALE GIORNALIERO 300,00", "CONTANTI 100,00", "POS 120,00", "POS 80,00"]))
    assert result["total_amount"] == Decimal("300.00")
    assert result["card_amount"] is None
    assert "card_amount" in result["diagnostics"]["unresolved_fields"]


def test_real_case_d_aggregate_with_detail_lines_is_not_double_counted():
    result = extract(
        render(H51 + ["TOTALE GIORNALIERO 300,00", "CONTANTI 100,00", "PAGAMENTI ELETTRONICI 200,00", "POS 120,00", "BANCOMAT 80,00"])
    )
    assert result["card_amount"] == Decimal("200.00")
    assert result["diagnostics"]["anomalies"] == []


def test_real_case_d_accounting_difference_is_reported_but_values_are_kept():
    result = extract(render(H51 + ["TOTALE GIORNALIERO 300,00", "CONTANTI 100,00", "POS 100,00", "STORNI 20,00"]))
    assert (result["cash_amount"], result["card_amount"]) == (Decimal("100.00"), Decimal("100.00"))
    assert "payments:total_mismatch" in result["diagnostics"]["anomalies"]


def test_real_case_f_explicit_zero_cash_is_zero_not_missing():
    result = extract(render(H51 + ["TOTALE GIORNALIERO 200,00", "CONTANTI 0,00", "POS 200,00"]))
    assert result["cash_amount"] == Decimal("0.00")
    assert "cash_amount" not in result["diagnostics"]["unresolved_fields"]


def test_upload_total_only_is_saved_with_null_breakdown(upload_env):
    image = render(H51 + ["TOTALE GIORNALIERO 200,00"])
    with Session(upload_env) as session:
        payload = _upload_png(session, image)
        closure = session.scalars(select(CashClosureIntake)).one()
        assert closure.status == "pending"
        assert session.scalars(select(DailyCashClosure)).all() == []
    assert closure.total_amount == Decimal("200.00")
    assert {"cash_amount", "card_amount"} <= set(payload["extraction"]["unresolved_fields"])
    assert closure.cash_amount is None
    assert closure.card_amount is None
