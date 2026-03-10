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
