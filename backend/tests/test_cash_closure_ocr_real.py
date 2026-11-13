"""Test che eseguono REALMENTE Tesseract/Poppler su documenti SINTETICI (Pillow).

Non sono scontrini di registratori reali: verificano la pipeline (pagina intera,
rotazioni, PDF multipagina), non l'accuratezza su registratori differenti.
"""

import io
import shutil
from decimal import Decimal

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.routers import documents as documents_router
from app.services.cash_closure_policy import classify_closure

pytesseract = pytest.importorskip("pytesseract")

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _has_ita():
    try:
        return shutil.which("tesseract") is not None and "ita" in pytesseract.get_languages()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_ita() or shutil.which("pdftoppm") is None,
    reason="Tesseract (ita) o Poppler non disponibili",
)

LINES = [
    "CHIUSURA GIORNALIERA",
    "DEL GIORNO 14/07/2026",
    "NUM. CHIUSURA 201",
    "TOTALE GIORNALIERO 945,80",
    "CONTANTI 320,50",
    "POS 625,30",
    "DOCUMENTI COMMERCIALI 118",
]


def _render(lines=LINES, size=(1000, 800), x=40):
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 44)
    for i, line in enumerate(lines):
        draw.text((x, 40 + i * 80), line, fill="black", font=font)
    return image


def _png(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _check(result):
    assert result["date"].isoformat() == "2026-07-14"
    assert result["closure_number"] == "201"
    assert result["total_amount"] == Decimal("945.80")
    assert result["cash_amount"] == Decimal("320.50")
    assert result["card_amount"] == Decimal("625.30")


def test_full_image():
    _check(documents_router.extract_daily_cash_closure(_png(_render()), "png"))


def test_management_screenshot_needs_review_and_keeps_partial_total_separate():
    image = _render([
        "CHIUSURA GIORNALIERA",
        "DATA 26/09/2023",
        "NUMERO SCONTRINI 25",
        "TOTALE SCONTRINI 303,50",
        "TOTALE FATTURE 5,50",
        "PAGAMENTI CONTANTI 255,50",
        "NUMERO AZZERAMENTI 10",
    ], size=(1600, 800))
    result = documents_router.extract_daily_cash_closure(_png(image), "png")
    assert classify_closure(result) == "SAVE_FOR_REVIEW"
    assert result["date"].isoformat() == "2023-09-26"
    assert result["receipts_count"] == 25
    assert result["receipts_total"] == Decimal("303.50")
    assert result["total_amount"] is None
    assert result["closure_number"] is None
    assert result["cash_amount"] == Decimal("255.50")
    assert result["card_amount"] is None


def test_generic_image_with_date_and_cash_is_not_a_closure():
    image = _render(["FOTO VACANZE", "DATA 26/09/2023", "CONTANTI 255,50"])
    result = documents_router.extract_daily_cash_closure(_png(image), "png")
    assert classify_closure(result) == "REJECT"


def test_content_in_legacy_crop_margin_is_still_read():
    # Il testo parte a sinistra, nella fascia (18%) eliminata dal vecchio ritaglio fisso.
    wide = _render(size=(1800, 800), x=10)
    _check(documents_router.extract_daily_cash_closure(_png(wide), "png"))


@pytest.mark.parametrize("degrees", [90, 180, 270])
def test_rotated_images(degrees):
    rotated = _render().rotate(degrees, expand=True, fillcolor="white")
    _check(documents_router.extract_daily_cash_closure(_png(rotated), "png"))


def test_multipage_pdf_reads_all_pages():
    page1 = _render(LINES[:3])
    page2 = _render(LINES[3:])
    buf = io.BytesIO()
    page1.save(buf, format="PDF", save_all=True, append_images=[page2])
    _check(documents_router.extract_daily_cash_closure(buf.getvalue(), "pdf"))


def test_alternate_reads_produce_text():
    texts = dict(documents_router.extract_alternate_texts(_png(_render()), "png"))
    assert set(texts) == {"legacy_crop", "flattened_denoised"}
    assert "945" in texts["flattened_denoised"]


def test_unreadable_file_yields_no_alternates():
    assert list(documents_router.extract_alternate_texts(b"garbage", "png")) == []
