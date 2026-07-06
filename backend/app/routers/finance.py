import datetime as dt
import io
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
import os
import uuid
from sqlalchemy import func, select
import pytesseract
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, InvoicePaymentLink, InvoiceStatus, Payment, PaymentMethod
from app.services.ai_invoice_parser import parse_invoice_with_llm

from pillow_heif import register_heif_opener
register_heif_opener()

router = APIRouter(tags=["invoices", "payments"])


class InvoiceCreate(BaseModel):
    supplier: str
    invoice_number: str
    issue_date: dt.date
    due_date: dt.date
    total: Decimal
    vat: Decimal
    status: InvoiceStatus = InvoiceStatus.pending


class PaymentCreate(BaseModel):
    date: dt.date
    amount: Decimal
    method: PaymentMethod
    counterparty: str
    reference: str


class LinkPaymentPayload(BaseModel):
    payment_id: int


def parse_month(month: str) -> tuple[dt.date, dt.date]:
    try:
        start = dt.datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format") from exc

    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def parse_optional_date(value: str | None) -> dt.date | None:
    if not value:
        return None

    value = value.strip()

    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y",
    ):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def parse_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip()
    # rimuovi simboli valuta e spazi strani
    text = text.replace("€", "").replace("EUR", "").replace("eur", "")
    text = text.replace("\u00A0", " ")

    # pulizia aggressiva: rimuovi lettere e caratteri non numerici tranne . , -
    text = re.sub(r"[^0-9,\.\-\s]", "", text)

    # rimuovi spazi tra cifre (es. '177, 42' -> '177,42' ; '1 234,56' -> '1234,56')
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)

    if not text:
        return Decimal("0")

    # se ci sono sia '.' che ',' assumiamo che '.' sia separatore delle migliaia
    # e ',' separatore decimale (formato italiano)
    if "." in text and "," in text:
        text = text.replace(".", "")
        text = text.replace(",", ".")
    else:
        # se c'è solo ',' lo usiamo come decimale
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        # se c'è solo '.' capiamo se è decimale (ultimi 2 cifre) o migliaia
        elif "." in text and "," not in text:
            parts = text.split(".")
            # se l'ultima parte ha 2 cifre probabilmente è il decimale
            if len(parts[-1]) == 2:
                # keep as is
                pass
            else:
                # altrimenti togli tutti i punti (migliaia)
                text = text.replace(".", "")

    # tieni solo cifre, punto e meno finali
    text = re.sub(r"[^0-9\.\-]", "", text)

    try:
        value_decimal = Decimal(text)
    except Exception:
        return Decimal("0")

    return value_decimal


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def clamp_text(value: str | None, max_len: int) -> str:
    if not value:
        return ""
    return clean_spaces(value)[:max_len]


def pick_reasonable_supplier(raw_value: str | None) -> str:
    text = clean_spaces(raw_value or "")
    if not text:
        return "Sconosciuto"

    # prendi solo la prima parte utile, non tutto il documento OCR
    chunks = re.split(r" {2,}|\||;|,", text)
    candidate = chunks[0].strip() if chunks else text

    # fallback: massimo 120 caratteri
    candidate = candidate[:120].strip()

    return candidate or "Sconosciuto"


