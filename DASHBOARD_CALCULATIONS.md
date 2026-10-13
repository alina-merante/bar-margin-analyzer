# Calcoli del dashboard

Questo documento descrive le formule usate dal dashboard e il contratto
applicativo del P&L.

## 1. Ricavi

I ricavi sono la somma delle chiusure di cassa comprese nel periodo selezionato.

- Fonte: `DailyCashClosure.total_amount`.
- Filtro temporale: `DailyCashClosure.date` compresa nel periodo.
- Formula: `Revenue = somma(DailyCashClosure.total_amount)`.

Le righe `SaleLine` sono usate per le analisi dei prodotti, ma non determinano
il revenue del P&L.

Le chiusure importate dal normale endpoint `POST /documents/upload` hanno data e
numero di chiusura validi e hanno superato il controllo duplicati
(`UNIQUE(date, closure_number)`), quindi la stessa chiusura non viene sommata
due volte. Il database non impedisce però un inserimento diretto con
`closure_number` NULL. Se l'importo non viene estratto dal documento, la
chiusura è salvata con totale `0.00` e contribuisce zero ai ricavi.

## 2. Costi

Gli expenses del P&L comprendono esclusivamente le fatture che soddisfano tutte
queste condizioni:

1. `Invoice.status` è `paid`;
2. esiste almeno un `InvoicePaymentLink` per la fattura;
3. la somma dei pagamenti collegati raggiunge `Invoice.total`.

Per ogni fattura valida:

- il costo è `Invoice.total`;
- la fattura viene conteggiata una sola volta tramite `Invoice.id`;
- il costo viene attribuito al mese della data del pagamento che completa il
  saldo; nell'implementazione tale data è la più recente tra i `Payment` collegati;
- gli acconti non generano costi finché la fattura non è completamente pagata;
- un overpayment viene rifiutato dagli endpoint e non può aumentare il costo
  oltre `Invoice.total`.

Esempio: per una fattura da 420 €, un acconto di 200 € a luglio e il saldo di
220 € ad agosto, luglio registra 0 € di costo e agosto registra 420 €.

`Invoice.total` rappresenta il totale finale/lordo del documento, comprensivo di
IVA quando applicabile. `Invoice.vat` rappresenta la quota IVA già contenuta
nel totale e non viene sommata nuovamente.

Non generano automaticamente costi:

- una fattura `pending`;
- una fattura `paid` senza `InvoicePaymentLink`;
- una fattura con link ma ancora `pending`;
- un `Payment` isolato;
- una `Transaction` bancaria negativa isolata.

Le `Transaction` bancarie negative non vengono sommate direttamente nel P&L.
Il fatto che un movimento bancario abbia importo negativo non è sufficiente a
generare un expense.

## 3. Profitto operativo

Il profitto operativo è la differenza tra ricavi e costi:

`Profit = Revenue - Expenses`

## 4. Trend P&L

L'endpoint del trend restituisce i valori mensili degli ultimi N mesi, incluso
il mese selezionato.

Ogni mese applica le stesse regole:

- `Revenue = somma delle chiusure cassa del mese`;
- `Expenses = somma di Invoice.total` delle sole fatture paid e riconciliate
  rilevanti nel mese;
- `Profit = Revenue - Expenses`.

## 5. Insight

Gli insight confrontano il mese selezionato con il mese precedente e includono:

- variazione percentuale dei ricavi;
- variazione percentuale dei costi;
- variazione percentuale del profitto;
- variazione percentuale della categoria di spesa principale;
- contributo percentuale del fornitore principale sulle spese totali.

Le sezioni relative a categoria, fornitore e ai relativi insight sono ancora
placeholder o incomplete nell'API e possono restituire liste vuote.

## 6. Spese per categoria

Questa sezione è prevista per distribuire gli expenses delle fatture
riconciliate per categoria. L'endpoint corrispondente è ancora placeholder o
incompleto e può restituire una lista vuota.

## 7. Spese per fornitore

Questa sezione è prevista per distribuire gli expenses delle fatture
riconciliate per fornitore. L'endpoint corrispondente è ancora placeholder o
incompleto e può restituire una lista vuota.

## 8. Riepilogo fatture

Questa sezione non fa parte della formula P&L: riepiloga i record delle fatture.

Valori mostrati:

- totale fatture;
- fatture in sospeso;
- fatture pagate;
- totale importo in sospeso;
- totale importo pagato.

Il numero "Da pagare" comprende tutte le fatture con saldo residuo, incluse
quelle già scadute; "Di cui scadute" è un sottoinsieme e non va sommato di
nuovo. Le fatture pagate sono quelle riconciliate a saldo. L'importo "Da
pagare" considera il residuo di ogni fattura non saldata:

`remaining_amount = max(0, Invoice.total - linked_amount)`

`linked_amount` è la somma dei `Payment.amount` collegati tramite
`InvoicePaymentLink`. Il totale pending è la somma dei residui, non dei totali
lordi delle fatture.

## 9. Stati delle fatture e arretrati

Lo stato di pagamento è confermato solo quando la fattura risulta pagata e i
pagamenti effettivamente collegati coprono il totale. Una fattura senza
pagamento registrato non è pagata anche se ha una scadenza passata.

Rispetto alla data odierna:

- **Pagata**: saldo coperto da pagamenti registrati;
- **Da pagare**: saldo residuo maggiore di zero, indipendentemente dalla
  scadenza;
- **Scaduta**: sottoinsieme di "Da pagare" con scadenza precedente a oggi;
- **In scadenza**: "Da pagare" non scaduta con scadenza entro 5 giorni (oggi
  incluso);
- **Futura non urgente**: "Da pagare" non scaduta con scadenza oltre 5 giorni.

La soglia di 5 giorni determina solo l'evidenziazione urgente e non riduce il
conteggio o l'importo "Da pagare". Le date di scadenza sono date civili: i
confronti non dipendono dall'ora del giorno o dal fuso orario.
Il totale documentale resta la somma degli importi originali delle fatture;
per il debito residuo si sottraggono i pagamenti collegati. Pertanto il totale
fatture è dato da fatture pagate più fatture con saldo ancora da saldare, senza
aggiungere una seconda volta le scadute.

I riepiloghi mensili e i filtri della pagina Fatture usano il mese di scadenza
selezionato. "Arretrati ANNO" include solo fatture non pagate e già scadute,
dello stesso anno selezionato e con scadenza in un mese precedente. Una fattura
scaduta nel mese selezionato resta nel filtro mensile "Scadute" e non viene
duplicata negli arretrati.

## 10. Pagamenti per metodo

Questa sezione raggruppa i pagamenti per metodo nel mese selezionato.

- Fonte: record di `Payment`.
- Aggregazione: somma di `Payment.amount` raggruppata per `Payment.method`.
- Questa aggregazione descrittiva non aggiunge automaticamente i pagamenti agli
  expenses del P&L.

## 11. Vincoli di riconciliazione

- Una `Transaction` può essere associata al massimo a un `Payment` tramite
  `Payment.transaction_id`, nullable e UNIQUE.
- Un `Payment` può essere collegato a una sola `Invoice`; il vincolo UNIQUE su
  `InvoicePaymentLink.payment_id` impedisce il riuso.
- Una fattura può avere più `Payment`, così da rappresentare pagamenti parziali.
- Una `Transaction` bancaria negativa isolata non genera un costo. I candidati
  vengono proposti in sola lettura e diventano pagamenti solo dopo conferma
  esplicita dell'utente.
