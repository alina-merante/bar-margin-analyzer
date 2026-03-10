import csv
import datetime as dt
import re
from decimal import Decimal
from io import StringIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CategoryRule, Product, SaleLine, Transaction

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
def import_bank_csv(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, int]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(StringIO(content))
    required_headers = {"date", "description", "amount"}

    if not reader.fieldnames or not required_headers.issubset({name.strip() for name in reader.fieldnames}):
        raise HTTPException(
            status_code=400,
            detail="CSV must contain required headers: date, description, amount",
        )

    rules = db.scalars(select(CategoryRule)).all()
    imported_rows = 0

    for idx, row in enumerate(reader, start=2):
        try:
            date = dt.date.fromisoformat(row["date"].strip())
            description = row["description"].strip()
            amount = Decimal(row["amount"].strip())
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid row at line {idx}: {exc}") from exc

        if not description:
            raise HTTPException(status_code=400, detail=f"description is required at line {idx}")

        category_id = None
        lower_description = description.lower()
        for rule in rules:
            if rule.keyword.lower() in lower_description:
                category_id = rule.category_id
                break

        transaction = Transaction(
            date=date,
            description=description,
            amount=amount,
            counterparty=extract_counterparty(description),
            category_id=category_id,
        )
        db.add(transaction)
        imported_rows += 1

    db.commit()
    return {"imported_rows": imported_rows}
