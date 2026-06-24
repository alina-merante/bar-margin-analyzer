import csv
import os
import uuid
from io import BytesIO, StringIO

from PIL import Image, ImageDraw, ImageFont
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pdf2image import convert_from_bytes
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.document import Document
from app.models.daily_cash_closure import DailyCashClosure

import datetime as dt
import re
from decimal import Decimal

import pytesseract

router = APIRouter(prefix="/documents", tags=["documents"])


def classify_document(filename: str) -> tuple[str, str]:
    extension = filename.rsplit(".", 1)[-1].upper() if "." in filename else "FILE"

    if extension == "PDF":
        return "Documento PDF", "Testo rilevato e pronto per classificazione"

    if extension in {"CSV", "XLS", "XLSX"}:
        return "Documento tabellare", "Dati strutturati rilevati"

    if extension in {"JPG", "JPEG", "PNG", "WEBP"}:
        return "Immagine", "Immagine acquisita per lettura AI"

    if extension == "TXT":
        return "Documento testuale", "Testo acquisito"

    return "Documento generico", "Documento acquisito"


def document_to_dict(document: Document) -> dict:
    return {
        "id": document.id,
        "month": document.month,
        "original_filename": document.original_filename,
        "stored_filename": document.stored_filename,
        "document_type": document.document_type,
        "category": document.category,
        "result": document.result,
        "file_url": document.file_url,
        "preview_url": document.preview_url,
        "status": document.status,
        "created_at": document.created_at.isoformat(),
        "section": document.section,
    }


def create_text_preview_image(
    original_filename: str,
    content: bytes,
    extension: str,
    stored_stem: str,
) -> str | None:
    os.makedirs("uploads/previews", exist_ok=True)

    preview_filename = f"{stored_stem}.png"
    preview_path = os.path.join("uploads", "previews", preview_filename)

    text = content.decode("utf-8-sig", errors="replace")

    if extension == "csv":
        reader = csv.reader(StringIO(text))
        lines = []
        for idx, row in enumerate(reader):
            if idx >= 35:
                break
            lines.append("   |   ".join(row))
    else:
        lines = text.splitlines()[:35]

    width = 1200
    padding = 60
    line_height = 32
    height = padding * 2 + 60 + max(1, len(lines)) * line_height

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        text_font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except Exception:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    y = padding
    draw.text((padding, y), original_filename, fill="#2b1a10", font=title_font)

    y += 60

    for line in lines:
        draw.text((padding, y), line[:120], fill="#3f2a1d", font=text_font)
        y += line_height

    image.save(preview_path, "PNG")

    return f"/uploads/previews/{preview_filename}"


def create_pdf_preview_images(
    content: bytes,
    stored_stem: str,
) -> str | None:
    try:
        os.makedirs("uploads/previews", exist_ok=True)

        pages = convert_from_bytes(content, dpi=130)

        preview_urls = []

        for index, page in enumerate(pages):
            preview_filename = f"{stored_stem}_{index + 1}.png"
            preview_path = os.path.join("uploads", "previews", preview_filename)

            page.thumbnail((1200, 1600))
            page.save(preview_path, "PNG")

            preview_urls.append(f"/uploads/previews/{preview_filename}")

        if not preview_urls:
            return None

        return ",".join(preview_urls)

    except Exception as exc:
        print(f"Errore creazione preview PDF: {exc}")
        return None

def parse_amount(value: str) -> Decimal:
    cleaned = value.strip().replace(".", "").replace(",", ".")
    return Decimal(cleaned)

def ocr_image(image: Image.Image) -> str:
    image = image.convert("L")

    width, height = image.size

    left_margin = int(width * 0.18)
    right_margin = int(width * 0.92)
    top_margin = int(height * 0.02)
    bottom_margin = int(height * 0.98)

    image = image.crop((left_margin, top_margin, right_margin, bottom_margin))

    width, height = image.size
    image = image.resize((width * 2, height * 2))

    config = "--psm 4"

    return pytesseract.image_to_string(
        image,
        lang="ita",
        config=config,
    )


def extract_text_from_document(content: bytes, extension: str) -> str:
    if extension == "pdf":
        pages = convert_from_bytes(content, dpi=250)
        text_parts = []

        for page in pages:
            text_parts.append(ocr_image(page))

        return "\n".join(text_parts)

    if extension in {"jpg", "jpeg", "png", "webp"}:
        image = Image.open(BytesIO(content))
        return ocr_image(image)

    return content.decode("utf-8-sig", errors="replace")

def find_amount_after_label(text: str, label: str) -> Decimal | None:
    pattern = rf"{label}\s+(\d{{1,3}}(?:\.\d{{3}})*,\d{{2}}|\d+,\d{{2}})"
    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    return parse_amount(match.group(1))


