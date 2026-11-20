# AT-005 - Controllo dei permessi

## Descrizione
Verifica che proprietario e amministratore globale possano annullare le chiusure, ma i dipendenti no.

## Prerequisiti
- Ambiente di test isolato.
- Utenti e dati di prova predisposti.

## Procedura
1. Accedere come proprietario.
2. Verificare la disponibilità dell'annullamento.
3. Accedere come dipendente.
4. Verificare che l'annullamento non sia consentito.
5. Verificare il rifiuto dell'operazione anche dal backend.

## Risultato atteso
Solo i ruoli autorizzati possono annullare.

## Risultato effettivo
Da verificare.

## Esito
NOT RUN

## Note e anomalie
Nessuna verifica ancora eseguita.
