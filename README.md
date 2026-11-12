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
In Codespaces, l'unico comando standard per avviare l'ambiente è:

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

## Fondamenta autenticazione backend

La revisione `20261111_0011` aggiunge le tabelle per sessioni server-side e
limitazione dei tentativi di login. Prima di avviare l'API in produzione,
configurare:

- `APP_ENV=production`;
- `AUTH_SECRET_KEY` con almeno 32 byte casuali;
- `AUTH_ALLOWED_ORIGINS` con le origini frontend autorizzate, separate da
  virgole. Non usare wildcard.

In produzione il cookie di sessione è sempre `Secure`, `HttpOnly` e
`SameSite=Lax`. In sviluppo il secret viene generato per il processo e le
sessioni non sopravvivono al riavvio.

Il primo owner può essere creato con
`cd backend && .venv/bin/python -m app.bootstrap_owner`, dopo aver applicato
le migrazioni al database scelto. Il comando chiede le credenziali senza
mostrare la password e si rifiuta di procedere se esistono già utenti o bar
non riconducibili al bar legacy.

La migrazione `20261111_0013` rende per-bar l'unicità di prodotti, categorie,
chiusure e intake, mantenendo vincoli separati per record legacy con `bar_id`
nullo. Categorie/regole, import CSV POS/banca e revisione delle chiusure
richiedono sessione autenticata, bar attivo e i permessi previsti. Gli import
assegnano `bar_id` lato server; gli ID di documenti e categorie vengono
verificati contro il bar selezionato.

Le API finanziarie di fatture, pagamenti e riconciliazioni richiedono ora una
sessione autenticata e un bar attivo. Owner e manager possono operare; lo staff
può consultare i dati finanziari del bar selezionato ma non crearli, modificarli,
cancellarli o riconciliarli. Le API verificano il tenant anche nei collegamenti
tra fatture, pagamenti e transazioni. Upload, elenco ed eliminazione documenti
e revisione OCR richiedono sessione, bar attivo e permessi; le scritture
richiedono anche token CSRF e `Origin` autorizzato. Lo staff può caricare e
revisionare, ma non eliminare documenti né gestire pagamenti. Documenti,
intake e allegati senza tenant non sono automaticamente accessibili.

Non esiste più un mount pubblico dei file: `GET /uploads/documents/{nome}`,
`GET /uploads/previews/{nome}` e `GET /uploads/invoices/{nome}` verificano
sessione, membership, bar attivo e record `Document` o `Invoice` pertinente.
Gli allegati fattura sono autorizzati tramite `Invoice.file_url`, senza
modifica dello schema o associazione automatica a `Document`; riferimenti
condivisi tra bar vengono negati. I file sono inviati senza cache e quelli
non visualizzabili in sicurezza vengono scaricati come allegati. Eliminare
un record documento non elimina i file dal disco.

Il frontend attuale deve ancora implementare `GET /auth/csrf`, `POST
/auth/login`, `GET /auth/bars` e `PUT /auth/active-bar`, e inviare cookie,
`X-CSRF-Token` e `Origin` autorizzato alle operazioni di scrittura, incluse
`POST /documents/upload`, `DELETE /documents/{id}` e le modifiche a
`/cash-closures/review/{id}`. Deve inoltre inviare la sessione nelle richieste
dei file protetti e l'header `X-Expected-Bar-ID` in tutte le richieste tenant-
scoped. Il valore deve essere l'ID del bar attivo letto da `/auth/active-bar`;
è un controllo di coerenza, non un'autorizzazione. Il backend verifica sessione,
bar attivo, membership e permessi indipendentemente dal valore ricevuto. Le
richieste senza header sono rifiutate (428), con valore non valido (400) o
diverso dal bar attivo (409). Le API `/auth/*` di login e selezione bar non
richiedono questo header. Le scritture serializzano il contesto sessione/bar/
membership per la durata della transazione; upload e OCR ricontrollano il
contesto prima del salvataggio definitivo. I download protetti mantengono il
contesto bloccato fino al completamento dello streaming del file. Fino a tale
adeguamento il flusso non funziona dall'interfaccia attuale.

