# Bar Margin Analyzer

Initial backend scaffold for the **Bar Margin Analyzer** project.

## Stack

- **Backend:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Migrations:** Alembic

## Project Structure

```text
backend/
  app/
    main.py
    database.py
    models/
    routers/
    services/
  alembic/
    versions/
  alembic.ini
  requirements.txt
docker-compose.yml
README.md
```

## Run with Docker Compose

```bash
docker compose up --build
```

API will be available at:
- `http://localhost:8000`
- `http://localhost:8000/health`
- `POST http://localhost:8000/imports/pos-csv`
- `GET http://localhost:8000/analytics/top-products?month=YYYY-MM`
- `GET http://localhost:8000/analytics/bottom-products?month=YYYY-MM`
- Swagger docs: `http://localhost:8000/docs`

## Database Migrations (Alembic)

Run alembic commands inside the API container:

```bash
docker compose run --rm api alembic revision -m "init"
docker compose run --rm api alembic upgrade head
```

## Notes

- `DATABASE_URL` is wired through Docker Compose.
- Base SQLAlchemy session/engine configuration is in `backend/app/database.py`.

## POS CSV Import

Expected CSV headers:

```csv
date,product,qty,total
2026-09-01,Beer Pint,12,72.00
2026-09-01,House Wine,5,30.00
```

Import endpoint example:

```bash
curl -X POST "http://localhost:8000/imports/pos-csv" \
  -F "file=@sales.csv"
```

Example response:

```json
{
  "imported_rows": 2
}
```

## Analytics Endpoints

Top products for a month:

```bash
curl "http://localhost:8000/analytics/top-products?month=2026-09"
```

Bottom products for a month:

```bash
curl "http://localhost:8000/analytics/bottom-products?month=2026-09"
```

Response shape includes ranking by quantity and ranking by revenue.
