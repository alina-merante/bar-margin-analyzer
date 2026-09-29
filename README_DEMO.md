# BarManager — Demo Guide

Questa guida mostra come avviare il progetto, caricare i dati demo e verificare
il dashboard.

## 1. Avviare il sistema

In un ambiente Docker standard, dalla root del repository:

```bash
npm run dev:full
```

In GitHub Codespaces:

```bash
npm run dev:codespaces
```

In entrambi i casi le migrazioni Alembic vengono applicate automaticamente prima
dell'avvio dell'API. Non serve eseguire una migrazione manuale.

API: `http://localhost:8000`
Frontend: `http://localhost:5173`

## 2. Creare categorie

```bash
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Bevande"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Utenze"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Caffè"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Pasticceria"}'
curl -X POST http://localhost:8000/categories -H "Content-Type: application/json" -d '{"name":"Servizi"}'
```

## 3. Creare regole

```bash
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"METRO","category_id":1}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"CAFFE","category_id":3}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"ENEL","category_id":2}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"ACQUA","category_id":2}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"PASTICCERIA","category_id":4}'
curl -X POST http://localhost:8000/rules -H "Content-Type: application/json" -d '{"keyword":"MANUTENZIONE","category_id":5}'
```

## 4. Importare i dati demo

Esempio per marzo 2026:

```bash
curl -X POST http://localhost:8000/imports/pos-csv \
  -F "file=@data/pos_marzo_2026.csv"

curl -X POST http://localhost:8000/imports/bank-csv \
  -F "file=@data/bank_marzo_2026.csv"
```

Ripetere per novembre 2025, dicembre 2025, gennaio 2026, febbraio 2026 e
aprile 2026 se si vuole popolare il trend completo.

Le regole vengono applicate durante l'importazione: crearle prima di importare
i movimenti bancari.

## 5. Cosa verificare

- KPI di ricavi, costi e profitto;
- trend degli ultimi sei mesi;
- prodotti più venduti;
- fatture e pagamenti;
- upload di documenti e fatture;
- insight disponibili.

Le breakdown per categoria e fornitore, le sezioni corrispondenti dell'overview
e alcuni insight analytics sono ancora placeholder nel backend e possono
risultare vuoti.

## Clean bootstrap

Per verificare schema, endpoint e build frontend usando risorse temporanee:

```bash
sh scripts/verify-clean-bootstrap.sh
```

## Troubleshooting

Se il dashboard non mostra dati, verificare l'endpoint:

```bash
curl http://localhost:8000/analytics/overview?month=2026-03
```

Se il frontend segnala `ECONNREFUSED 127.0.0.1:8000`, controllare lo stato dei
servizi con `docker compose ps` in modalità standard. In Codespaces controllare
anche `backend/.uvicorn.log`.