Tutti gli endpoint `/analytics/*` richiedono sessione e bar attivo accessibile
(owner, manager o staff); le risposte non sono memorizzabili nella cache.
Aggregazioni e confronti includono soltanto i record del bar attivo, escludendo
quelli con `bar_id` nullo e i collegamenti incoerenti fra tenant. Il frontend
deve autenticarsi e selezionare un bar prima di caricare la dashboard, e
ricaricare gli analytics dopo ogni cambio di bar. I riepiloghi per fornitore e
gli insight per categoria/fornitore conservano il comportamento attuale ancora
non implementato. Il fatturato usa il totale delle chiusure: non esiste un
riepilogo analytics separato degli incassi contanti/carta;
`payments-by-method` riguarda i pagamenti registrati. Non esporre pubblicamente
l'applicazione senza una verifica
complessiva della sicurezza e dell'integrazione frontend.

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

Import POS (richiede sessione autenticata, bar selezionato, cookie CSRF e
header `Origin` autorizzato):

```bash
curl -X POST http://localhost:8000/imports/pos-csv \
  -F "file=@data/pos_marzo_2026.csv"
```

Import movimenti bancari (stessi requisiti dell'import POS):

```bash
curl -X POST http://localhost:8000/imports/bank-csv \
  -F "file=@data/bank_marzo_2026.csv"
```

Upload chiusura di cassa (`section=cash`), dopo autenticazione e selezione
del bar (sostituire cookie e token con quelli della sessione):

```bash
curl -X POST http://localhost:8000/documents/upload \
  -H "Origin: http://localhost:5173" -H "X-CSRF-Token: TOKEN" \
  -b "barmanager_session=SESSIONE; barmanager_csrf=TOKEN" \
  -F "file=@chiusura.pdf" -F "month=2026-03" -F "section=cash"
```

L'endpoint crea `Document` e `CashClosureIntake` nella stessa transazione,
assegnandoli al bar attivo; una chiusura attendibile viene salvata subito,
mentre una lettura incerta richiede revisione e approvazione. Risponde:

- HTTP 409 per un documento duplicato o una chiusura con la stessa data e
  numero nello stesso bar;
- HTTP 422 se il file è illeggibile o non contiene evidenze sufficienti.

Il campo `detail` della risposta contiene il motivo in italiano ed è mostrato
così com'è nell'interfaccia. Dettagli e limiti dell'estrazione sono in
[README_ARCHITECTURE.md](README_ARCHITECTURE.md#chiusure-di-cassa).

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
- `/invoices/{invoice_id}/transaction-candidates`
- `/invoices/{invoice_id}/reconcile-transaction`

## Stato degli analytics

Le seguenti aree sono attualmente placeholder o incomplete nell'API:

- spese per categoria;
- spese per fornitore;
- sezioni categoria/fornitore dell'overview;
- calcoli degli insight per categoria e fornitore.

Gli endpoint esistono e restituiscono la forma prevista, ma le liste dei
risultati possono essere vuote.

## Costi e riconciliazione verificati

I test backend verificano che:

- una fattura non pagata è esclusa dal P&L e il costo viene contato una sola
   volta;
- una Transaction bancaria negativa isolata non genera un costo;
- i pagamenti parziali mantengono il residuo e non generano costo prima del
   saldo;
- il costo intero viene attribuito al mese del pagamento che completa il saldo;
- overpayment, riuso della Transaction e riuso del Payment tra fatture vengono
   rifiutati;
- una fattura con pagamenti riconciliati non può essere eliminata.

La riconciliazione bancaria non è automatica: BarManager propone movimenti
candidati in sola lettura e crea il pagamento solo dopo conferma dell'utente.
Le formule e gli esempi P&L sono descritti in
[DASHBOARD_CALCULATIONS.md](DASHBOARD_CALCULATIONS.md).

## Documentazione correlata

- [README_DEMO.md](README_DEMO.md): caricamento dati demo e controlli del dashboard;
- [README_ARCHITECTURE.md](README_ARCHITECTURE.md): stack e struttura reale;
- [DASHBOARD_CALCULATIONS.md](DASHBOARD_CALCULATIONS.md): formule e specifica dei costi;
- [frontend/README.md](frontend/README.md): sviluppo e struttura del frontend.