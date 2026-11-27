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

Tutte le chiusure OCR entrano in revisione,
anche quando i dati estratti sono completi e coerenti.

1. Visualizzare il documento originale.
2. Correggere i campi, se autorizzati.
3. Registrare la verifica completata.
4. Approvare o rifiutare secondo le autorizzazioni.

Una correzione o rielaborazione invalida la verifica precedente.
L'approvazione e il rifiuto definitivo sono riservati al
proprietario e all'amministratore globale.

## Build e lint

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
```

Le sezioni analytics relative a categorie, fornitori e alcuni insight sono
ancora placeholder nel backend e possono quindi apparire vuote nell'interfaccia.

## Layout responsive e sistema grafico

Il file `src/responsive.css` centralizza le regole responsive,
le proporzioni tipografiche, le spaziature e lo stile delle scrollbar.
Le tabelle si adattano allo spazio disponibile tramite container queries.

La suite `responsive.spec.js` verifica cinque pagine operative
su otto risoluzioni, da 320 a 1920 px, includendo contenuti
sintetici, filtri, modali e schede OCR senza modificare
i dati contabili del database.

### Sistema grafico responsive

- Font Inter e gerarchia tipografica condivisa.
- Layout adattivi per smartphone, tablet e desktop.
- Schede, pulsanti, filtri e spaziature uniformati.
- Tabelle adattive tramite container queries.
- Storico documenti e chiusure con layout compatto.
- Filtri di revisione accessibili anche senza legenda visibile.
