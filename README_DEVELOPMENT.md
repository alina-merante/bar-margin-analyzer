# Sviluppo e configurazione

## Avvio standard

    npm run dev:full

## GitHub Codespaces

    npm run dev:codespaces

Le migrazioni Alembic vengono applicate automaticamente
dalle procedure di avvio standard.

## Ambiente PWA isolato

    ./scripts/start-pwa-test.sh

- Backend: 127.0.0.1:8001
- Frontend: 127.0.0.1:5174
- Database: bar_margin_analyzer_pwa_test

Utilizzare esclusivamente configurazioni e credenziali
dedicate all'ambiente di test.

L'accesso remoto privato avviene tramite Tailscale.
Non esporre pubblicamente l'ambiente di test.

## Test frontend

    npm --prefix frontend test
    npm --prefix frontend run build
    npm --prefix frontend run lint

## Clean bootstrap

    sh scripts/verify-clean-bootstrap.sh

## Test di accettazione

Consultare [la guida dedicata](acceptance-tests/README.md).

## Workflow Git

1. Creare un branch dedicato alla funzionalità.
2. Implementare le modifiche.
3. Aggiornare i test e la documentazione pertinente.
4. Verificare le regressioni.
5. Eseguire commit e push.
6. Integrare in main soltanto dopo la validazione.

## Pulizia del repository

Non versionare credenziali, backup locali, report
temporanei, archivi di analisi e artefatti dei test.

Conservare invece test automatici, fixture riutilizzabili
e documentazione tecnica pertinente.

## Interfaccia utente

Tutti i testi destinati agli utenti devono essere
in italiano, inclusi errori, conferme, avvisi,
autorizzazioni e messaggi di caricamento.

I log tecnici possono essere in inglese.

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

## Migrazioni Alembic

Le migrazioni vengono applicate automaticamente prima dell'avvio dell'API:

- in Docker tramite `backend/docker-entrypoint.sh`;
- in Codespaces tramite `scripts/dev-codespaces.sh`.

Non è necessario eseguire una migrazione manuale durante l'avvio normale.

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
