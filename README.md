# Bar Margin Analyzer

BarManager è un'applicazione FastAPI + React per importare dati POS e bancari,
gestire fatture e pagamenti e visualizzare analytics finanziari.

## Avvio rapido

### Modalità Docker standard

Dalla root del repository:

```bash
npm run dev:full
```

Il comando installa le dipendenze frontend, avvia PostgreSQL e l'API in Docker,
attende il controllo di salute dell'API e avvia il frontend Vite.

### Modalità GitHub Codespaces

Il repository include [`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json).
Dopo la creazione del Codespace:

```bash
npm run dev:codespaces
```

In questa modalità PostgreSQL gira nel container Docker `db`, mentre backend e
frontend girano come processi nativi. Il backend usa Python 3.12 e
`backend/.venv`; il frontend usa Node 20 e Vite.

Il devcontainer configura Python 3.12, Node 20, accesso Docker, dipendenze OCR
e dipendenze frontend. Installa Tesseract, il pacchetto lingua italiana
`tesseract-ocr-ita`, Poppler e `python3.12-venv`.

## Porte e URL

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Swagger: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`

Vite inoltra le richieste `/api/*` a `http://127.0.0.1:8000`.

## Migrazioni Alembic

Le migrazioni vengono applicate automaticamente prima dell'avvio dell'API:

- in Docker tramite `backend/docker-entrypoint.sh`;
- in Codespaces tramite `scripts/dev-codespaces.sh`.

Non è necessario eseguire una migrazione manuale durante l'avvio normale.

## Clean bootstrap

Per verificare database vuoto, schema, endpoint API e build frontend usando
risorse Compose temporanee:

```bash
sh scripts/verify-clean-bootstrap.sh
```

Lo script crea un volume PostgreSQL temporaneo, esegue le migrazioni, verifica
le tabelle e gli endpoint, compila il frontend e rimuove le risorse temporanee.

## Ripresa del progetto dopo mesi

1. Aprire il repository in GitHub Codespaces oppure in un ambiente con Docker,
   Node 20 e Python 3.12.
2. Eseguire `npm run dev:codespaces` in Codespaces oppure `npm run dev:full` in
   modalità Docker standard.
3. Aprire `http://localhost:5173` e verificare l'API con:
   `curl http://localhost:8000/health`.
4. Per popolare il dashboard, seguire [README_DEMO.md](README_DEMO.md).
5. Se un servizio non è pronto, controllare `docker compose ps`; in Codespaces
   controllare anche `backend/.uvicorn.log`.

Comandi utili dalla root:

- `npm run dev:api`: avvia solo PostgreSQL e API in Docker;
- `npm run dev:stop`: arresta i container Docker API e database;
- `npm run dev:down`: arresta e rimuove le risorse Compose.

## Import e API principali

Import POS:

```bash
curl -X POST http://localhost:8000/imports/pos-csv \
  -F "file=@data/pos_marzo_2026.csv"
```

Import movimenti bancari:

```bash
curl -X POST http://localhost:8000/imports/bank-csv \
  -F "file=@data/bank_marzo_2026.csv"
```

Endpoint analytics principali:

- `/analytics/pnl?month=YYYY-MM`
- `/analytics/pnl/trend?months=6&month=YYYY-MM`
- `/analytics/pnl/ytd?year=YYYY`
- `/analytics/overview?month=YYYY-MM`
- `/analytics/expenses-by-category?month=YYYY-MM`
- `/analytics/expenses-by-supplier?month=YYYY-MM`
- `/analytics/invoices-summary`
- `/analytics/payments-by-method?month=YYYY-MM`
- `/analytics/insights?month=YYYY-MM`

## Stato degli analytics

Le seguenti aree sono attualmente placeholder o incomplete nell'API:

- spese per categoria;
- spese per fornitore;
- sezioni categoria/fornitore dell'overview;
- calcoli degli insight per categoria e fornitore.

Gli endpoint esistono e restituiscono la forma prevista, ma le liste dei
risultati possono essere vuote.

## Specifica dei costi e punto aperto

La specifica desiderata per costi e riconciliazione è descritta in
[DASHBOARD_CALCULATIONS.md](DASHBOARD_CALCULATIONS.md). In particolare, resta
da verificare separatamente che:

- un movimento bancario negativo isolato non generi automaticamente un costo;
- una fattura isolata o non riconciliata non generi automaticamente un costo;
- una fattura pagata e riconciliata venga conteggiata una sola volta;
- fattura, movimento bancario e pagamento non producano doppio conteggio.

Questa documentazione conserva la specifica desiderata senza correggerla in
base all'implementazione attuale. La verifica appartiene ai test funzionali
successivi.

## Documentazione correlata

- [README_DEMO.md](README_DEMO.md): caricamento dati demo e controlli del dashboard;
- [README_ARCHITECTURE.md](README_ARCHITECTURE.md): stack e struttura reale;
- [DASHBOARD_CALCULATIONS.md](DASHBOARD_CALCULATIONS.md): formule e specifica dei costi;
- [frontend/README.md](frontend/README.md): sviluppo e struttura del frontend.