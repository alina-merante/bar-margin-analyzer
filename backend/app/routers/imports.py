import csv
import datetime as dt
import os
import re
from decimal import Decimal
from io import StringIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CategoryRule, Document, Product, SaleLine, Transaction
from app.routers.documents import create_bank_document

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/pos-csv")
def import_pos_csv(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, int]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(StringIO(content))
    expected_fields = {"date", "product", "qty", "total"}

    if not reader.fieldnames or set(reader.fieldnames) != expected_fields:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain exactly these headers: date, product, qty, total",
        )

    imported_rows = 0

    for idx, row in enumerate(reader, start=2):
        try:
            sale_date = dt.date.fromisoformat(row["date"].strip())
            product_name = row["product"].strip()
            qty = Decimal(row["qty"].strip())
            total = Decimal(row["total"].strip())
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid row at line {idx}: {exc}") from exc

        if not product_name:
            raise HTTPException(status_code=400, detail=f"Product is required at line {idx}")

        product = db.scalar(select(Product).where(Product.name == product_name))
        if product is None:
            product = Product(name=product_name)
            db.add(product)
            db.flush()

        db.add(SaleLine(date=sale_date, product_id=product.id, qty=qty, total=total))
        imported_rows += 1

    db.commit()
    return {"imported_rows": imported_rows}


def extract_counterparty(description: str) -> str:
    cleaned = " ".join(description.split())

    for separator in [" - ", " / ", " | "]:
        if separator in cleaned:
            candidate = cleaned.split(separator, 1)[1].strip()
            if candidate:
                cleaned = candidate
                break

    prefix_pattern = re.compile(
        r"^(card purchase|card payment|pos|sepa transfer|bank transfer|payment to|transfer to)\s+",
        flags=re.IGNORECASE,
    )
    cleaned = prefix_pattern.sub("", cleaned)
    cleaned = re.sub(r"\b(ref|id|trx|transaction)\b[:#\-\s]*\w+", "", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split()).strip("-_")

    return cleaned if cleaned else description.strip()


@router.post("/bank-csv")
def import_bank_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    document_id: Annotated[int | None, Form()] = None,
    month: Annotated[str | None, Form()] = None,
) -> dict[str, int]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    created_paths: list[str] = []

    try:
        if document_id is not None:
            if month:
                raise HTTPException(
                    status_code=400,
                    detail="month cannot be combined with document_id",
                )
            document = db.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="bank document not found")
            if document.section != "bank":
                raise HTTPException(status_code=400, detail="document must be a bank document")

        content = file.file.read()
        rows = parse_bank_csv(file.filename, content)

        if month:
            document, created_paths = create_bank_document(
                file.filename,
                content,
                month,
                db,
            )
            document_id = document.id

        result = import_bank_transactions(rows, db, document_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        for path in created_paths:
            if os.path.exists(path):
                os.remove(path)
        raise


def parse_bank_csv(filename: str, content: bytes) -> list[tuple[dt.date, str, Decimal]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(StringIO(text))
    required_headers = {"date", "description", "amount"}

    if not reader.fieldnames or not required_headers.issubset({name.strip() for name in reader.fieldnames}):
        raise HTTPException(
            status_code=400,
            detail="CSV must contain required headers: date, description, amount",
        )

    rows = []
    for idx, row in enumerate(reader, start=2):
        try:
            date = dt.date.fromisoformat(row["date"].strip())
            description = row["description"].strip()
            amount = Decimal(row["amount"].strip())
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid row at line {idx}: {exc}") from exc

        if not description:
            raise HTTPException(status_code=400, detail=f"description is required at line {idx}")
        rows.append((date, description, amount))

    return rows


def import_bank_transactions(
    rows: list[tuple[dt.date, str, Decimal]],
    db: Session,
    document_id: int | None,
) -> dict[str, int]:
    rules = db.scalars(select(CategoryRule)).all()
    imported_rows = 0
    skipped_rows = 0

    for date, description, amount in rows:
        category_id = None
        lower_description = description.lower()
        for rule in rules:
            if rule.keyword.lower() in lower_description:
                category_id = rule.category_id
                break

        counterparty = extract_counterparty(description)
        existing_transaction = db.scalar(
            select(Transaction.id).where(
                Transaction.date == date,
                Transaction.description == description,
                Transaction.amount == amount,
                Transaction.counterparty == counterparty,
            )
        )

        if existing_transaction is not None:
            skipped_rows += 1
            continue

        db.add(
            Transaction(
                date=date,
                description=description,
                amount=amount,
                counterparty=counterparty,
                document_id=document_id,
                category_id=category_id,
            )
        )
        imported_rows += 1

    return {"imported_rows": imported_rows, "skipped_rows": skipped_rows}
