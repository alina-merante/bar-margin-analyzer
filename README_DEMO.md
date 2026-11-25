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

## 2. Preparare i dati dimostrativi

Accedere con un account di test autorizzato e selezionare
il bar dimostrativo.

Creare categorie e regole prima di importare i movimenti
bancari, utilizzando le operazioni autorizzate.

I precedenti esempi curl senza autenticazione non sono
più applicabili alle API protette.

Per le fixture isolate consultare
[la guida ai test](acceptance-tests/README.md).

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

### Test manuale degli errori di upload

Nella pagina Upload, sezione chiusura di cassa:

1. Caricare una chiusura già presente: compare un banner rosso
   "Documento già presente" con il motivo restituito dal backend (HTTP 409).
2. Cliccare altrove nella pagina: il banner deve restare visibile.
3. Chiuderlo con la X.
4. Caricare un documento in cui la data non è leggibile: compare il banner
   "Dati non validi" con il motivo del rifiuto (HTTP 422).

### Test del flusso OCR e revisione

Per testare l'estrazione OCR:

1. Preparare una fotografia di una chiusura di cassa (PDF o PNG). I test
   forniti in `data/` contengono esempi sintetici.
2. Dalla pagina Upload, caricare il file nella sezione "Chiusura di cassa".
3. Consultare la chiusura nella schermata di revisione.
4. Controllare e correggere i valori estratti.
5. Registrare la verifica completata.
6. Approvare con un account autorizzato.
7. Controllare i ricavi nel dashboard.

Non è previsto il salvataggio contabile automatico.

Limiti noti del test:

- L'OCR è stato verificato su immagini sintetiche; la precisione su documenti
  reali da registratori diversi non è garantita.
- Il parser concentra l'estrazione su sei campi: data, numero, totale, contanti,
  carta e numero scontrini. Campi aggiuntivi non sono estratti.

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