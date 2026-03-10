# Bar Margin Analyzer

Initial backend scaffold for the **Bar Margin Analyzer** project.

## Stack

- **Backend:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Migrations:** Alembic

## Run with Docker Compose

```bash
docker compose up --build
```

API available at:

- `http://localhost:8000`
- `http://localhost:8000/health`
- Swagger docs: `http://localhost:8000/docs`

## Database Migrations (Alembic)

Run alembic commands inside the API container:

```bash
docker compose run --rm api alembic upgrade head
```

## POS CSV Import (existing)

Expected CSV headers:

```csv
date,product,qty,total
2026-09-01,Beer Pint,12,72.00
2026-09-01,House Wine,5,30.00
```

Endpoint example:

```bash
curl -X POST "http://localhost:8000/imports/pos-csv" -F "file=@sales.csv"
```

## Bank Transactions Import

Expected CSV headers:

```csv
date,description,amount
2026-09-01,CARD PURCHASE - Metro Cash & Carry,-124.80
2026-09-02,BANK TRANSFER FROM EVENT ORGANIZER,850.00
```

Endpoint example:

```bash
curl -X POST "http://localhost:8000/imports/bank-csv" -F "file=@bank.csv"
```

Response example:

```json
{
  "imported_rows": 2
}
```

## Categories and Rules

Create category:

```bash
curl -X POST "http://localhost:8000/categories" \
  -H "Content-Type: application/json" \
  -d '{"name":"Supplies"}'
```

List categories:

```bash
curl "http://localhost:8000/categories"
```

Create rule:

```bash
curl -X POST "http://localhost:8000/rules" \
  -H "Content-Type: application/json" \
  -d '{"keyword":"metro","category_id":1}'
```

List rules:

```bash
curl "http://localhost:8000/rules"
```

Rules are applied during `/imports/bank-csv` import using case-insensitive keyword matching against `description`.

## Analytics Endpoints

Monthly P&L summary:

```bash
curl "http://localhost:8000/analytics/pnl?month=2026-09"
```

Year-to-date P&L with monthly breakdown:

```bash
curl "http://localhost:8000/analytics/pnl/ytd?year=2026"
```

Combined monthly overview (defaults to current month when `month` is omitted):

```bash
curl "http://localhost:8000/analytics/overview?month=2026-09"
```

Expenses by category for month:

```bash
curl "http://localhost:8000/analytics/expenses-by-category?month=2026-09"
```

Expenses by supplier for month:

```bash
curl "http://localhost:8000/analytics/expenses-by-supplier?month=2026-09"
```

Behavior notes:

- `month` format is `YYYY-MM`.
- `year` format is `YYYY`.
- Revenue uses `SaleLine.total` only.
- Expenses use absolute values of negative `Transaction.amount` only.
- Positive bank transactions are ignored in expense calculations.
- Delta fields in `/analytics/pnl` are calculated as current month minus previous month.

Legacy sales analytics remain available:

- `GET /analytics/top-products?month=YYYY-MM`
- `GET /analytics/bottom-products?month=YYYY-MM`
