# AT-007 - Login, logout e navigazione

## Obiettivo
Verificare la navigazione dopo una nuova autenticazione, la permanenza
sulla pagina corrente durante il refresh e il logout protetto da CSRF.

## Prerequisiti
- Ambiente PWA isolato.
- Utente di test autorizzato.
- Nessun accesso al database originale.

## Scenari
1. Da Fatture effettuare logout e nuovo login: apertura Dashboard.
2. Da Caricamenti effettuare logout e nuovo login: apertura Dashboard.
3. Da Storico effettuare logout e nuovo login: apertura Dashboard.
4. Aggiornare Fatture con sessione valida: permanenza su Fatture.
5. Effettuare logout dopo una rotazione del token CSRF: nessun errore 403.
6. Verificare che un errore di logout sia mostrato all'utente.
7. Verificare il reindirizzamento alla prima pagina autorizzata.
8. Verificare che una sessione scaduta richieda nuova autenticazione.

## Test automatici
- `frontend/tests/authNavigation.test.mjs`
- `frontend/tests/authShellBehavior.test.mjs`
- `backend/tests/test_auth_foundation.py`

I test frontend AT-007 verificano le regole presenti nel codice e
il comportamento del client HTTP simulato. Non sostituiscono un test
browser end-to-end né verificano tutti gli scenari di errore.

## Verifica manuale preliminare
L'utente ha confermato il corretto funzionamento del flusso
login/logout e navigazione nell'ambiente PWA.

## Esito complessivo
PASS PARZIALE - verifica manuale preliminare confermata.

Test automatici:
- 7/7 test di regressione frontend superati.
- 3/3 test comportamentali React superati.
- Logout riuscito, logout rifiutato e rinnovo CSRF fallito verificati.

Restano da automatizzare:
- Navigazione completa in browser end-to-end.
- Scadenza della sessione.
- Conflitti tra schede.
