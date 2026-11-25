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
- I campi principali sono data, descrizione, importo, controparte, categoria e
  `document_id`, FK nullable verso `Document.id`.
- Le regole sono applicate durante `/imports/bank-csv`.
- Quando la richiesta include il mese del documento, il CSV viene validato
  interamente prima di creare il documento. Document e nuove Transaction sono
  persistiti con un unico commit; in caso di errore il rollback non lascia
  Document o Transaction parziali.
- La deduplicazione confronta data, descrizione, importo e controparte; le righe
  già importate vengono saltate.
- L'import crea movimenti `Transaction`; non crea automaticamente `Payment` e
  non produce costi nel P&L.

### Chiusure di cassa

Le chiusure sono caricate da `POST /documents/upload` con `section` `cash` o
`cash_closure`; i dati estratti via OCR/testo restano in revisione e sono
salvati in `DailyCashClosure` soltanto dopo approvazione esplicita.

Validazione, prima di scrivere file o record:

- l'API rifiuta con HTTP 422 documenti illeggibili o senza evidenze sufficienti;
- data, numero e totale mancanti o ambigui possono essere completati in
  revisione, ma sono obbligatori per l'approvazione;
- contanti ed elettronici non riconosciuti restano NULL, non zero;
- il totale scontrini è una lettura separata, non il totale complessivo;
  il numero di azzeramenti non è un identificativo di chiusura.

Prevenzione dei duplicati:

- controlli su hash del file e su data e numero nel bar attivo;
- vincoli univoci per bar sui documenti in revisione e sulle chiusure approvate.

Atomicità dell'import:

- `Document` e `CashClosureIntake` sono creati nella stessa transazione;
- se l'errore avviene durante la scrittura del file, la generazione delle
  preview, il flush o il commit, viene eseguito il rollback e vengono rimossi il
  file originale e le preview create da quel tentativo. Non resta quindi un
  `Document` senza intake né file orfani;
- il cleanup non riguarda upload già completati con successo.

Pipeline OCR (`app/services/document_ocr.py`, `cash_closure_parser.py`):
lettura della pagina intera (nessun ritaglio), correzione dell'orientamento,
PDF multipagina. Il parser raccoglie i candidati per ogni campo (etichetta,
vicinanza) e non sceglie mai il primo valore. Se restano campi ambigui,
malformati, mancanti o incoerenze aritmetiche parte una seconda lettura
(ritaglio storico, immagine binarizzata) confrontata campo per campo; i valori
in conflitto restano irrisolti. Altri metodi di pagamento (buoni pasto, ticket)
sono rilevati ma non contabilizzati.

Limiti noti: accuratezza non verificata su documenti reali di registratori
diversi (i test OCR usano immagini sintetiche); nessun raddrizzamento di
inclinazioni piccole; HEIC, CSV e XLSX non supportati per le chiusure; PDF con
più chiusure rifiutati come ambigui.

### Revisione e correzione chiusure (SAVE_FOR_REVIEW)

Tutte le chiusure riconosciute sono salvate con lo stato `SAVE_FOR_REVIEW`
nella tabella `cash_closure_intakes`. La revisione permette di controllare:

- Data ambigua (non è una data di calendario valida)
- Campi obbligatori mancanti (numero, totale)
- Importi incoerenti (totale ≠ contanti + carta)
- Campi irrisolti (testo ambiguo, multipli candidati)

L'interfaccia visualizza:

- Anteprima dell'immagine originale
- Sei campi editabili (data, numero, totale, contanti, carta, scontrini)
- Pulsanti per approvare (collegare a `DailyCashClosure`) o rifiutare

Dopo l'approvazione, i dati corretti vengono salvati in `DailyCashClosure` e
la riga di revisione è marcata come processata. Il numero di scontrini corretto
è conservato separatamente dal valore OCR originale.
L'approvazione richiede un proprietario del bar o un amministratore globale
con accesso al bar attivo. Il filtro mensile usa la data effettiva dell'intake;
la vista di tutte le chiusure include anche quelle prive di data. Salvare una
data corretta o rielaborata aggiorna `Document.month`; in assenza di data resta
il precedente mese archivistico. Non vengono modificati documenti già approvati.

### Storico documenti

La colonna DATA usa date in formato italiano `GG/MM/AAAA` e rappresenta la data
contabile disponibile per il documento:

- BANK: data della Transaction collegata; se le date sono diverse, intervallo
  dalla data minima alla massima.
