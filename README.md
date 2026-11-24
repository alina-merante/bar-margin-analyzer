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

### Test PWA privato in Codespaces

Preparare **manualmente** PostgreSQL su `127.0.0.1:5432` con il database
esclusivo `bar_margin_analyzer_pwa_test`, le migrazioni e un utente applicativo.
Gli script non creano database né applicano migrazioni. Servono le dipendenze
backend e frontend già installate, MagicDNS e HTTPS abilitati nella tailnet.

Impostare `DATABASE_URL` nell'ambiente oppure creare il file locale ignorato
`scripts/.pwa-test.env`, leggibile solo dall'utente (`chmod 600`), contenente
una singola riga `DATABASE_URL=postgresql+psycopg2://.../bar_margin_analyzer_pwa_test`
senza virgolette. Usare credenziali proprie o `.pgpass`; codificare eventuali
caratteri speciali nell'URL. L'URL deve puntare a `localhost` o `127.0.0.1`
porta 5432 e non può contenere parametri. Non inserire segreti nei file
versionati. La variabile d'ambiente prevale sul file.

```bash
./scripts/start-pwa-test.sh
./scripts/stop-pwa-test.sh
```

Al primo avvio, aprire il link di autorizzazione Tailscale mostrato nel
terminale. Lo script usa un daemon userspace dedicato, stato persistente in
`~/.local/share/tailscale/barmanager-pwa-test` e Serve esclusivamente privato:
il link HTTPS indicato va aperto da un dispositivo autorizzato nella tailnet.
Se Tailscale non è installato, scarica i binari ufficiali 1.90.9 e ne verifica
il checksum SHA-256, senza privilegi amministrativi. Il daemon usa networking
userspace senza modificare il DNS del Codespace: il nome MagicDNS potrebbe non
risolversi nel terminale del Codespace anche quando funziona sulla tailnet.

Il backend ascolta solo su `127.0.0.1:8001`, Vite su `127.0.0.1:5174`;
i log privati e i PID sono in `~/.local/state/barmanager-pwa-test`. Gli upload
sono isolati in `$HOME/.local/share/barmanager-pwa-test/uploads`: se la directory esiste già,
deve appartenere all'utente e avere permessi `700`. Cookie Secure, controlli
CSRF e isolamento tenant restano attivi. L'arresto conserva database, upload e
stato Tailscale. Porte o socket già occupati da processi non gestiti producono
un errore: liberare i conflitti **manualmente**, solo dopo aver identificato
i processi, senza toccare i servizi principali.