def find_int_after_label(text: str, label: str) -> int | None:
    pattern = rf"{label}\s+(\d+)"
    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    return int(match.group(1))


def extract_daily_cash_closure(content: bytes, extension: str) -> dict:
    text = extract_text_from_document(content, extension)

    print("TESTO OCR CHIUSURA CASSA:")
    print(text)

    date = dt.date.today()

    date_match = re.search(
        r"(?:DEL GIORNO:|DATA)?\s*(\d{2})[-/](\d{2})[-/](\d{2,4})",
        text,
        re.IGNORECASE,
    )

    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3))

        if year < 100:
            year += 2000

        date = dt.date(year, month, day)

    closure_number_match = re.search(
        r"(?:NUM\.\s*CHIUSURA|CHIUSURA\s*N\.?)\s*[:\-]?\s*(\d+)",
        text,
        re.IGNORECASE,
    )

    total_amount = (
        find_amount_after_label(text, r"AMMONTARE\s+GIORNO")
        or find_amount_after_label(text, r"CORRISP\.\s+GIORNALIERO")
        or Decimal("0.00")
    )

    card_amount = (
        find_amount_after_label(text, r"PAGAM\.\s+ELETTRONICI")
        or Decimal("0.00")
    )

    cash_amount = (
        find_amount_after_label(text, r"AMMONTARE")
        or Decimal("0.00")
    )

    receipts_count = find_int_after_label(text, r"DOCUM\.\s+DI\s+VENDITA")

    return {
        "date": date,
        "closure_number": closure_number_match.group(1) if closure_number_match else None,
        "total_amount": total_amount,
        "cash_amount": cash_amount,
        "card_amount": card_amount,
        "receipts_count": receipts_count,
    }

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    month: str = Form(...),
    section: str = Form("other"),
    db: Session = Depends(get_db),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    if not month:
        raise HTTPException(status_code=400, detail="month is required")

    content = await file.read()
    print("UPLOAD SECTION:", section)
    print("UPLOAD FILENAME:", file.filename)
    if not content:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    os.makedirs("uploads/documents", exist_ok=True)

    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    stored_filename = f"{uuid.uuid4()}.{extension}"
    stored_stem = stored_filename.rsplit(".", 1)[0]

    file_path = os.path.join("uploads", "documents", stored_filename)

    with open(file_path, "wb") as output:
        output.write(content)

    file_url = f"/uploads/documents/{stored_filename}"
    preview_url = file_url
    generated_preview_url = None

    if extension == "pdf":
        generated_preview_url = create_pdf_preview_images(
            content=content,
            stored_stem=stored_stem,
        )

    elif extension in {"csv", "txt"}:
        generated_preview_url = create_text_preview_image(
            original_filename=file.filename,
            content=content,
            extension=extension,
            stored_stem=stored_stem,
        )

    if generated_preview_url:
        preview_url = generated_preview_url

    category, result = classify_document(file.filename)

    document = Document(
        month=month,
        original_filename=file.filename,
        stored_filename=stored_filename,
        document_type=extension.upper(),
        category=category,
        result=result,
        file_url=file_url,
        preview_url=preview_url,
        status="Elaborato",
        section=section,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    if section in {"cash", "cash_closure"}:
        print("ENTRATO IN CASH CLOSURE")
        extracted_data = extract_daily_cash_closure(content, extension)

        cash_closure = DailyCashClosure(
            date=extracted_data["date"],
            closure_number=extracted_data["closure_number"],
            total_amount=extracted_data["total_amount"],
            cash_amount=extracted_data["cash_amount"],
            card_amount=extracted_data["card_amount"],
            receipts_count=extracted_data["receipts_count"],
            document_id=document.id,
        )

        db.add(cash_closure)
        db.commit()

    return document_to_dict(document)


@router.get("")
def list_documents(
    month: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Document)

    if month:
        query = query.where(Document.month == month)

    documents = db.scalars(query.order_by(Document.created_at.desc())).all()
    return [document_to_dict(document) for document in documents]


@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    document = db.get(Document, document_id)

    if not document:
        raise HTTPException(status_code=404, detail="document not found")

    file_path = document.file_url.lstrip("/") if document.file_url else None
    preview_urls = document.preview_url.split(",") if document.preview_url else []

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    for preview_url in preview_urls:
        preview_path = preview_url.lstrip("/")

        if preview_path != file_path and os.path.exists(preview_path):
            os.remove(preview_path)

    cash_closures = db.scalars(
        select(DailyCashClosure).where(DailyCashClosure.document_id == document.id)
    ).all()

    for cash_closure in cash_closures:
        db.delete(cash_closure)

    db.delete(document)
    db.commit()

    return {"ok": True, "deleted_document_id": document_id}