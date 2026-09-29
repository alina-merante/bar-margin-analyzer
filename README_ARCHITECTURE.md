# BarManager — Architettura

BarManager importa dati POS e movimenti bancari, gestisce fatture e pagamenti,
e mette a disposizione analytics via API REST e interfaccia React.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic
- Database: PostgreSQL 16 in Docker
- Backend standard: container Docker
- Backend Codespaces: processo nativo in `backend/.venv`, Python 3.12
- Frontend: React, React Router e Vite, processo nativo con Node 20
- OCR: Tesseract con lingua italiana, Poppler, Pillow e `pdf2image`

## Runtime

In modalità standard, `npm run dev:full` avvia PostgreSQL e API in Docker e il
frontend nativamente con Vite.

In GitHub Codespaces, `npm run dev:codespaces` avvia PostgreSQL in Docker e
backend/frontend nativamente. Questa separazione è definita da
[`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json), che
configura Python 3.12, Node 20, Docker, OCR e il forwarding delle porte.

Le porte principali sono `5432` per PostgreSQL, `8000` per l'API e `5173` per
il frontend.

## Struttura reale

```text
backend/
  app/
    main.py
    database.py
    models/
      category_rule.py
      daily_cash_closure.py
      document.py
      expense_category.py
      invoice.py
      invoice_payment_link.py
      payment.py
      product.py
      sale_line.py
      transaction.py
    routers/
      analytics.py
      categories.py
      documents.py
      finance.py
      health.py
      imports.py
    services/
      ai_invoice_parser.py
  alembic/
  Dockerfile
  docker-entrypoint.sh

frontend/
  src/
    App.jsx
    App.css
    index.css
    components/Sidebar.jsx
    pages/
      DashboardPage.jsx
      InvoicesPage.jsx
      UploadPage.jsx

data/
  pos_*.csv
  bank_*.csv

.devcontainer/devcontainer.json
docker-compose.yml
docker-compose.clean-bootstrap.yml
scripts/dev-full.sh
scripts/dev-codespaces.sh
scripts/verify-clean-bootstrap.sh
```

## Core concepts

### Sales POS

- Sono memorizzate in `SaleLine`.
- I campi principali sono data, prodotto, quantità e totale.
- Sono importate tramite `/imports/pos-csv`.

### Movimenti bancari

- Sono memorizzati in `Transaction`.
- I campi principali sono data, descrizione, importo, controparte e categoria.
- Le regole sono applicate durante `/imports/bank-csv`.

### Categorie e regole

Le categorie definiscono i tipi di spesa e le regole associano parole chiave
alle categorie durante l'importazione dei movimenti bancari.

### Fatture e pagamenti

Le fatture tracciano fornitore, scadenza, importi e stato. I pagamenti possono
essere collegati manualmente alle fatture.

### Analytics

Endpoint principali:

- `/analytics/pnl`
- `/analytics/pnl/trend`
- `/analytics/pnl/ytd`
- `/analytics/overview`
- `/analytics/expenses-by-category`
- `/analytics/expenses-by-supplier`
- `/analytics/insights`

Le breakdown per categoria e fornitore, le sezioni corrispondenti dell'overview
e i relativi insight sono attualmente placeholder o incompleti nell'API. Gli
endpoint esistono, ma i risultati possono essere vuoti.

## Specifica dei costi

La specifica desiderata dei costi e della riconciliazione è mantenuta in
[DASHBOARD_CALCULATIONS.md](DASHBOARD_CALCULATIONS.md). La sua coerenza con
l'implementazione è un punto aperto da verificare con i test funzionali e non
viene modificata in questo aggiornamento documentale.

## Avvio e clean bootstrap

Usare `npm run dev:full` in modalità Docker standard oppure
`npm run dev:codespaces` in GitHub Codespaces. Le migrazioni Alembic vengono
applicate automaticamente prima dell'avvio dell'API.

Per verificare schema, endpoint e build frontend su risorse temporanee:

```bash
sh scripts/verify-clean-bootstrap.sh
```

API: `http://localhost:8000` e `http://localhost:8000/docs`.