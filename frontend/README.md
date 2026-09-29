# BarManager frontend

Frontend React del progetto BarManager, sviluppato con Vite.

## Sviluppo

Dalla root del repository, il modo consigliato per avviare l'intero progetto è:

```bash
npm run dev:full
```

In GitHub Codespaces usare:

```bash
npm run dev:codespaces
```

Per avviare solo il frontend:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Il server Vite ascolta sulla porta `5173` e inoltra le richieste `/api/*`
all'API su `http://127.0.0.1:8000`.

## Struttura

- `src/App.jsx`: routing, caricamento dati, upload ed export del dashboard;
- `src/pages/DashboardPage.jsx`: dashboard analytics;
- `src/pages/InvoicesPage.jsx`: gestione fatture e pagamenti;
- `src/pages/UploadPage.jsx`: import POS, movimenti bancari e documenti;
- `src/components/Sidebar.jsx`: navigazione principale;
- `src/App.css` e `src/index.css`: stile dell'applicazione.

## Build e lint

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
```

Le sezioni analytics relative a categorie, fornitori e alcuni insight sono
ancora placeholder nel backend e possono quindi apparire vuote nell'interfaccia.