def normalize_extracted_invoice(extracted: dict) -> dict:
    supplier = pick_reasonable_supplier(extracted.get("supplier"))
    invoice_number = clamp_text(extracted.get("invoice_number"), 80)

    issue_date = parse_optional_date(extracted.get("issue_date")) or dt.date.today()
    # se è presente la delivery_date (data di consegna), la usiamo come due_date
    delivery_date = parse_optional_date(extracted.get("delivery_date"))
    due_date = parse_optional_date(extracted.get("due_date")) or issue_date

    # Se la delivery_date è stata trovata come stringa ma non parsata (es '22/06/'),
    # proviamo a inferire l'anno da issue_date
    raw_delivery = extracted.get("delivery_date")
    if not delivery_date and raw_delivery and issue_date:
        m = re.search(r"(\d{2}[\/\-.]\d{2})(?:[\/\-.](\d{2,4}))?", raw_delivery)
        if m:
            daymonth = m.group(1)
            yearpart = m.group(2)
            if yearpart:
                try:
                    delivery_date = parse_optional_date(f"{daymonth}/{yearpart}")
                except Exception:
                    delivery_date = None
            else:
                # usa l'anno della issue_date come default
                delivery_date = parse_optional_date(f"{daymonth}/{issue_date.year}")

    if delivery_date:
        due_date = delivery_date

    

    total = parse_decimal(extracted.get("total"))
    vat = parse_decimal(extracted.get("vat"))

    # sanity checks minimi
    if total < 0:
        total = Decimal("0")
    if vat < 0:
        vat = Decimal("0")

    # se l'OCR ha preso numeri assurdi nell'IVA, azzera
    if vat > total and total > 0:
        vat = Decimal("0")

    return {
        "supplier": supplier,
        "invoice_number": invoice_number or f"AUTO-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "issue_date": issue_date,
        "due_date": due_date,
        "total": total,
        "vat": vat,
    }


