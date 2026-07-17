import datetime as dt
import io
import re
import xml.etree.ElementTree as ET
import unicodedata
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


def normalize_lookup_text(value: str | None) -> str:
    text = clean_spaces(value or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def score_supplier_candidate(value: str | None) -> int:
    text = clean_spaces(value or "")
    if not is_valid_supplier_name(text):
        return -100

    norm = normalize_lookup_text(text)
    score = 0

    legal_tokens = ("srl", "spa", "s p a", "snc", "sas", "snc", "societa", "ditta")
    beverage_tokens = ("distribuzione", "bevande", "caffe", "torrefazione", "drink", "italiana")
    customer_tokens = ("cliente", "destinatario", "spett le", "committente", "cessionario")

    if any(token in norm for token in legal_tokens):
        score += 6
    if any(token in norm for token in beverage_tokens):
        score += 4
    if any(token in norm for token in customer_tokens):
        score -= 8

    if re.search(r"\d", text):
        score -= 1

    word_count = len(norm.split())
    if 2 <= word_count <= 6:
        score += 2

    return score


def collect_supplier_candidates(text: str) -> list[tuple[int, str]]:
    lines = [clean_spaces(line) for line in text.splitlines() if clean_spaces(line)]
    normalized_lines = [normalize_lookup_text(line) for line in lines]
    candidates: list[tuple[int, str]] = []

    label_boost_tokens = ("cedente prestatore", "fornitore", "emittente", "ragione sociale")
    hard_negative_tokens = (
        "cliente",
        "destinatario",
        "cessionario",
        "committente",
        "indirizzo",
        "partita iva",
        "codice fiscale",
        "iban",
        "scadenza",
        "totale",
        "iva",
        "fattura",
    )
    beverage_tokens = ("bevande", "distribuzione", "drink", "acqua", "birra", "vino")

    max_lines = min(len(lines), 120)
    for idx in range(max_lines):
        line = lines[idx]
        # Pulisci eventuali code OCR tipo "... S.R.L. FATTURA N. ..."
        line = re.sub(r"\bfattura\b.*$", "", line, flags=re.IGNORECASE).strip(" -:;,.\t")
        if not line:
            continue

        norm = normalize_lookup_text(line)
        if not norm:
            continue

        base_score = score_supplier_candidate(line)
        if base_score <= -100:
            continue

        score = base_score
        prev_norm = normalized_lines[idx - 1] if idx > 0 else ""
        next_norm = normalized_lines[idx + 1] if idx + 1 < len(normalized_lines) else ""

        if any(token in prev_norm for token in label_boost_tokens):
            score += 8
        if any(token in norm for token in beverage_tokens):
            score += 5
        if any(token in norm for token in hard_negative_tokens):
            score -= 9
        if any(token in next_norm for token in ("p iva", "partita iva", "rea", "pec")):
            score += 2

        # Linee troppo lunghe o rumorose tendono a essere descrizioni/indirizzi.
        if len(norm.split()) > 9:
            score -= 3

        candidates.append((score, line[:120]))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def canonicalize_supplier_name(value: str | None) -> str:
    raw = clean_spaces(value or "")
    if not raw:
        return "Sconosciuto"

    # Rimuove code di rumore OCR (es. "FATTURA", "N. 123") dal nome fornitore.
    cleaned = re.sub(r"\bfattura\b.*$", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bn[°ºo\.]?\s*[a-z0-9\/_\.\-]+$", "", cleaned, flags=re.IGNORECASE)
    cleaned = clean_spaces(cleaned).strip(" -:;,.\t")
    if cleaned:
        raw = cleaned

    norm = normalize_lookup_text(raw)

    # Normalizzazione dinamica per varianti OCR comuni sul fornitore bevande.
    if (
        ("distribuzione" in norm and "bevande" in norm)
        or (re.search(r"(?:^|\s)[a-z]?izione\s+bevande", norm) and "s r l" in norm)
        or ("bevande" in norm and "s r l" in norm and ("tribuzione" in norm or "izione" in norm))
    ):
        return "DISTRIBUZIONE BEVANDE S.R.L."

    # Canonicalizzazione dinamica per varianti OCR di "Torrefazione Italiana S.p.A."
    if (
        ("torrefazione" in norm and "italiana" in norm)
        or re.search(r"torrefa[a-z]*\s+italian[a-z]*", norm)
    ):
        return "TORREFAZIONE ITALIANA S.p.A."

    return raw


def infer_invoice_category(supplier: str | None, invoice_number: str | None = None) -> str:
    supplier_norm = normalize_lookup_text(supplier)
    invoice_norm = normalize_lookup_text(invoice_number)

    if supplier_norm == "cliente" and (invoice_norm.startswith("tc ") or invoice_norm.startswith("tc-")):
        return "Caffe"

    if any(token in supplier_norm for token in ("caff", "torrefazione", "vergnano", "espresso")):
        return "Caffe"

    if any(token in supplier_norm for token in ("bevande", "drink", "birra", "wine", "acqua", "coca", "pepsi", "sprite", "aperol", "campari", "distribuzione")):
        return "Bevande"

    if any(token in supplier_norm for token in ("latte", "lattiero")):
        return "Latticini"

    if any(token in supplier_norm for token in ("dolci", "pane", "pastic")):
        return "Pasticceria"

    if any(token in supplier_norm for token in ("serviz", "copywriter", "consul", "manutenz")):
        return "Servizi"

    if any(token in supplier_norm for token in ("utenz", "energia", "luce", "gas", "enel", "acquedotto")):
        return "Utenze"

    return "Altro"


def is_valid_supplier_name(value: str | None) -> bool:
    text = clean_spaces(value or "")
    if not text or len(text) < 3:
        return False

    norm = normalize_lookup_text(text)
    if norm in {"sconosciuto", "cliente", "fornitore", "n a", "na"}:
        return False

    # Evita di usare intestazioni tipiche del destinatario/cliente come fornitore.
    if any(token in norm for token in ("spett le", "destinatario", "cessionario", "committente")):
        return False

    if re.fullmatch(r"[0-9\s\-\/\.]+", text):
        return False

    return True


def normalize_invoice_number_value(value: str | None) -> str:
    raw = clean_spaces(value or "")
    if not raw:
        return ""

    compact = re.sub(r"\s+", "", raw.upper())
    compact = compact.replace("N.", "").replace("N°", "").replace("Nº", "")
    compact = compact.strip("-_/.:;")

    if re.search(r"\d+[\.,]\d{2}$", compact):
        return ""

    if re.fullmatch(r"\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}", compact):
        return ""

    if not re.fullmatch(r"[A-Z0-9\/_\.\-]{2,40}", compact):
        return ""

    if not re.search(r"\d", compact):
        return ""

    return compact


def extract_invoice_number_from_text(text: str) -> str | None:
    lines = [clean_spaces(line) for line in text.splitlines() if clean_spaces(line)]

    line_patterns = [
        r"(?:numero\s+fattura|fattura\s*n[°ºo\.]?|n[°ºo\.]?\s*fattura|nr\.?\s*fattura|numero\s+documento|doc(?:umento)?\s*n(?:umero)?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\s\/_\.\-]{1,30})",
        r"\bfattura\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\s\/_\.\-]{1,30})",
    ]

    for raw_line in lines:
        upper_line = raw_line.upper()
        for pattern in line_patterns:
            match = re.search(pattern, upper_line, flags=re.IGNORECASE)
            if not match:
                continue

            normalized = normalize_invoice_number_value(match.group(1))
            if normalized:
                return normalized

    generic_patterns = [
        r"\b[A-Z]{1,4}[\/_\-]\d{2,10}\b",
        r"\b\d{2,10}[\/_\-][A-Z0-9]{1,8}\b",
        r"\b\d{5,12}\b",
    ]

    for pattern in generic_patterns:
        for token in re.findall(pattern, text.upper()):
            normalized = normalize_invoice_number_value(token)
            if normalized:
                return normalized

    return None


def merge_extracted_invoice(
    ai_extracted: dict | None,
    heuristic_extracted: dict,
    source_text: str | None = None,
) -> dict:
    ai = ai_extracted or {}
    heuristic = heuristic_extracted or {}

    ai_supplier = clean_spaces(ai.get("supplier", ""))
    heuristic_supplier = clean_spaces(heuristic.get("supplier", ""))

    ai_score = score_supplier_candidate(ai_supplier)
    heuristic_score = score_supplier_candidate(heuristic_supplier)

    supplier = ai_supplier if ai_score >= heuristic_score else heuristic_supplier
    supplier_score = max(ai_score, heuristic_score)

    if source_text:
        text_candidates = collect_supplier_candidates(source_text)
        if text_candidates:
            text_score, text_supplier = text_candidates[0]
            # Preferisci il candidato OCR se e' significativamente migliore.
            if text_score >= supplier_score + 2:
                supplier = text_supplier
                supplier_score = text_score

    if not is_valid_supplier_name(supplier):
        supplier = "Sconosciuto"

    supplier = canonicalize_supplier_name(supplier)

    ai_number = normalize_invoice_number_value(ai.get("invoice_number", ""))
    heuristic_number = normalize_invoice_number_value(heuristic.get("invoice_number", ""))
    invoice_number = ai_number or heuristic_number

    if not invoice_number and source_text:
        invoice_number = extract_invoice_number_from_text(source_text) or ""

    issue_date = ai.get("issue_date") or heuristic.get("issue_date")
    due_date = ai.get("due_date") or heuristic.get("due_date")
    delivery_date = heuristic.get("delivery_date")

    ai_total = parse_decimal(ai.get("total"))
    heuristic_total = parse_decimal(heuristic.get("total"))
    total = str(ai_total if is_reasonable_money(ai_total) else heuristic_total)

    ai_vat = parse_decimal(ai.get("vat"))
    heuristic_vat = parse_decimal(heuristic.get("vat"))
    vat = str(ai_vat if Decimal("0") <= ai_vat <= parse_decimal(total) else heuristic_vat)

    return {
        "supplier": supplier,
        "invoice_number": invoice_number,
        "issue_date": issue_date,
        "due_date": due_date,
        "delivery_date": delivery_date,
        "total": total,
        "vat": vat,
    }

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

    if not is_valid_supplier_name(candidate):
        return "Sconosciuto"

    return candidate or "Sconosciuto"


def normalize_extracted_invoice(extracted: dict) -> dict:
    supplier = canonicalize_supplier_name(pick_reasonable_supplier(extracted.get("supplier")))

    invoice_number = normalize_invoice_number_value(extracted.get("invoice_number"))
    if not invoice_number:
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

    def xml_text(paths: list[str]) -> str | None:
        for path in paths:
            el = root.find(path)
            if el is not None and el.text and clean_spaces(el.text):
                return clean_spaces(el.text)
        return None

    supplier = xml_text([
        ".//{*}CedentePrestatore/{*}DatiAnagrafici/{*}Anagrafica/{*}Denominazione",
        ".//{*}CedentePrestatore/{*}DatiAnagrafici/{*}Anagrafica/{*}Nome",
        ".//{*}CedentePrestatore/{*}DatiAnagrafici/{*}Anagrafica/{*}Cognome",
    ])

    # Fallback estremo: qualsiasi Denominazione, ma solo se valida.
    if not is_valid_supplier_name(supplier):
        generic_name = xml_text([
            ".//{*}Denominazione",
            ".//{*}Nome",
        ])
        supplier = generic_name if is_valid_supplier_name(generic_name) else "Sconosciuto"

    invoice_number = xml_text([
        ".//{*}DatiGeneraliDocumento/{*}Numero",
        ".//{*}Numero",
    ])
    issue_date = xml_text([
        ".//{*}DatiGeneraliDocumento/{*}Data",
        ".//{*}Data",
    ])
    total = xml_text([
        ".//{*}DatiGeneraliDocumento/{*}ImportoTotaleDocumento",
        ".//{*}ImportoTotaleDocumento",
    ])
    vat = xml_text([
        ".//{*}DatiRiepilogo/{*}Imposta",
        ".//{*}Imposta",
    ])
    due_date = xml_text([
        ".//{*}DettaglioPagamento/{*}DataScadenzaPagamento",
        ".//{*}DataScadenzaPagamento",
    ])

    return {
        "supplier": supplier or "Sconosciuto",
        "invoice_number": invoice_number or "",
        "issue_date": issue_date,
        "due_date": due_date,
        "total": total or "0",
        "vat": vat or "0",
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

    for line in lines[:25]:
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
        "cliente",
        "destinatario",
        "indirizzo",
        "partita iva",
        "codice fiscale",
        "iban",
    ]

    filtered_text = "\n".join(
        line for line in lines if not any(word in line.lower() for word in blacklist)
    )
    scored_lines = collect_supplier_candidates(filtered_text)

    if scored_lines:
        best = scored_lines[0][1]
        if is_valid_supplier_name(best):
            return best

    return "Sconosciuto"

def extract_invoice_from_text(text: str) -> dict:
    text = text.replace("\r", "\n")

    normalized_text = text.replace("\r", "\n")
    normalized_text = re.sub(r"[ \t]+", " ", normalized_text)
    normalized_text = re.sub(r"\n+", "\n", normalized_text)

    supplier = extract_supplier_from_text(text)

    invoice_number = extract_invoice_number_from_text(normalized_text)

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
        "category": infer_invoice_category(invoice.supplier, invoice.invoice_number),
        "status": invoice.status.value,
        "file_url": invoice.file_url,

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
            heuristic_extracted = extract_invoice_from_text(text)
            ai_parsed = parse_invoice_with_llm(text)
            extracted = merge_extracted_invoice(ai_parsed, heuristic_extracted, text)

        elif filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")):
            text = ocr_image_bytes(content)
            heuristic_extracted = extract_invoice_from_text(text)
            ai_parsed = parse_invoice_with_llm(text)
            extracted = merge_extracted_invoice(ai_parsed, heuristic_extracted, text)

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
                "category": infer_invoice_category(existing_invoice.supplier, existing_invoice.invoice_number),
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
            "category": infer_invoice_category(invoice.supplier, invoice.invoice_number),
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
            "category": infer_invoice_category(row.supplier, row.invoice_number),
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