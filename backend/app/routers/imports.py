import csv
import datetime as dt
from decimal import Decimal
from io import StringIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, SaleLine

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
