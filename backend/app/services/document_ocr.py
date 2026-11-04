"""Acquisizione, preprocessing e OCR dei documenti (Tesseract, Pillow, pdf2image).

Nessuna pagina viene ritagliata nella lettura principale. Le letture
alternative (ritaglio storico, immagine binarizzata) servono solo come secondo
tentativo e sono eseguite in modo lazy dal chiamante.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Callable, Iterator

import pytesseract
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageSequence, UnidentifiedImageError

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}
OCR_LANG = "ita"
OCR_TIMEOUT_SECONDS = 120
PDF_RENDER_DPI = 250
ORIENTATION_PROBE_SIZE = 1400
TARGET_LONG_SIDE = 2800
MAX_UPSCALE = 3.0


class DocumentReadError(Exception):
    """Il file non è un'immagine o un PDF leggibile."""


@dataclass(frozen=True)
class OcrAttempt:
    name: str
    prepare: Callable[[Image.Image], Image.Image]
    psm: int


def _flatten_to_gray(image: Image.Image) -> Image.Image:
    if "A" in image.getbands() or image.mode == "P":
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba)
    return ImageOps.grayscale(image)


def _upscale(gray: Image.Image) -> Image.Image:
    long_side = max(gray.size)
    factor = min(MAX_UPSCALE, TARGET_LONG_SIDE / long_side)
    if factor <= 1:
        return gray
    return gray.resize((round(gray.width * factor), round(gray.height * factor)), Image.LANCZOS)


def _prepare_full_page(gray: Image.Image) -> Image.Image:
    return ImageOps.autocontrast(_upscale(gray), cutoff=1)


def _prepare_legacy_crop(gray: Image.Image) -> Image.Image:
    # Pipeline storica: ritaglio fisso e ingrandimento 2x. Utile solo come
    # tentativo aggiuntivo perché può eliminare parti del documento.
    width, height = gray.size
    cropped = gray.crop((int(width * 0.18), int(height * 0.02), int(width * 0.92), int(height * 0.98)))
    return cropped.resize((cropped.width * 2, cropped.height * 2))


def _prepare_flattened_binary(gray: Image.Image) -> Image.Image:
    # Compensa ombre e illuminazione non uniforme (tipiche delle fotografie).
    scaled = _upscale(gray)
    background = scaled.filter(ImageFilter.GaussianBlur(radius=max(scaled.size) / 40))
    flattened = ImageOps.invert(ImageChops.subtract(background, scaled, scale=1.0, offset=0))
    flattened = ImageOps.autocontrast(flattened, cutoff=1)
    return flattened.point(lambda value: 255 if value > 140 else 0)


PRIMARY_ATTEMPT = OcrAttempt("full_page", _prepare_full_page, 4)
ALTERNATE_ATTEMPTS = (
    OcrAttempt("legacy_crop", _prepare_legacy_crop, 4),
    OcrAttempt("flattened_binary", _prepare_flattened_binary, 6),
)


def load_pages(
    content: bytes,
    extension: str,
    renderer: Callable[..., list[Image.Image]] = convert_from_bytes,
) -> list[Image.Image]:
    try:
        if extension == "pdf":
            pages = renderer(content, dpi=PDF_RENDER_DPI)
        elif extension in IMAGE_EXTENSIONS:
            with Image.open(io.BytesIO(content)) as source:
                pages = [
                    ImageOps.exif_transpose(frame.copy())
                    for frame in ImageSequence.Iterator(source)
                ]
        else:
            raise DocumentReadError(f"Formato non leggibile con OCR: {extension}")
    except DocumentReadError:
        raise
    except PDFInfoNotInstalledError:
        raise
    except (PDFPageCountError, PDFSyntaxError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise DocumentReadError("Documento non leggibile") from exc
    except Image.DecompressionBombError as exc:
        raise DocumentReadError("Immagine troppo grande") from exc
    if not pages:
        raise DocumentReadError("Documento senza pagine")
    return pages


def _rotate_clockwise(image: Image.Image, degrees: int) -> Image.Image:
    if degrees % 360 == 0:
        return image
    return image.rotate(-degrees, expand=True, fillcolor=255)


def _probe(image: Image.Image) -> Image.Image:
    probe = image.copy()
    probe.thumbnail((ORIENTATION_PROBE_SIZE, ORIENTATION_PROBE_SIZE))
    return ImageOps.autocontrast(probe, cutoff=1)


def _readability_score(image: Image.Image) -> float:
    # Misura solo relativa, usata per confrontare le orientazioni dello stesso
    # documento: somma delle confidence Tesseract delle parole alfabetiche.
    data = pytesseract.image_to_data(
        image,
        lang=OCR_LANG,
        config="--psm 4",
        output_type=pytesseract.Output.DICT,
        timeout=OCR_TIMEOUT_SECONDS,
    )
    score = 0.0
    for word, confidence in zip(data["text"], data["conf"]):
        word = word.strip()
        if len(word) >= 3 and word.isalpha() and float(confidence) >= 0:
            score += float(confidence)
    return score


def correct_orientation(gray: Image.Image) -> Image.Image:
    """Raddrizza pagine ruotate di 90/180/270 gradi (foto orizzontali o capovolte)."""
    # L'OSD di Tesseract si è rivelato inaffidabile su scontrini (dichiara 0 gradi
    # per pagine capovolte): si confrontano le quattro orientazioni, privilegiando
    # 0 gradi a parità di punteggio.
    probe = _probe(gray)
    scores = {}
    for degrees in (0, 90, 180, 270):
        try:
            scores[degrees] = _readability_score(_rotate_clockwise(probe, degrees))
        except (pytesseract.TesseractError, RuntimeError):
            scores[degrees] = 0.0
    best = max(scores, key=lambda degrees: (scores[degrees], degrees == 0))
    return _rotate_clockwise(gray, best)


def ocr_prepared(image: Image.Image, attempt: OcrAttempt) -> str:
    return pytesseract.image_to_string(
        attempt.prepare(image),
        lang=OCR_LANG,
        config=f"--psm {attempt.psm}",
        timeout=OCR_TIMEOUT_SECONDS,
    )


def iter_attempt_texts(
    content: bytes,
    extension: str,
    attempts: tuple[OcrAttempt, ...],
    renderer: Callable[..., list[Image.Image]] = convert_from_bytes,
) -> Iterator[tuple[str, str]]:
    """Restituisce (nome tentativo, testo di tutte le pagine), un tentativo alla volta.

    Pagine e orientamento sono calcolati una sola volta; ogni tentativo viene
    eseguito solo quando il chiamante richiede l'elemento successivo.
    """
    pages = [correct_orientation(_flatten_to_gray(page)) for page in load_pages(content, extension, renderer)]
    for attempt in attempts:
        yield attempt.name, "\n".join(ocr_prepared(page, attempt) for page in pages)
