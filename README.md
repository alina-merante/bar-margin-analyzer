# BarManager — Bar Margin Analyzer

Applicazione web multi-tenant per la gestione operativa
ed economica dei bar.

## Funzionalità

- Dashboard economica e indicatori di redditività.
- Gestione fatture, scadenze e pagamenti.
- Importazione movimenti bancari e dati POS.
- Riconciliazione bancaria.
- Caricamento documenti e acquisizione fotografica.
- Estrazione OCR, revisione e verifica delle chiusure di cassa.
- Approvazione, storico e annullamento tracciato delle chiusure.
- Gestione multi-bar con ruoli e permessi granulari.
- Autenticazione e protezione delle sessioni.
- Interfaccia PWA utilizzabile tramite browser.

## Stack tecnologico

| Componente | Tecnologia |
| --- | --- |
| Frontend | React, Vite |
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy |
| Migrazioni | Alembic |
| OCR | Tesseract, Poppler, Pillow |
| Test | Pytest, Node Test Runner, Playwright |
| Ambiente | Docker, GitHub Codespaces |

## Avvio rapido

### Docker

    npm run dev:full

### GitHub Codespaces

    npm run dev:codespaces

### Servizi

| Servizio | Indirizzo |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

## Ruoli e sicurezza

- Amministratore globale: accesso ai bar attivi.
- Proprietario: accesso completo ai propri bar.
- Responsabile e dipendente: accesso secondo i permessi assegnati.

Le autorizzazioni sono applicate dal backend.
I dati operativi sono isolati per bar.

Approvazione, rifiuto definitivo e annullamento delle
chiusure sono riservati al proprietario e
all'amministratore globale.

## Test

I test devono utilizzare esclusivamente ambienti isolati.

    npm --prefix frontend test
    npm --prefix frontend run build

Per le procedure backend e Playwright consultare
la documentazione di sviluppo e accettazione.

## Documentazione

- [Architettura](README_ARCHITECTURE.md)
- [Sicurezza e autorizzazioni](README_SECURITY.md)
- [Sviluppo e configurazione](README_DEVELOPMENT.md)
- [Guida demo](README_DEMO.md)
- [Calcoli economici](DASHBOARD_CALCULATIONS.md)
- [Frontend](frontend/README.md)
- [Test di accettazione](acceptance-tests/README.md)

## Convenzioni di sviluppo

- Main riservato alle versioni validate.
- Branch dedicati alle singole macrofunzionalità.
- Test di regressione prima dell'integrazione.
- Documentazione aggiornata insieme al codice.
- Interfaccia utente interamente in italiano.
- Credenziali, backup e report temporanei esclusi da Git.
- Nessuna modifica ai database reali senza autorizzazione.

## Stato del progetto

Le funzionalità principali sono implementate e sottoposte
a test automatici.

Restano da completare la revisione responsive complessiva,
la verifica dell'interfaccia in italiano, il pannello
amministrativo frontend e il flusso di attivazione account.

L'accuratezza OCR su documenti reali eterogenei e
l'utilizzo su dispositivi fisici richiedono ulteriori verifiche.

Alcuni analytics per categoria e fornitore sono incompleti.
