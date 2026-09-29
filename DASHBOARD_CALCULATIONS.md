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

## 2. Costi

Gli expenses del P&L comprendono esclusivamente le fatture che soddisfano tutte
queste condizioni:

1. `Invoice.status` è `paid`;
2. esiste almeno un `InvoicePaymentLink` per la fattura;
3. almeno uno dei pagamenti collegati ha una data rilevante nel periodo
   selezionato.

Per ogni fattura valida:

- il costo è `Invoice.total`;
- la fattura viene conteggiata una sola volta tramite `Invoice.id`;
- più link o più pagamenti sulla stessa fattura non duplicano il costo;
- un overpayment non aumenta il costo oltre `Invoice.total`.

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

## 9. Pagamenti per metodo

Questa sezione raggruppa i pagamenti per metodo nel mese selezionato.

- Fonte: record di `Payment`.
- Aggregazione: somma di `Payment.amount` raggruppata per `Payment.method`.
- Questa aggregazione descrittiva non aggiunge automaticamente i pagamenti agli
  expenses del P&L.

## 10. Problema fuori scope

Il modello attuale consente che lo stesso `Payment` venga collegato a fatture
diverse. Questo problema non viene risolto dal contratto P&L corrente e resta
fuori scope per questa modifica.