- CASH: data della chiusura approvata oppure della revisione pendente collegata.
- Fatture: `Invoice.issue_date`.
- Altri documenti: `Document.created_at` come fallback.

Per documenti BANK legacy senza Transaction collegate, e documenti CASH senza
una data di chiusura disponibile, la visualizzazione usa `Document.created_at`
come fallback. Il filtro dei documenti CASH usa la data contabile disponibile,
anche se il mese archivistico di un record storico differisce; per le chiusure
senza data usa il mese archivistico. Fatture e documenti bancari conservano le
regole precedenti.

### Categorie e regole

Le categorie definiscono i tipi di spesa e le regole associano parole chiave
alle categorie durante l'importazione dei movimenti bancari.

### Fatture e pagamenti

Le fatture tracciano fornitore, scadenza, importi e stato. La riconciliazione
bancaria segue il flusso:

`Transaction → Payment → InvoicePaymentLink → Invoice`

- `Payment.transaction_id` è una FK nullable e UNIQUE verso `Transaction.id`;
  NULL mantiene possibili i Payment manuali e una Transaction può alimentare al
  massimo un Payment.
- `InvoicePaymentLink.payment_id` è UNIQUE: un Payment può essere collegato a
  una sola Invoice. Una Invoice può invece avere più Payment per i pagamenti
  parziali.
- `ON DELETE RESTRICT` impedisce di cancellare una Transaction già usata da un
  Payment. Le fatture con almeno un pagamento collegato non possono essere
  eliminate.
- Il sistema non trasforma automaticamente una Transaction in costo o
  pagamento. La ricerca candidati è read-only; l'utente deve confermare
  l'abbinamento.
- La riconciliazione confermata crea Payment e link in un'unica transazione,
  aggiorna lo stato della fattura e rifiuta Transaction positive, overpayment e
  riuso di movimenti o pagamenti.
- Il metodo viene derivato dai termini espliciti nella descrizione o nella
  controparte: SEPA, bonifico o transfer indicano `bank_transfer`; card/carta
  indica `card`. Per movimenti bancari non classificabili il fallback è
  `bank_transfer`.

Endpoint di riconciliazione:

- `GET /invoices/{invoice_id}/transaction-candidates`: propone candidati senza
  creare Payment o link;
- `POST /invoices/{invoice_id}/reconcile-transaction`: riconcilia il movimento
  indicato solo dopo la conferma dell'utente.

Un Payment manuale mantiene `transaction_id = NULL`, anche dopo essere stato
collegato a una fattura tramite il flusso manuale esistente.

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

Il P&L include una fattura una sola volta, per `Invoice.total`, nel mese del
pagamento che completa il saldo. I pagamenti parziali non generano costi finché
la fattura resta pending. "Da pagare" somma i residui delle fatture pending.
Formule ed esempi sono in [DASHBOARD_CALCULATIONS.md](DASHBOARD_CALCULATIONS.md).

## Avvio e clean bootstrap

Usare `npm run dev:full` in modalità Docker standard oppure
`npm run dev:codespaces` in GitHub Codespaces. Le migrazioni Alembic vengono
applicate automaticamente prima dell'avvio dell'API.

Per verificare schema, endpoint e build frontend su risorse temporanee:

```bash
sh scripts/verify-clean-bootstrap.sh
```

API: `http://localhost:8000` e `http://localhost:8000/docs`.

## Rielaborazione delle chiusure OCR

In **Chiusure da verificare**, usare **Rielabora OCR** per rileggere il
documento originale di una chiusura ancora pendente. Confrontare i valori
attuali, comprese eventuali correzioni manuali, con la nuova lettura e confermare
solo se si desidera sostituirli. I valori precedenti restano nello storico della
scheda; la chiusura richiede comunque revisione e approvazione esplicita.
Salvare prima eventuali modifiche non ancora salvate. Il totale scontrini è
distinto dal totale complessivo e non lo sostituisce.
La vista predefinita mostra le chiusure con data nel mese selezionato; scegliere
**Tutte le chiusure pendenti** per vedere anche altri mesi e quelle senza data.
Una data salvata o rielaborata aggiorna il periodo del documento. Senza data
resta il mese archivistico precedente, non una data contabile inventata.
L'approvazione è riservata al proprietario del bar o a un amministratore
globale con accesso al bar attivo.

### Ripristino dei documenti originali mancanti

Quando il file originale di una chiusura di cassa già importata non è più
disponibile, è possibile ricaricare lo stesso documento tramite il normale
caricamento delle chiusure di cassa.

