import datetime as dt
import io
import re
import xml.etree.ElementTree as ET
from decimal import Decimal

import pytesseract
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice, InvoicePaymentLink, InvoiceStatus, Payment, PaymentMethod

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
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")

    text = str(value).strip()
    text = text.replace("€", "").replace("EUR", "").replace("eur", "")
    text = text.replace(".", "").replace(",", ".")
    text = re.sub(r"[^\d.\-]", "", text)

    try:
        return Decimal(text)
    except Exception:
        return Decimal("0")


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
    due_date = parse_optional_date(extracted.get("due_date")) or issue_date

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
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image, lang=lang)
    return clean_spaces(text)


def ocr_pdf_bytes(file_bytes: bytes, lang: str = "ita") -> str:
    pages = convert_from_bytes(file_bytes, dpi=220)
    texts = []

    for page in pages[:3]:
        texts.append(pytesseract.image_to_string(page, lang=lang))

    return clean_spaces("\n".join(texts))


def extract_field(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_spaces(match.group(1))
    return None


def extract_supplier_from_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        first = lines[0]
        if len(first) > 2:
            return clean_spaces(first)
    return "Sconosciuto"


def extract_invoice_from_text(text: str) -> dict:
    text = text.replace("\r", "\n")

    invoice_number = extract_field(
        [
            r"(?:fattura\s*n[°ºo\.]*\s*|numero\s*fattura\s*[:\-]?\s*)([A-Z0-9\/\-_]+)",
            r"(?:n[°ºo\.]*\s*fattura\s*[:\-]?\s*)([A-Z0-9\/\-_]+)",
        ],
        text,
    )

    issue_date = extract_field(
        [
            r"(?:data\s*fattura\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
            r"(?:data\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
        ],
        text,
    )

    due_date = extract_field(
        [
            r"(?:scadenza\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
            r"(?:data\s*scadenza\s*[:\-]?\s*)(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})",
        ],
        text,
    )

    total = extract_field(
        [
            r"(?:totale\s*documento\s*[:\-]?\s*)([\d\.,]+)",
            r"(?:totale\s*fattura\s*[:\-]?\s*)([\d\.,]+)",
            r"(?:totale\s*[:\-]?\s*)([\d\.,]+)",
        ],
        text,
    )

    vat = extract_field(
        [
            r"(?:iva\s*[:\-]?\s*)([\d\.,]+)",
            r"(?:imposta\s*[:\-]?\s*)([\d\.,]+)",
        ],
        text,
    )

    supplier = extract_supplier_from_text(text)

    return {
        "supplier": supplier,
        "invoice_number": invoice_number,
        "issue_date": issue_date,
        "due_date": due_date,
        "total": total or "0",
        "vat": vat or "0",
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
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "total": float(invoice.total),
        "vat": float(invoice.vat),
        "status": invoice.status.value,
    }


@router.post("/invoices/extract")
async def extract_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    filename = file.filename.lower()
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    try:
        if filename.endswith(".xml"):
            extracted = extract_invoice_from_xml(content)

        elif filename.endswith(".pdf"):
            text = ocr_pdf_bytes(content)
            extracted = extract_invoice_from_text(text)

        elif filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
            text = ocr_image_bytes(content)
            extracted = extract_invoice_from_text(text)

        else:
            raise HTTPException(
                status_code=400,
                detail="unsupported file format. Use pdf, jpg, jpeg, png, webp or xml",
            )

        normalized = normalize_extracted_invoice(extracted)

        invoice = Invoice(
            supplier=normalized["supplier"],
            invoice_number=normalized["invoice_number"],
            issue_date=normalized["issue_date"],
            due_date=normalized["due_date"],
            total=normalized["total"],
            vat=normalized["vat"],
            status=InvoiceStatus.pending,
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        return {
            "id": invoice.id,
            "supplier": invoice.supplier,
            "invoice_number": invoice.invoice_number,
            "issue_date": invoice.issue_date.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            "total": float(invoice.total),
            "vat": float(invoice.vat),
            "status": invoice.status.value,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"invoice extraction failed: {exc}") from exc


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
            "issue_date": row.issue_date.isoformat(),
            "due_date": row.due_date.isoformat(),
            "total": float(row.total),
            "vat": float(row.vat),
            "status": row.status.value,
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