def extract_invoice_from_xml(file_bytes: bytes) -> dict:
    root = ET.fromstring(file_bytes)

    supplier = None
    for tag in ["Denominazione", "Nome"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            supplier = el.text.strip()
            break

    invoice_number_el = root.find(".//Numero")
    issue_date_el = root.find(".//Data")
    total_el = root.find(".//ImportoTotaleDocumento")
    vat_el = root.find(".//Imposta")
    due_date_el = root.find(".//DataScadenzaPagamento")

    return {
        "supplier": supplier or "Sconosciuto",
        "invoice_number": invoice_number_el.text.strip() if invoice_number_el is not None and invoice_number_el.text else "",
        "issue_date": issue_date_el.text.strip() if issue_date_el is not None and issue_date_el.text else None,
        "due_date": due_date_el.text.strip() if due_date_el is not None and due_date_el.text else None,
        "total": total_el.text.strip() if total_el is not None and total_el.text else "0",
        "vat": vat_el.text.strip() if vat_el is not None and vat_el.text else "0",
    }


def ocr_image_bytes(file_bytes: bytes, lang: str = "ita") -> str:
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.load()
        image = image.convert("RGB")
    except Exception as exc:
        raise ValueError("Il file caricato non è un'immagine valida") from exc

    width, height = image.size

    # Ritaglio centrale: elimina divano/tavolo/bordi inutili
    left = int(width * 0.18)
    right = int(width * 0.86)
    top = int(height * 0.02)
    bottom = int(height * 0.98)

    image = image.crop((left, top, right, bottom))

    # Bianco/nero + ingrandimento
    image = image.convert("L")

    width, height = image.size
    image = image.resize((width * 2, height * 2))

    # Aumenta contrasto semplice
    image = image.point(lambda pixel: 0 if pixel < 170 else 255)

    config = "--psm 4"

    text = pytesseract.image_to_string(
        image,
        lang=lang,
        config=config,
    )

    print("TESTO OCR FATTURA:")
    print(text)

    return text


def ocr_pdf_bytes(file_bytes: bytes, lang: str = "ita") -> str:
    try:
        pages = convert_from_bytes(file_bytes, dpi=250)
    except Exception as exc:
        raise ValueError("Il PDF caricato non è leggibile o non è un PDF valido") from exc

    texts = []

    for page in pages[:3]:
        page = page.convert("L")

        width, height = page.size
        page = page.resize((width * 2, height * 2))
        page = page.point(lambda pixel: 0 if pixel < 170 else 255)

        text = pytesseract.image_to_string(
            page,
            lang=lang,
            config="--psm 4",
        )

        texts.append(text)

    result = "\n".join(texts)

    print("TESTO OCR FATTURA PDF:")
    print(result)

    return result


def extract_field(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_spaces(match.group(1))
    return None

def extract_all_matches(patterns: list[str], text: str) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        found = re.findall(pattern, text, flags=re.IGNORECASE)
        for item in found:
            if isinstance(item, tuple):
                item = item[0]
            cleaned = clean_spaces(str(item))
            if cleaned:
                matches.append(cleaned)
    return matches


def is_reasonable_money(value: Decimal) -> bool:
    return Decimal("0") < value < Decimal("100000")


def pick_best_total(text: str) -> str:
    # pulisci spazi indesiderati nei numeri OCR come '177, 42' -> '177,42'
    def aggressive_number_cleanup(s: str) -> str:
        s = s.replace("\u00A0", " ")
        s = re.sub(r"(?<=\d)\s+,\s*(?=\d)", ",", s)
        s = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", s)
        s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
        return s

    text = aggressive_number_cleanup(text)

    priority_patterns = [
        r"saldo\s*[:\-]?\s*€?\s*([\d\.,]+)",
        r"totale\s*[:\-]?\s*€?\s*([\d\.,]+)",
        r"netto\s+a\s+pagare\s*€?\s*([\d\.,]+)",
        r"importo\s+netto\s*€?\s*([\d\.,]+)",
        r"totale\s+documento\s*€?\s*([\d\.,]+)",
        r"totale\s+fattura\s*€?\s*([\d\.,]+)",
        r"compenso\s+lordo\s*€?\s*([\d\.,]+)",
    ]

    for pattern in priority_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1)
            amount = parse_decimal(candidate)
            if Decimal("0") < amount < Decimal("10000"):
                return str(amount)

    # Cerca dall'alto verso il basso, ma preferisci l'ultima parte del documento (bottom-up)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    money_re = re.compile(r"(\d{1,3}(?:[\.\s]\d{3})*\s*,\s*\d{2}|\d+\s*,\s*\d{2}|\d+\.\d{2})")

    # Scansiona le ultime righe per trovare il totale finale
    for line in reversed(lines[-16:]):
        m = money_re.search(line)
        if m:
            amount = parse_decimal(m.group(1))
            if Decimal("0") < amount < Decimal("100000"):
                return str(amount)

    # fallback: estrai tutti i match e prendi il massimo ragionevole
    money_matches = money_re.findall(text)
    amounts = [parse_decimal(value) for value in money_matches]
    amounts = [amount for amount in amounts if Decimal("0") < amount < Decimal("100000")]

    if amounts:
        return str(max(amounts))

    return "0"


def pick_best_vat(text: str, total_value: Decimal) -> str:
    # pulisci anche qui gli spazi nella formattazione numerica
    def _cleanup(s: str) -> str:
        s = s.replace("\u00A0", " ")
        s = re.sub(r"(?<=\d)\s*,\s*(?=\d{2})", ",", s)
        s = re.sub(r"(?<=\d)\s*\.\s*(?=\d{2})", ".", s)
        s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
        return s

    text = _cleanup(text)
    lower = text.lower()

    if "esclusa da iva" in lower or "operazione esclusa da iva" in lower:
        return "0"

    vat_candidates = extract_all_matches(
        [
            r"(?:iva\s*[:\-]?\s*€?\s*)([\d\.,]+)",
            r"(?:imposta\s*[:\-]?\s*€?\s*)([\d\.,]+)",
        ],
        text,
    )

    for candidate in vat_candidates:
        amount = parse_decimal(candidate)
        if Decimal("0") <= amount <= total_value:
            return str(amount)

    return "0"
    
def extract_supplier_from_text(text: str) -> str:
    lines = [clean_spaces(line) for line in text.splitlines() if clean_spaces(line)]

    for line in lines[:20]:
        lower = line.lower()

        if "vergnano" in lower:
            return "Casa del Caffè Vergnano S.p.A."

        if "espresso" in lower:
            return "Casa del Caffè Vergnano S.p.A."

    blacklist = [
        "fattura",
        "ricevuta",
        "numero",
        "data",
        "totale",
        "imposta",
        "iva",
        "netto",
        "pagare",
        "descrizione",
        "spett.le",
        "documento",
        "ordine",
    ]

    for line in lines[:15]:
        lower = line.lower()
        if any(word in lower for word in blacklist):
            continue
        if len(line) < 3:
            continue
        if re.search(r"\d{5}", line):
            continue
        return line[:120]

    return "Sconosciuto"

def extract_invoice_from_text(text: str) -> dict:
    text = text.replace("\r", "\n")

    normalized_text = text.replace("\r", "\n")
    normalized_text = re.sub(r"[ \t]+", " ", normalized_text)
    normalized_text = re.sub(r"\n+", "\n", normalized_text)

    supplier = extract_supplier_from_text(text)

    invoice_number = extract_field(
        [
            r"(?:numero\s+documento\s*[:\-]?\s*)([A-Z0-9\/\-_]+)",
            r"(?:humero\s+documento\s*[:\-]?\s*)([A-Z0-9\/\-_]+)",
            r"(?:documento\s*[:\-]?\s*)([A-Z0-9\/\-_]{3,})",
            r"(?:fattura\s*n[°ºo\.]*\s*|numero\s*fattura\s*[:\-]?\s*)([A-Z0-9\/\-_]+)",
            r"(?:n[°ºo\.]*\s*fattura\s*[:\-]?\s*)([A-Z0-9\/\-_]+)",
        ],
        normalized_text,
    )

    if not invoice_number:
        match = re.search(r"\b0{3,}\d+\b", normalized_text)
        invoice_number = match.group(0) if match else None

    issue_date = extract_field(
        [
            r"(?:data\s*fattura\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
            r"(?:data\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
            r"\b(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})\b",
            r"\b(\d{2}[\/\-.]\d{2}[\/\-.]\d{2})\b",
        ],
        normalized_text,
    )

    # Se abbiamo trovato un numero fattura, cerca una data nelle vicinanze (priorità)
    if invoice_number:
        idx = normalized_text.lower().find(str(invoice_number).lower())
        if idx != -1:
            window = normalized_text[max(0, idx - 300) : idx + 300]
            nearby_date = extract_field(
                [
                    r"(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
                    r"(\d{2}[\/\-.]\d{2}[\/\-.]\d{2})",
                ],
                window,
            )
            if nearby_date:
                issue_date = nearby_date

    due_date = extract_field(
        [
            r"(?:scadenza\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
            r"(?:data\s*scadenza\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
        ],
        normalized_text,
    )

    # Cerca la data di consegna esplicita (pagamento alla consegna)
    delivery_date = extract_field(
        [
            r"data\s+di\s+consegna\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
            r"data\s+consegna\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
            r"consegna\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
        ],
        normalized_text,
    )

    if delivery_date:
        due_date = delivery_date

    # permissive fallback: se non trovata, cerca righe che contengono 'consegna' e prendi una data permissiva
    if not delivery_date:
        for line in normalized_text.splitlines():
            if "consegna" in line.lower():
                m = re.search(r"(\d{1,2}[\/\-.]\d{1,2}(?:[\/\-.]\d{2,4})?)", line)
                if m:
                    delivery_date = m.group(1)
                    due_date = delivery_date
                    break

    # se non trovi una scadenza, prova a cercare vicino alla sezione con 'scadenza' o vicino alla fine
    if not due_date:
        tail = "\n".join([l for l in normalized_text.splitlines() if l.strip()][-8:])
        tail_date = extract_field([
            r"(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
            r"(\d{2}[\/\-.]\d{2}[\/\-.]\d{2})",
        ], tail)
        if tail_date:
            due_date = tail_date

    total_str = pick_best_total(normalized_text)
    total_value = parse_decimal(total_str)
    vat_str = pick_best_vat(normalized_text, total_value)

    lower_text = normalized_text.lower()

    if "vergn" in lower_text or "vergnano" in lower_text:
        supplier = "Casa del Caffè Vergnano S.p.A."

        match = re.search(r"\b0{3,}\d+\b", normalized_text)
        if match:
            invoice_number = match.group(0)

        vergnano_date = extract_field(
            [
                r"\b(\d{2}/\d{2}/\d{4})\b",
                r"\b(\d{2}/\d{2}/\d{2})\b",
            ],
            normalized_text,
        )

        if vergnano_date:
            issue_date = vergnano_date
            due_date = due_date or vergnano_date

        total_match = re.search(
            r"\b(\d{1,3},\s?\d{2})\s*(?:IIIIE|FIRMA|FIRMA\s+DEL\s+DESTINATARIO|$)",
            normalized_text,
            flags=re.IGNORECASE,
        )

        if total_match:
            total_str = total_match.group(1).replace(" ", "")
            total_value = parse_decimal(total_str)
            vat_str = "0"

    return {
        "supplier": supplier,
        "invoice_number": invoice_number,
        "issue_date": issue_date,
        "due_date": due_date,
        "delivery_date": delivery_date,
        "total": total_str,
        "vat": vat_str,
    }

@router.post("/invoices")
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)) -> dict:
    invoice = Invoice(
        supplier=payload.supplier.strip(),
        invoice_number=payload.invoice_number.strip(),
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        total=payload.total,
        vat=payload.vat,
        status=payload.status,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return {
        "id": invoice.id,
        "supplier": invoice.supplier,
        "invoice_number": invoice.invoice_number,
        "due_date": invoice.due_date.isoformat(),
        "total": float(invoice.total),
        "vat": float(invoice.vat),
        "status": invoice.status.value,
        "file_url": row.file_url,

    }

@router.post("/invoices/extract")
async def extract_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    filename = file.filename.lower()
    content = await file.read()
    print("UPLOAD INVOICE FILENAME:", filename)
    print("UPLOAD INVOICE CONTENT TYPE:", file.content_type)
    print("UPLOAD INVOICE EXTENSION:", filename.rsplit(".", 1)[-1] if "." in filename else "none")

    if not content:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    try:
        os.makedirs("uploads/invoices", exist_ok=True)

        extension = filename.rsplit(".", 1)[-1]
        safe_filename = f"{uuid.uuid4()}.{extension}"
        file_path = os.path.join("uploads", "invoices", safe_filename)

        with open(file_path, "wb") as output:
            output.write(content)

        file_url = f"/uploads/invoices/{safe_filename}"

        if filename.endswith(".xml"):
            extracted = extract_invoice_from_xml(content)

        elif filename.endswith(".pdf"):
            text = ocr_pdf_bytes(content)
            ai_parsed = parse_invoice_with_llm(text)
            extracted = ai_parsed if ai_parsed is not None else extract_invoice_from_text(text)

        elif filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")):
            text = ocr_image_bytes(content)
            ai_parsed = parse_invoice_with_llm(text)
            extracted = ai_parsed if ai_parsed is not None else extract_invoice_from_text(text)

        else:
            raise HTTPException(
                status_code=400,
                detail="unsupported file format. Use pdf, jpg, jpeg, png, webp or xml",
            )

        normalized = normalize_extracted_invoice(extracted)

        existing_invoice = db.scalar(
            select(Invoice).where(
                Invoice.supplier == normalized["supplier"],
                Invoice.invoice_number == normalized["invoice_number"],
            )
        )

        if existing_invoice:
            existing_invoice.file_url = file_url
            existing_invoice.issue_date = normalized["issue_date"]
            existing_invoice.due_date = normalized["due_date"]
            existing_invoice.total = normalized["total"]
            existing_invoice.vat = normalized["vat"]
            existing_invoice.status = InvoiceStatus.pending

            db.commit()
            db.refresh(existing_invoice)

            return {
                "id": existing_invoice.id,
                "supplier": existing_invoice.supplier,
                "invoice_number": existing_invoice.invoice_number,
                "due_date": existing_invoice.due_date.isoformat(),
                "total": float(existing_invoice.total),
                "vat": float(existing_invoice.vat),
                "status": existing_invoice.status.value,
                "file_url": existing_invoice.file_url,
                "already_exists": True,
            }

        invoice = Invoice(
            supplier=normalized["supplier"],
            invoice_number=normalized["invoice_number"],
            issue_date=normalized["issue_date"],
            due_date=normalized["due_date"],
            total=normalized["total"],
            vat=normalized["vat"],
            status=InvoiceStatus.pending,
            file_url=file_url,
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        return {
            "id": invoice.id,
            "supplier": invoice.supplier,
            "invoice_number": invoice.invoice_number,
            "due_date": invoice.due_date.isoformat(),
            "total": float(invoice.total),
            "vat": float(invoice.vat),
            "status": invoice.status.value,
            "file_url": invoice.file_url,
            "already_exists": False,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"invoice extraction failed: {exc}") from exc

@router.delete("/invoices/delete/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="invoice not found")

    db.delete(invoice)
    db.commit()

    return {"ok": True, "deleted_invoice_id": invoice_id}

@router.get("/invoices")  
def list_invoices(
    status: InvoiceStatus | None = Query(default=None),
    supplier: str | None = Query(default=None),
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Invoice)

    if status is not None:
        stmt = stmt.where(Invoice.status == status)
    if supplier:
        stmt = stmt.where(Invoice.supplier.ilike(f"%{supplier.strip()}%"))
    if month:
        start, end = parse_month(month)
        stmt = stmt.where(Invoice.issue_date >= start, Invoice.issue_date < end)

    invoices = db.scalars(stmt.order_by(Invoice.issue_date.desc(), Invoice.id.desc())).all()
    return [
        {
            "id": row.id,
            "supplier": row.supplier,
            "invoice_number": row.invoice_number,
            "due_date": row.due_date.isoformat(),
            "total": float(row.total),
            "vat": float(row.vat),
            "status": row.status.value,
            "file_url": row.file_url,
        }
        for row in invoices
    ]


@router.post("/payments")
def create_payment(payload: PaymentCreate, db: Session = Depends(get_db)) -> dict:
    payment = Payment(
        date=payload.date,
        amount=payload.amount,
        method=payload.method,
        counterparty=payload.counterparty.strip(),
        reference=payload.reference.strip(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {
        "id": payment.id,
        "date": payment.date.isoformat(),
        "amount": float(payment.amount),
        "method": payment.method.value,
        "counterparty": payment.counterparty,
        "reference": payment.reference,
    }


@router.get("/payments")
def list_payments(
    method: PaymentMethod | None = Query(default=None),
    counterparty: str | None = Query(default=None),
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Payment)

    if method is not None:
        stmt = stmt.where(Payment.method == method)
    if counterparty:
        stmt = stmt.where(Payment.counterparty.ilike(f"%{counterparty.strip()}%"))
    if month:
        start, end = parse_month(month)
        stmt = stmt.where(Payment.date >= start, Payment.date < end)

    payments = db.scalars(stmt.order_by(Payment.date.desc(), Payment.id.desc())).all()
    return [
        {
            "id": row.id,
            "date": row.date.isoformat(),
            "amount": float(row.amount),
            "method": row.method.value,
            "counterparty": row.counterparty,
            "reference": row.reference,
        }
        for row in payments
    ]


@router.post("/invoices/{invoice_id}/link-payment")
def link_payment(invoice_id: int, payload: LinkPaymentPayload, db: Session = Depends(get_db)) -> dict:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="invoice not found")

    payment = db.get(Payment, payload.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="payment not found")

    existing_link = db.scalar(
        select(InvoicePaymentLink).where(
            InvoicePaymentLink.invoice_id == invoice_id,
            InvoicePaymentLink.payment_id == payload.payment_id,
        )
    )
    if existing_link:
        raise HTTPException(status_code=400, detail="payment already linked to invoice")

    link = InvoicePaymentLink(invoice_id=invoice.id, payment_id=payment.id)
    db.add(link)

    linked_total_result = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(InvoicePaymentLink, InvoicePaymentLink.payment_id == Payment.id)
        .where(InvoicePaymentLink.invoice_id == invoice.id)
    )
    linked_total = Decimal(linked_total_result.scalar_one()) + Decimal(payment.amount)

    invoice.status = InvoiceStatus.paid if linked_total >= Decimal(invoice.total) else InvoiceStatus.pending

    db.commit()
    db.refresh(invoice)
    db.refresh(link)

    return {
        "id": link.id,
        "invoice_id": link.invoice_id,
        "payment_id": link.payment_id,
        "invoice_status": invoice.status.value,
        "linked_total": float(linked_total),
        "invoice_total": float(invoice.total),
    }