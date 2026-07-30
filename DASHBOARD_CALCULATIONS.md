# Calcoli del dashboard

Questo documento descrive come vengono calcolate le varie sezioni del dashboard.

## 1. Ricavi

I ricavi corrispondono alla somma di tutte le chiusure di cassa del periodo selezionato.

- Fonte: DailyCashClosure.total_amount
- Filtro temporale: la chiusura è inclusa se la sua data rientra nel mese selezionato
- Formula:
  - Ricavi = somma(DailyCashClosure.total_amount)

## 2. Costi

I costi vengono conteggiati combinando due fonti:

1. Fatture pagate e riconciliate
2. Movimenti bancari con importo negativo, che rappresentano spese

Regole:
- Una singola fattura non genera costo fino a quando non è pagata.
- Un movimento bancario da solo non genera costo se è positivo o se non rappresenta una spesa.
- Le spese negative dei movimenti bancari vengono incluse nel totale dei costi.
- Per le fatture, il costo contribuisce come invoice.total + invoice.vat quando la fattura è pagata e ha almeno un pagamento collegato nel periodo.

Calcolo:
- Per ogni fattura pagata con almeno un pagamento collegato nel periodo:
  - contributo costo = invoice.total + invoice.vat
- Per ogni movimento bancario nel periodo con amount < 0:
  - contributo costo = abs(amount)
- Totale costi = somma dei contributi sopra indicati

## 3. Margine operativo

Il margine operativo è la differenza tra ricavi e costi.

- Formula:
  - Margine operativo = Ricavi - Costi

## 4. Trend P&L

L’endpoint del trend restituisce i valori mensili degli ultimi N mesi, incluso il mese selezionato.

Ogni mese usa la stessa logica:
- Ricavi = somma delle chiusure di cassa del mese
- Costi = somma delle fatture pagate e dei movimenti bancari negativi del mese
- Profitto = Ricavi - Costi

## 5. Insight

Gli insight confrontano il mese selezionato con il mese precedente.

Includono:
- Variazione percentuale dei ricavi
- Variazione percentuale dei costi
- Variazione percentuale del profitto
- Variazione percentuale della categoria di spesa principale
- Contributo percentuale del fornitore principale sulle spese totali

## 6. Spese per categoria

Questa sezione mostra la distribuzione dei costi per categoria di spesa.

L’implementazione attuale usa il modello dei costi basato su fatture e movimenti bancari negativi.

## 7. Spese per fornitore

Questa sezione mostra la distribuzione dei costi per fornitore.

L’implementazione attuale usa il modello dei costi basato su fatture e movimenti bancari negativi.

## 8. Riepilogo fatture

Questa sezione non è parte della formula P&L, ma è un riepilogo dei record delle fatture.

Valori mostrati:
- Totale fatture
- Fatture in sospeso
- Fatture pagate
- Totale importo in sospeso
- Totale importo pagato

## 9. Pagamenti per metodo

Questa sezione raggruppa i pagamenti per metodo di pagamento nel mese selezionato.

- Fonte: record di Payment
- Aggregazione: somma di Payment.amount raggruppata per Payment.method