## Porte e URL

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Swagger: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`

Vite inoltra le richieste `/api/*` a `http://127.0.0.1:8000`.

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

### Fondazione amministrazione globale e permessi

La migrazione additiva `20261112_0014` aggiunge `users.is_global_admin`,
predefinito a `false` anche per gli utenti esistenti, e la tabella
`membership_permissions`. Non cambia ruoli, membership o bar legacy e non
assegna permessi. Il privilegio globale è indipendente da email e ruolo owner.
Il downgrade rifiuta di procedere se esistono amministratrici globali o permessi:
la loro rimozione deve essere decisa e gestita esplicitamente prima del downgrade.

La nomina di un utente **esistente e attivo** è un'operazione amministrativa
locale, non un endpoint. Dopo la migrazione, da un ambiente con accesso
amministrativo controllato al database, configurare esplicitamente
`DATABASE_URL` per il database desiderato e avviare:

```bash
cd backend
.venv/bin/python -m app.promote_global_admin ID_UTENTE
```

Il comando mostra driver, host, porta e nome del database senza credenziali né
parametri di connessione, oltre all'utente; verificare entrambi e digitare
esattamente `PROMOTE ID_UTENTE` per confermare. Non crea
account, non richiede password utente e non promuove automaticamente gli owner.
Limitare accesso al comando, alle credenziali del database e all'ambiente
operativo a personale autorizzato.

I permessi sono righe univoche per membership: quindi uno stesso utente può
avere concessioni diverse nei diversi bar. I codici ammessi sono definiti in
`backend/app/permissions.py` e vincolati anche nello schema; codici sconosciuti
sono rifiutati. Nessun permesso viene assegnato automaticamente. Il catalogo
distingue documenti propri e di tutti, upload, creazione, modifica, revisione,
approvazione ed eliminazione dove applicabili, e lettura separata di incassi,
costi, pagamenti, profitti, margini e analytics. Non contiene un permesso
delegabile per approvare chiusure di cassa: la regola riserva tale
approvazione all'amministratrice globale o all'owner del bar.

**Questa è soltanto una fondazione, non l'enforcement dei nuovi permessi.**
Non esistono ancora API di gestione account, assegnazioni o permessi, né un
bypass operativo per l'amministratrice globale; i router usano ancora la matrice
owner/manager/staff descritta sotto. Analytics e altre letture economiche sono
ancora visibili allo staff del bar. L'approvazione delle chiusure è invece
limitata al proprietario o all'amministratore globale con accesso al bar.
Le nuove importazioni di cassa richiedono sempre la revisione manuale. L'accesso a
analytics non dovrà implicare accesso a dati economici non autorizzati, anche
quando ricavabili da aggregati. La distinzione dei propri documenti richiede
ancora la registrazione dell'autore e il controllo su API e download.
Il bar legacy con ID `-1` non viene modificato da questa migrazione. L'header
tenant accetta ID positivi e, come unica eccezione negativa, `-1`; restano
obbligatorie sessione, membership e autorizzazioni per il bar.

### API di amministrazione globale

La migrazione `20261112_0015` aggiunge il registro `admin_audit` e una riga di
serializzazione per le scritture amministrative. Le operazioni e il relativo
audit sono confermati nella stessa transazione; l'audit registra l'attore,
l'azione, i riferimenti al bar/account e le variazioni, mai password o token.
Il downgrade è bloccato se esistono eventi di audit, per evitare di perderli.

Le API `/admin/*` richiedono una sessione attiva di amministratrice globale,
verificata nel backend; non richiedono un bar attivo né `X-Expected-Bar-ID`.
Le scritture richiedono anche `Origin` autorizzato e `X-CSRF-Token`. La
protezione delle API operative e la loro matrice di ruoli rimangono invariate.

| Metodo e percorso | Operazione |
| --- | --- |
| `GET /admin/bars`, `POST /admin/bars` | Elenco, inclusi i disattivati; creazione con `name` |
| `GET /admin/bars/{id}`, `PATCH /admin/bars/{id}` | Dettaglio; modifica di `name` e/o `is_active` |
| `GET /admin/users`, `POST /admin/users` | Elenco; creazione con `email` |
| `GET /admin/users/{id}`, `PATCH /admin/users/{id}` | Dettaglio; modifica di `email` e/o `is_active` |
| `GET /admin/bars/{id}/memberships` | Elenco delle assegnazioni del bar |
| `POST /admin/bars/{id}/memberships` | Assegna `user_id` e ruolo `owner` o `staff` |
| `PATCH /admin/bars/{id}/memberships/{user_id}` | Cambia il ruolo in `owner` o `staff` |
| `DELETE /admin/bars/{id}/memberships/{user_id}` | Revoca l'assegnazione |

Non è possibile cambiare `is_global_admin` via API. L'ultimo amministratore
globale attivo non può essere disattivato. La disattivazione del bar non
elimina dati o membership; la revoca nega il successivo accesso tenant senza
cancellare i dati operativi. I ruoli `manager` storici restano visibili e non
sono convertiti automaticamente. La modifica del ruolo o la revoca elimina
anche gli eventuali permessi granulari associati alla vecchia membership.

La creazione dell'account normalizza l'email e genera una credenziale casuale
non comunicata, non utilizzabile dall'utente. La risposta indica
`password_setup_required`: **l'account non può ancora effettuare il login**.
Non esiste un servizio configurato per invito/reset password e nessun endpoint
di impostazione password è stato introdotto; serve un successivo flusso sicuro
prima dell'utilizzo degli account creati. Risposte e audit non contengono hash
o password. La disattivazione revoca tutte le sessioni non ancora revocate
dell'utente, anche quelle su altri dispositivi, nella stessa transazione della
modifica dello stato. La riattivazione non ripristina le vecchie sessioni:
è necessario un nuovo login.

L'amministratrice globale non ha ancora accesso operativo automatico a tutti i
bar, e i permessi granulari non sono ancora applicati alle API operative. Non
esistono ancora API di gestione dei permessi dei dipendenti né interfaccia
amministrativa. Le criticità di lettura economica descritte sopra restano aperte.

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

### Accesso dal frontend

Il frontend usa `/api/auth/csrf`, `/login`, `/session`, `/logout`, `/bars` e
`/active-bar` tramite il proxy Vite. Effettuare il login con un account attivo
già configurato, quindi selezionare un bar assegnato; la selezione può essere
cambiata dalla barra laterale. L'invito e il reset della password non sono
ancora disponibili. L'amministratrice globale non ha un bypass operativo:
per usare un bar serve comunque una membership.

Il cookie di sessione `HttpOnly` è gestito dal browser; la password e il token
CSRF non vengono salvati in localStorage. Il token CSRF rimane in memoria e
viene inviato nelle scritture; il browser invia `Origin` e il backend lo
confronta con `AUTH_ALLOWED_ORIGINS`. La sessione dura 12 ore per default
(`AUTH_SESSION_TTL_SECONDS`); logout o scadenza richiedono un nuovo accesso.
Per HTTPS configurare `AUTH_COOKIE_SECURE=true` e un secret stabile e sicuro.
In produzione il cookie Secure è obbligatorio.

Le richieste tenant includono `X-Expected-Bar-ID`, che verifica la coerenza
con la selezione nella sessione e **non** concede autorizzazioni. Il backend
continua a controllare sessione, membership, bar attivo e ruolo. Le richieste
senza header sono rifiutate (428), con ID non valido (400), bar non accessibile
(403) o bar attivo differente (409). Le API `/auth/*` non richiedono l'header.
Al cambio bar o logout il frontend chiude il vecchio contesto, annulla le
richieste pendenti e rimuove i dati visualizzati. L'annullamento nel browser
non garantisce l'interruzione di una scrittura già ricevuta dal server.
I file protetti sono richiesti
con lo stesso contesto e mostrati tramite URL blob temporanei revocati alla
chiusura; le richieste usano `no-store`.

Schede dello stesso browser condividono la sessione: una selezione fatta in
un'altra scheda può causare 409. Inoltre `/auth/csrf` ruota il token della
sessione e può invalidare quello in memoria in un'altra scheda. In questi casi
l'interfaccia richiede di ripristinare la sessione; un'operazione fallita non
viene ripetuta automaticamente. Browser o dispositivi con login distinti
mantengono sessioni indipendenti. Le scritture serializzano il contesto
sessione/bar/membership; upload e OCR lo ricontrollano prima del salvataggio.
I download protetti lo mantengono bloccato fino al termine dello streaming.

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

### Prova isolata e tablet Android

Per una prova locale con dati fittizi, scegliere porte libere e usare un
database e una directory upload temporanei, separati da quelli reali. Ad
esempio, dalla root, con le dipendenze già installate:

```bash
export BM_TEST_DIR="$(mktemp -d)"
export DATABASE_URL="sqlite:///$BM_TEST_DIR/app.db"
export UPLOAD_BASE_PATH="$BM_TEST_DIR/uploads"
export OPENAI_API_KEY=""
export AUTH_ALLOWED_ORIGINS="http://localhost:5173"
export AUTH_COOKIE_SECURE=false
cd backend
.venv/bin/python -c 'from app.database import Base, engine; import app.models; Base.metadata.create_all(engine)'
.venv/bin/python -m app.bootstrap_owner
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Il bootstrap va eseguito solo dopo aver verificato `DATABASE_URL`; inserire
credenziali e dati fittizi. `create_all` è utile solo per questa prova
temporanea, non sostituisce le migrazioni per ambienti reali. In un secondo
terminale avviare `npm --prefix frontend run dev -- --host 127.0.0.1` e
aprire `http://localhost:5173`. Il proxy Vite richiede l'API sulla porta
locale 8000. Non eseguire lo script Codespaces standard per questa prova:
applica migrazioni al database configurato. Eliminare successivamente solo la
directory temporanea creata per la prova.

Per verifiche automatiche isolate, dalla root:

```bash
npm --prefix frontend test
export BM_TEST_DIR="$(mktemp -d)"
export DATABASE_URL="sqlite:///$BM_TEST_DIR/app.db"
export UPLOAD_BASE_PATH="$BM_TEST_DIR/uploads"
export OPENAI_API_KEY=""
unset TEST_POSTGRESQL_URL TEST_PERMISSION_POSTGRESQL_URL TEST_ADMIN_MIGRATION_POSTGRESQL_URL TEST_ADMIN_RACE_POSTGRESQL_URL TEST_ADMIN_POSTGRESQL_URL
cd backend
.venv/bin/python -m pytest -p no:cacheprovider tests/test_bar_context.py tests/test_operational_tenant_scope.py tests/test_document_tenant_scope.py tests/test_finance_tenant_scope.py tests/test_analytics_tenant_scope.py tests/test_cash_closure_review.py -q
```

Una prova Chromium locale con backend SQLite e dati fittizi ha esercitato
login, ripristino sessione, dashboard, cambio bar, anteprima fattura protetta, riconciliazione e
scollegamento pagamento, upload e approvazione di una chiusura, logout e
sessione scaduta. L'estrazione OCR nella prova era simulata: qualità e
comportamento dell'OCR reale non sono così verificati.

#### Accesso privato da Codespaces

Per una prova con dati fittizi, configurare un database e una directory upload
temporanei come sopra, senza avviare lo script Codespaces che applica migrazioni.
Nel pannello **Ports** verificare manualmente che la porta frontend 5173 sia
privata; copiare il relativo URL HTTPS e aprirlo nel browser del tablet dopo
aver effettuato l'accesso con un account GitHub autorizzato al Codespace.
Prima di avviare il backend, impostare `AUTH_ALLOWED_ORIGINS` all'origine esatta
dell'URL HTTPS del frontend, senza percorso né barra finale, e
`AUTH_COOKIE_SECURE=true`. Avviare il frontend Vite e il backend sulla porta
locale 8000: il proxy `/api` inoltra le richieste al backend senza esporlo
direttamente. Non rendere pubblici frontend, API, database o upload.
Se Vite rifiuta l'host inoltrato, si può riavviare il frontend impostando
`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` al solo hostname esatto dell'URL
frontend, senza protocollo né percorso; non autorizzare indiscriminatamente
tutti gli host.

Il login usa cookie HttpOnly, CSRF e l'header di contesto tenant
`X-Expected-Bar-ID`; queste protezioni non vanno disabilitate. L'accesso
all'URL privato dal tablet, inclusi autenticazione GitHub, eventuale controllo
host di Vite, cookie e selezione del bar, richiede una prova reale: il
forwarding privato può richiedere passaggi manuali. Non è un deployment.

#### PWA e fotocamera

Il manifest BarManager indica apertura standalone, avvio da `/` e icone
192/512 px. Su Chrome Android, dall'URL HTTPS privato, usare il menu del browser
e scegliere **Installa app** o **Aggiungi a schermata Home**, se disponibile.
La disponibilità dell'installazione e il funzionamento dell'app installata con
l'autenticazione privata di Codespaces devono essere verificati sul dispositivo.

La connessione Internet rimane necessaria: non è registrato un service worker e
non è prevista alcuna cache offline di documenti, dati finanziari o risposte API.
La disconnessione impedisce l'accesso alle funzionalità.

In Carica documenti, **Scatta foto** è disponibile separatamente per chiusure di
cassa e fatture; un secondo pulsante per le fatture è presente nella pagina
Fatture. Il browser riceve la richiesta di utilizzare la fotocamera posteriore:
la scelta effettiva dipende da Android, browser e permessi. I selettori per
documenti esistenti restano disponibili. Le foto seguono gli stessi flussi
OCR e revisione già in uso per i file, con i relativi limiti e controlli;
per le chiusure il file originale oltre 20 MB viene rifiutato.

Una prova Chromium con viewport e tocco simulati, usando API e file fittizi, ha
verificato login, cambio bar, dashboard, pagamenti, caricamento, revisione e
controlli fotocamera. Non verifica fotocamera nativa, OCR reale o installazione
Android. Touch, orientamento, tastiera, accesso privato e acquisizione vanno
ancora provati sul tablet. I permessi granulari restano da applicare alle API
operative; l'approvazione delle chiusure segue la restrizione descritta sopra.

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
assegnandoli al bar attivo. Ogni chiusura riconosciuta resta in attesa di
revisione e approvazione esplicita, anche se tutti i campi sono stati letti.
Per approvare servono data, numero di chiusura e totale: se mancanti, inserirli
solo dopo verifica sul documento. Il totale scontrini è mostrato separatamente
e non viene considerato il totale complessivo. Risponde:

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

### Recupero automatico del processo Tailscale

All'avvio dell'ambiente PWA, se il socket Tailscale esiste ma il
file PID è mancante o non valido, lo script tenta di recuperare
il processo già attivo.

Il recupero è consentito soltanto quando viene identificato
un unico processo compatibile con la configurazione BarManager,
verificando proprietario, eseguibile, argomenti di avvio,
marcatore `BARMANAGER_PWA_PROCESS=tailscaled` e tempo di avvio.

Se le verifiche falliscono, l'avvio rimane bloccato per sicurezza.
Non vengono cancellati socket, stato Tailscale, database o upload.

La procedura è stata verificata anche con un test reale di
recupero del file PID mancante.

### Clean Bootstrap autenticato

Il workflow GitHub Actions `Clean Bootstrap` verifica le migrazioni
Alembic, l'avvio del backend, gli endpoint della dashboard e la build
del frontend in un ambiente PostgreSQL temporaneo.

Gli endpoint protetti sono verificati tramite
`scripts/verify-clean-bootstrap-auth.py`, che crea un utente e un bar
di test, effettua il login con protezione CSRF e controlla gli endpoint
con una sessione autenticata.

Lo script è riservato a GitHub Actions e verifica il nome e l'host del
database prima di creare dati temporanei. Non utilizza credenziali o
database dell'ambiente PWA.

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


### Permessi di rifiuto delle chiusure OCR

Le chiusure in attesa possono essere revisionate e corrette da utenti con
permesso `REVIEW_OCR`. L'approvazione e il rifiuto definitivo sono invece
riservati al proprietario del bar o all'amministratore globale.
Il backend applica il controllo a entrambe le operazioni; il frontend
mostra il pulsante Rifiuta soltanto agli utenti autorizzati.
Sono previsti test di regressione per il blocco del rifiuto da parte
di staff e manager.

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

### API amministrativa: permessi granulari

L'API amministrativa restituisce `permissions` nelle risposte
relative alle membership.

Un amministratore globale può assegnare o revocare i permessi
delegabili mediante:

`PUT /admin/bars/{bar_id}/memberships/{user_id}/permissions`

Esempio di corpo JSON:

`{"permissions": ["revenue.view", "costs.view"]}`

Un elenco vuoto revoca tutti i permessi delegati.
Le modifiche vengono registrate nell'audit amministrativo.
Non è possibile modificare i permessi del proprietario.

Nota: la configurazione dei permessi non costituisce ancora
protezione delle API operative. L'applicazione delle autorizzazioni
e l'adeguamento del frontend saranno completati nei passaggi
successivi.


### Protezione delle API analytics

Gli 11 endpoint `/analytics` richiedono autorizzazioni granulari
per gli utenti non proprietari del bar.

I permessi vengono verificati sul backend prima di elaborare i dati.
Il permesso `analytics.view` non autorizza automaticamente
la visualizzazione di fatturato, costi, pagamenti o profitti.

Il proprietario conserva l'accesso completo ai dati del proprio bar.
Le approvazioni delle chiusure di cassa restano separate
dai permessi di visualizzazione finanziaria.

La protezione delle altre API finanziarie e l'adeguamento
della dashboard per gli utenti con accesso limitato
devono ancora essere completati.

I test in `backend/tests/test_financial_permissions.py`
verificano la logica dei permessi e la presenza dei controlli
negli endpoint; non sostituiscono i test HTTP di integrazione.


### Permessi nel contesto del bar

Le risposte di `/auth/bars` e `/auth/active-bar` includono
il campo `permissions`, contenente i permessi delegati
all'utente per il bar selezionato.

La lettura di `/api/payments` richiede `payments.view`
per gli utenti non proprietari.

Il frontend e gli altri endpoint finanziari devono
ancora essere adeguati.


### Dashboard e permessi frontend

La dashboard completa è visibile ai proprietari e agli utenti
che possiedono contemporaneamente `analytics.view`,
`revenue.view`, `costs.view` e `profit.view`.

Per gli altri utenti, la route `/dashboard` reindirizza
a `/upload` e il caricamento dei dati della dashboard
viene saltato.

Questa è una prima protezione dell'interfaccia.
Restano da implementare la visualizzazione parziale
dei dati, i controlli sulle fatture e i test end-to-end.


### Tracciabilità autore fatture e documenti

La migrazione Alembic `20261118_0016` introduce il campo
`created_by_user_id` nelle tabelle `invoices` e `documents`.

- Il campo è facoltativo per mantenere compatibili i record storici.
- Le nuove fatture manuali e OCR registrano l'utente autenticato.
- I nuovi documenti caricati registrano l'utente autenticato.
- Le importazioni bancarie CSV registrano l'utente autenticato.
- L'eliminazione dell'utente imposta il riferimento a NULL,
  senza eliminare automaticamente fatture o documenti.
- I record storici senza autore non devono essere attribuiti
  automaticamente a un dipendente.
- La migrazione deve essere verificata esclusivamente su un
  database di test prima di qualsiasi applicazione altrove.

**Stato:** modelli e percorsi di creazione aggiornati.
Migrazione non ancora applicata; autorizzazioni di lettura
`view_own` e `view_all` ancora da completare.


### Permessi granulari di lettura

Gli endpoint `GET /invoices` e `GET /documents`
applicano i permessi granulari di lettura.

- `view_all`: tutti i record del bar autorizzato.
- `view_own`: solo record con `created_by_user_id`
  corrispondente all'utente autenticato.
- Senza permesso: HTTP 403.
- Proprietario e amministratrice globale autorizzata:
  accesso completo.
- I record storici privi di autore non sono visibili
  tramite `view_own`.
- I dettagli dei pagamenti delle fatture richiedono
  anche `payments.view`.

La migrazione `20261118_0016` deve essere applicata
esclusivamente al database di test prima dei test
di integrazione che utilizzano le nuove colonne.


### Protezione download granulari

L'endpoint `/uploads/{kind}/{filename}` verifica i permessi
granulari prima di restituire fatture, documenti e anteprime.

- Fatture: `invoices.view_own` oppure `invoices.view_all`.
- Documenti e anteprime: `documents.view_own` oppure
  `documents.view_all`.
- Con `view_own`, tutti i record associati al file devono
  appartenere all'utente autenticato.
- Restano obbligatori i controlli sul bar attivo, sulla
  validità dei riferimenti e sulla sicurezza del filesystem.
- I record storici senza autore non sono accessibili
  tramite `view_own`.


### Permessi granulari per la revisione delle chiusure

Nel branch `feature/granular-permissions` sono stati introdotti
controlli granulari per le operazioni sulle chiusure di cassa.

- `cash_closures.review`: accesso alla revisione OCR.
- `cash_closures.edit`: correzione dei valori e rielaborazione OCR.
- Approvazione e rifiuto definitivi: riservati al proprietario
  del bar e all'amministratore globale.

La separazione dei permessi di visualizzazione `view_own` e
`view_all`, la verifica completata e i relativi test di
autorizzazione sono ancora da implementare.

Le modifiche non richiedono migrazioni del database.

- `cash_closures.view_own`: visualizzazione delle chiusure caricate personalmente.
- `cash_closures.view_all`: visualizzazione delle chiusure di tutto il bar.
- L'elenco e il dettaglio applicano i permessi di lettura nel backend.

- Le operazioni di correzione e rielaborazione OCR verificano anche l'accesso alla singola chiusura secondo i permessi `view_own` e `view_all`.


### Verifica completata delle chiusure OCR

Endpoint `POST /cash-closures/review/{intake_id}/verify`:
registra in `ocr_values.verification` l'identificativo
dell'utente verificatore e la data/ora UTC.

Richiede `cash_closures.review` e il permesso di lettura
della specifica chiusura. Non approva la chiusura:
lo stato resta `pending`.

Da completare prima dell'utilizzo operativo:
invalidazione della verifica dopo correzioni o rielaborazioni,
test delle transizioni, interfaccia e regole di approvazione.

- Una correzione dei valori o una rielaborazione OCR annulla la verifica precedente: occorre verificare nuovamente la chiusura prima dell'approvazione.

- L'approvazione di una chiusura `pending` richiede una verifica valida registrata in `ocr_values.verification`. L'approvazione rimane riservata al proprietario e all'amministratore globale.


### Test di sicurezza verifica chiusure

I test backend verificano registrazione dell'utente e della data,
rifiuto delle verifiche duplicate, invalidazione dopo correzioni,
obbligatorietà dei campi e divieto di approvazione per lo staff.


### Controlli aggiuntivi OCR e approvazione

Sono stati aggiunti controlli di regressione per la sostituzione
dei metadati OCR e per il divieto di approvazione da parte dello staff.
L'approvazione resta riservata al proprietario e all'amministratore globale.


### Verifica endpoint HTTP chiusure

Sono presenti test per verificare che l'endpoint POST
`/cash-closures/review/{intake_id}/verify` sia registrato
e che una richiesta priva di autenticazione venga rifiutata.


### Sicurezza rielaborazione OCR

Dopo la rivalidazione dei permessi, gli endpoint di anteprima
e conferma OCR ricontrollano l'accesso alla specifica chiusura.

La conferma OCR invalida sempre la verifica precedente,
anche se i metadati estratti contengono il campo `verification`.

L'approvazione rimane riservata al proprietario del bar
o all'amministratore globale e richiede una verifica valida.


### Verifica e permessi delle chiusure nel frontend

La scheda di revisione espone i permessi `can_edit` e `can_verify`
restituiti dal backend. I campi sono di sola lettura senza permesso
di modifica; correzione e rielaborazione OCR sono riservate agli
utenti autorizzati.

Il pulsante "Verifica completata" invoca l'endpoint di verifica.
L'approvazione resta riservata al proprietario del bar o
all'amministratore globale e richiede una verifica precedente.

I controlli frontend non sostituiscono quelli applicati dal backend.


### Autorizzazioni granulari per il caricamento documenti

L'endpoint `POST /documents/upload` richiede il permesso
generale di ruolo `UPLOAD_DOCUMENTS` e il permesso
granulare relativo alla sezione:

- `cash` e `cash_closure`: `cash_closures.upload`
- `bank` e `other`: `documents.upload`

Le sezioni non riconosciute vengono rifiutate.
I permessi sono ricontrollati durante l'elaborazione,
anche dopo la rivalidazione del contesto utente.

L'approvazione e il rifiuto delle chiusure restano
riservati al proprietario e all'amministratrice globale.


### Eliminazione fatture con permessi granulari

L'endpoint `DELETE /invoices/delete/{invoice_id}` richiede
il permesso delegabile `invoices.delete`.

Il proprietario del bar e l'amministratore globale sono
autorizzati automaticamente. Manager e staff devono ricevere
esplicitamente il permesso.

L'eliminazione è limitata alle fatture del bar attivo.
Le fatture con pagamenti riconciliati non possono essere eliminate.

Test HTTP: `backend/tests/test_invoice_delete_permissions.py`.


### Protezione documenti di chiusure approvate

L'eliminazione di un documento collegato a una
`CashClosureIntake` con stato `approved` è bloccata
con HTTP 409.

La chiusura approvata e il documento originale devono
essere conservati. L'eventuale annullamento avviene tramite
l'operazione tracciata descritta nella sezione seguente,
senza eliminazione definitiva.


### Eliminazione documenti con permessi granulari

L'endpoint `DELETE /documents/{document_id}` applica permessi
granulari in base alla tipologia del documento:

- `documents.delete` per documenti generici e bancari;
- `cash_closures.delete` per documenti di cassa;
- proprietario e amministratore globale autorizzati automaticamente;
- manager e dipendenti autorizzati solo con permesso esplicito.

La classificazione considera sia la sezione del documento sia
i collegamenti a `CashClosureIntake` e `DailyCashClosure`.

Restano attivi i controlli di isolamento tra bar e il divieto
di eliminazione definitiva delle chiusure approvate.


### Test di delega eliminazione documenti

I test verificano che il ruolo manager non conferisca
automaticamente il diritto di eliminare documenti.
L'operazione è consentita soltanto dopo l'assegnazione
esplicita del permesso `documents.delete`, mantenendo
i controlli CSRF e l'isolamento tra bar.


### Visibilità eliminazione nello storico documenti

Nello storico della pagina Upload, il pulsante di eliminazione è
mostrato soltanto se l'utente dispone del permesso delegabile
corrispondente: `invoices.delete` per le fatture,
`documents.delete` per documenti generici e bancari,
`cash_closures.delete` per documenti di cassa.

Il frontend controlla i permessi anche prima di invocare
le funzioni di eliminazione. Il backend rimane l'autorità
per autorizzazione, isolamento tenant e protezione delle
chiusure approvate: queste ultime non possono essere
eliminate definitivamente, anche quando il pulsante è visibile.


### Test automatici dei permessi di eliminazione

La suite backend verifica le autorizzazioni granulari per
l'eliminazione di fatture, documenti e chiusure di cassa,
inclusi isolamento tra bar, CSRF e divieto di eliminazione
definitiva delle chiusure approvate.

La suite frontend include
`frontend/tests/upload-delete-permissions.test.mjs`,
eseguita tramite `npm test`, che verifica la funzione
`canDeleteHistoryEntry` utilizzata nella pagina Upload.

Sono coperti i seguenti casi:
- utente senza permessi di eliminazione;
- permesso `documents.delete`;
- permesso `cash_closures.delete`;
- permesso `invoices.delete`;
- proprietario del bar;
- assenza delle funzioni di eliminazione.

I controlli frontend regolano la visibilità dei pulsanti,
mentre l'autorizzazione effettiva resta responsabilità
del backend.

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


### Acceptance Test

Gli scenari di accettazione manuali sono documentati in `acceptance-tests/scenarios/`, con descrizione, procedura, risultato atteso ed esito effettivo. I report delle esecuzioni sono conservati in `acceptance-tests/reports/`. Le verifiche devono utilizzare un database isolato.


### Acceptance test AT-007 - Autenticazione e navigazione

Lo scenario `acceptance-tests/scenarios/AT-007-login-logout-navigation.md`
documenta la verifica di login, logout, rinnovo CSRF e navigazione.

I test automatici dedicati sono in
`frontend/tests/authNavigation.test.mjs` e si eseguono con
`npm --prefix frontend test`.

La verifica manuale preliminare è riuscita. Sono superati
7 test di regressione frontend e 3 test comportamentali React,
inclusi i casi di logout riuscito e fallito.

I test non costituiscono ancora una verifica browser end-to-end
completa; i casi di sessione scaduta e concorrenza tra schede
restano da coprire.

### Accesso PWA di test tramite GitHub Codespaces

Lo script `scripts/start-pwa-test.sh` autorizza esplicitamente
sia l'origine HTTPS Tailscale sia l'origine HTTPS della porta 5174
di GitHub Codespaces, quando `CODESPACE_NAME` è disponibile.

Restano attivi i controlli CSRF e i cookie Secure.
Quando cambia la configurazione delle origini, arrestare
l'ambiente con `scripts/stop-pwa-test.sh` e riavviarlo.

Vite autorizza esplicitamente entrambi gli hostname.
