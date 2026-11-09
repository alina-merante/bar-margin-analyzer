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
- `src/components/AlertBanner.jsx`: banner di feedback (`error`, `warning`,
  `success`);
- `src/apiErrors.js`: conversione delle risposte di errore API in messaggi;
- `src/components/Sidebar.jsx`: navigazione principale;
- `src/App.css` e `src/index.css`: stile dell'applicazione.

## Messaggi di upload

Gli esiti degli upload (CSV POS/banca, fatture, documenti e chiusure di cassa)
sono mostrati con `AlertBanner`:

- i messaggi restano visibili finché non vengono chiusi con il pulsante X
  (`aria-label="Chiudi messaggio"`) oppure sostituiti da un nuovo upload nella
  stessa area; un click altrove nella pagina non li cancella e non ci sono timer;
- gli errori usano `role="alert"`, i successi `role="status"`; tutti i messaggi,
  anche di successo, sono chiudibili;
- `src/apiErrors.js` ricava il testo da `detail` del backend (stringa, array di
  validazione FastAPI o oggetto con `message`) e gestisce risposte non JSON o
  vuote;
- HTTP 409: titolo "Documento già presente" e `detail` originale del backend,
  banner rosso;
- HTTP 422: titolo "Dati non validi" e `detail` originale, quando disponibile;
- HTTP 500 e superiori: titolo "Errore del server" e messaggio fisso senza
  dettagli tecnici;
- errore di rete: titolo "Connessione non riuscita" e messaggio fisso.

La variante `warning` (arancione) è prevista per avvisi non bloccanti.

I test frontend si eseguono con `npm --prefix frontend test`.

## Flusso OCR e revisione chiusure di cassa

L'applicazione supporta il caricamento di fotografie di chiusure di cassa in PDF
o PNG. Il backend estrae automaticamente sei campi mediante OCR:

- Data chiusura (GG/MM/YYYY)
- Numero chiusura
- Importo totale (in €)
- Importo contanti (in €)
- Importo carta/POS (in €)
- Numero scontrini emessi

**Flusso AUTO_SAVE:** Se tutti i campi sono estratti correttamente e coerenti
(importo totale = contanti + carta), il record viene salvato automaticamente.

**Flusso SAVE_FOR_REVIEW:** Se mancano campi, ci sono incoerenze negli importi,
o la data è ambigua, il record viene messo in revisione. L'operatore può:

1. Visualizzare l'anteprima dell'immagine
2. Correggere manualmente i campi non estratti o errati
3. Approvare e collegare la chiusura ai dati effettivi del registratore
4. Rifiutare e marcare come non applicabile

I dati estratti e corretti vengono salvati nel database con timestamp e
tracciamento delle modifiche.

## Build e lint

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
```

Le sezioni analytics relative a categorie, fornitori e alcuni insight sono
ancora placeholder nel backend e possono quindi apparire vuote nell'interfaccia.