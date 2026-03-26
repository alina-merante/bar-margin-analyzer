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

## Invoice and Payment Tracking

### Sample payloads

Invoice payload:

```json
{
  "supplier": "Metro Cash & Carry",
  "invoice_number": "INV-2026-091",
  "issue_date": "2026-09-05",
  "due_date": "2026-09-30",
  "total": 450.00,
  "vat": 75.00,
  "status": "pending"
}
```

Payment payload:

```json
{
  "date": "2026-09-20",
  "amount": 300.00,
  "method": "bank_transfer",
  "counterparty": "Metro Cash & Carry",
  "reference": "PAY-2026-09-20-01"
}
```

### Invoice endpoints

Create invoice:

```bash
curl -X POST "http://localhost:8000/invoices" \
  -H "Content-Type: application/json" \
  -d '{"supplier":"Metro Cash & Carry","invoice_number":"INV-2026-091","issue_date":"2026-09-05","due_date":"2026-09-30","total":450.00,"vat":75.00,"status":"pending"}'
```

List invoices:

```bash
curl "http://localhost:8000/invoices"
```

Filter invoices by status, supplier, and month:

```bash
curl "http://localhost:8000/invoices?status=pending&supplier=metro&month=2026-09"
```

### Payment endpoints

Create payment:

```bash
curl -X POST "http://localhost:8000/payments" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-09-20","amount":300.00,"method":"bank_transfer","counterparty":"Metro Cash & Carry","reference":"PAY-2026-09-20-01"}'
```

List payments:

```bash
curl "http://localhost:8000/payments"
```

Filter payments by method, counterparty, and month:

```bash
curl "http://localhost:8000/payments?method=card&counterparty=metro&month=2026-09"
```

### Link payment to invoice

Manual link endpoint:

```bash
curl -X POST "http://localhost:8000/invoices/1/link-payment" \
  -H "Content-Type: application/json" \
  -d '{"payment_id":1}'
```

Behavior notes:

- A payment can be linked to one or more invoices.
- Link creation is manual in this POC.
- Invoice status is set to `paid` when linked payment totals are greater than or equal to invoice total.

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

Invoice summary analytics:

```bash
curl "http://localhost:8000/analytics/invoices-summary"
```

Payments grouped by method for a month:

```bash
curl "http://localhost:8000/analytics/payments-by-method?month=2026-09"
```

Automated financial insights for a month:

```bash
curl "http://localhost:8000/analytics/insights?month=2026-09"
```

Behavior notes:

- `month` format is `YYYY-MM`.
- `year` format is `YYYY`.
- Revenue uses `SaleLine.total` only.
- Expenses use absolute values of negative `Transaction.amount` only.
- Positive bank transactions are ignored in expense calculations.
- Delta fields in `/analytics/pnl` are calculated as current month minus previous month.
- `/analytics/insights` compares current month to previous month and returns:
  - `metrics`: revenue, expenses, profit, and percentage changes (rounded to 2 decimals).
  - `insights`: text insights for significant changes in revenue/expenses/profit (>5%), top expense category change (>10%), and top supplier expense share.

Legacy sales analytics remain available:

- `GET /analytics/top-products?month=YYYY-MM`
- `GET /analytics/bottom-products?month=YYYY-MM`
