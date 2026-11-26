# Sicurezza e autorizzazioni

## Autenticazione

- Autenticazione mediante sessioni server-side.
- Protezione CSRF delle operazioni di modifica.
- Limitazione dei tentativi di autenticazione.
- Invalidazione delle sessioni revocate.
- Protezione delle operazioni provenienti da schede obsolete.

Il frontend gestisce la scadenza della sessione e il
rinnovo del token CSRF senza ripetere operazioni appartenenti
a un'altra sessione.

## Ruoli

| Ruolo | Ambito |
| --- | --- |
| Amministratore globale | Tutti i bar attivi |
| Proprietario | Bar di appartenenza |
| Responsabile | Permessi assegnati |
| Dipendente | Permessi assegnati |

L'amministratore globale non necessita di una membership
per accedere ai bar attivi.

## Isolamento multi-tenant

Il backend verifica la sessione, il bar attivo e le
autorizzazioni dell'utente.

La selezione del bar nel frontend non costituisce
un'autorizzazione sufficiente.

Le richieste associate a una sessione o a un bar non
più corrispondente al contesto attivo vengono respinte.

## Permessi granulari

Le autorizzazioni riguardano:

- Consultazione degli indicatori economici.
- Lettura di fatture e documenti.
- Caricamento e download dei documenti.
- Revisione delle chiusure di cassa.
- Eliminazione di fatture e documenti.

La visibilità dei comandi nel frontend rispetta i
permessi, ma il controllo decisivo avviene nel backend.

## Chiusure di cassa

L'approvazione richiede verifica esplicita dei dati.

Approvazione e annullamento sono riservati al proprietario
e all'amministratore globale autorizzato.

Le chiusure approvate sono protette dalle eliminazioni
e dalle modifiche non consentite.

L'annullamento richiede una motivazione e conserva
lo storico e la tracciabilità dell'operazione.

## Verifiche

Consultare [i test di accettazione](acceptance-tests/README.md).

Non utilizzare credenziali reali o database di produzione
per le verifiche automatiche.

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
