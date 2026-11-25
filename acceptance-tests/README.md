# Acceptance Test - BarManager
Test di accettazione eseguiti tramite interfaccia grafica, su un database isolato.

## Scenari disponibili

- `AT-001-login.md`: Accesso a BarManager.
- `AT-002-storico.md`: Storico delle chiusure.
- `AT-003-annullamento.md`: Annullamento di una chiusura.
- `AT-004-kpi.md`: Aggiornamento KPI.
- `AT-005-permessi.md`: Controllo dei permessi.
- `AT-006-isolamento-bar.md`: Isolamento tra bar.
- `AT-007-login-logout-navigation.md`: Login, logout, CSRF e navigazione.

## Stati dei test

- NOT RUN: non eseguito.
- PASS: superato.
- FAIL: fallito.
- BLOCKED: non eseguibile.

I test devono essere eseguiti esclusivamente su ambienti isolati.

## Ultima regressione — 25 novembre 2026

| Suite | Superati | Falliti |
| --- | ---: | ---: |
| Frontend | 236 | 0 |
| Autenticazione Playwright | 16 | 0 |
| Chiusure di cassa Playwright | 10 | 0 |
| Permessi, isolamento e interfaccia Playwright | 24 | 0 |
| Totale | 286 | 0 |

Build frontend completata con successo.

### Copertura aggiuntiva AT-UI

- AT-UI.01: identità amministratore globale.
- AT-UI.02: identità proprietario.
- AT-UI.03: identità dipendente.
- AT-UI.04: apertura e chiusura del selettore bar.
- AT-UI.05: accessibilità da tastiera.
- AT-UI.06: chiusura cliccando all'esterno.

Tutti i sei scenari sono stati superati.

### Ripristino ambiente

Le chiusure sintetiche annullate durante i test sono
state ripristinate correttamente.

Ricavi attesi di novembre: 2255,00 euro.

### Verifiche ancora aperte

- Revisione responsive complessiva.
- Verifica su dispositivi fisici.
- Controllo integrale dei testi dell'interfaccia in italiano.
- Validazione OCR su documenti reali eterogenei.

Il risultato di questa regressione non costituisce
una nuova esecuzione completa della suite backend.