Il ripristino è consentito esclusivamente se:
- il documento appartiene al bar attualmente selezionato;
- esiste una precedente acquisizione con SHA-256 identico;
- il file originale è effettivamente mancante;
- l'utente dispone dei permessi necessari per il caricamento.

Il ripristino conserva il documento e la chiusura esistenti, senza creare
nuovi record o modificare importi, dati OCR e stato di approvazione.

I file esistenti non vengono sovrascritti. I duplicati normali continuano
a restituire HTTP 409.

Il ripristino utilizza la directory configurata tramite UPLOAD_BASE_PATH.
Per l'ambiente PWA isolato, gli upload sono conservati nella directory
persistente definita in scripts/pwa-test-common.sh.

Test dedicati:
backend/tests/test_missing_cash_document_recovery.py

### Avvisi per chiusure di cassa incomplete

Nella schermata di revisione OCR, BarManager mostra un avviso
riepilogativo quando mancano uno o più campi obbligatori:
data, numero della chiusura o totale complessivo.

L'avviso si aggiorna durante la compilazione e scompare quando
tutti i campi obbligatori sono valorizzati.

Un campo vuoto rappresenta un dato non noto ed è distinto da
un valore esplicito pari a zero. Il totale complessivo non viene
ricavato automaticamente dal totale degli scontrini.

La modifica riguarda esclusivamente l'interfaccia e non altera
i dati OCR salvati, i controlli del backend o le autorizzazioni
di approvazione.

Test dedicati:
`node --test frontend/tests/cashClosureIncomplete.test.js`

### Caricamento fotografie da tablet

- Le immagini fino a 20 MB vengono caricate normalmente.
- Le immagini superiori a 20 MB vengono inviate alla funzione
  di compressione automatica prima del caricamento.
- La compressione utilizza un obiettivo di 5 MB e una dimensione
  massima di 2000 pixel per lato.
- Se la compressione fallisce, viene mostrato un messaggio
  comprensibile e il caricamento viene interrotto.
- I PDF superiori a 20 MB vengono rifiutati con un messaggio
  che richiede di ridurne la dimensione.
- Le regole di caricamento sono coperte da test automatici.

La disponibilità della fotocamera fisica e il risultato della
compressione su uno specifico tablet richiedono una prova
sul dispositivo reale.

### Storico e annullamento delle chiusure di cassa

Nel branch `feature/granular-permissions` è disponibile una
pagina dedicata allo storico delle chiusure di cassa, raggiungibile
dalla navigazione dell'applicazione secondo i permessi previsti.

Lo storico permette di:
- consultare le chiusure approvate e annullate del mese selezionato;
- visualizzare data, numero, importi e documento associato;
- distinguere le chiusure approvate da quelle annullate;
- annullare una chiusura approvata quando il backend autorizza
  esplicitamente l'operazione tramite `can_annul`.

L'annullamento:
- è riservato al proprietario del bar e all'amministratrice globale
  autorizzata;
- richiede una motivazione non vuota;
- utilizza `POST /cash-closures/review/{id}/annul`;
- è protetto da autenticazione, CSRF e isolamento tra bar;
- conserva la chiusura e il documento originale;
- registra le informazioni di annullamento per la tracciabilità;
- esclude le chiusure annullate dai calcoli analytics pertinenti.

L'endpoint `GET /cash-closures/history?month=YYYY-MM`
restituisce lo storico del mese nel contesto del bar attivo.

Il frontend impedisce di utilizzare una conferma di annullamento
aperta per un bar differente. Durante il cambio bar o mese
non mostra dati del contesto precedente e ignora le risposte
tardive delle richieste precedenti.

In caso di errore di caricamento dello storico, viene mostrato
il pulsante **Riprova caricamento**, che ripete la lettura senza
modificare le chiusure.

Dopo un annullamento riuscito, lo storico viene aggiornato.
Un eventuale errore nel successivo aggiornamento della dashboard
non viene presentato come fallimento dell'annullamento.

La migrazione Alembic
`20261120_0017_add_cash_closure_annulment.py`
introduce i campi necessari alla tracciabilità.
Non applicare la migrazione al database originale senza
una verifica preventiva in ambiente di test e autorizzazione esplicita.

I test frontend sono in
`frontend/tests/cashClosureHistoryPage.test.mjs`
e coprono permessi, motivazione obbligatoria, cambio bar,
risposte tardive, aggiornamento dopo annullamento,
errori e tentativi di ricaricamento.

I test backend sono in
`backend/tests/test_cash_closure_annulment.py`.
