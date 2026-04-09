# Bar Margin Analyzer — Demo Guide

This guide shows how to run the project and visualize financial analytics.

---

## 1. Start the system

docker compose up --build

---

## 2. Run database migrations

docker compose exec api bash -lc "cd /app && PYTHONPATH=/app alembic upgrade head"

---

## 3. Create categories

curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Bevande"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Utenze"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Caffè"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Pasticceria"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Servizi"}'

---

## 4. Create rules

curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"METRO","category_id":1}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"CAFFE","category_id":3}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"ENEL","category_id":2}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"ACQUA","category_id":2}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"PASTICCERIA","category_id":4}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"MANUTENZIONE","category_id":5}'

---

## 5. Import demo data

Example (March 2026):

curl -X POST http://localhost:8000/imports/pos-csv \
  -F "file=@data/pos_marzo_2026.csv"

curl -X POST http://localhost:8000/imports/bank-csv \
  -F "file=@data/bank_marzo_2026.csv"

Repeat for:

- November 2025
- December 2025
- January 2026
- February 2026
- April 2026

---

## 6. Open frontend

http://localhost:5173

---

## What you will see

- KPI (ricavi, costi, profitto)
- Trend ultimi 6 mesi
- Prodotti più venduti
- Categorie di spesa
- Top fornitori
- Fatture recenti
- Insight automatici

---

## Notes

- Month format: YYYY-MM
- Only negative bank transactions are counted as expenses
- Rules are applied during import only

---

## Troubleshooting

### No data in dashboard

curl http://localhost:8000/analytics/overview?month=2026-03

---

### Many "Uncategorized"

- Create rules BEFORE import
- Re-import bank CSV after creating rules
