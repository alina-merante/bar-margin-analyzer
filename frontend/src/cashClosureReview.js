const REVIEW_FIELDS = [
  "date",
  "closure_number",
  "total_amount",
  "cash_amount",
  "card_amount",
  "receipts_count",
];

export const CASH_REVIEW_LABELS = {
  date: "Data",
  closure_number: "Numero chiusura",
  total_amount: "Totale complessivo",
  cash_amount: "Contanti",
  card_amount: "Pagamenti elettronici",
  receipts_count: "Numero scontrini",
  receipts_total: "Totale scontrini",
};

const ANOMALY_MESSAGES = {
  missing: "non rilevato",
  ambiguous: "incerto",
  conflict: "valori discordanti",
  malformed: "non leggibile",
  resolved_among_alternatives: "da verificare tra più valori rilevati",
  in_future: "data futura da verificare",
  generic_label: "letto da un'etichetta generica: verifica sul documento",
};

export function cashClosureWarnings(review) {
  const messages = new Set();
  for (const anomaly of review.anomalies || []) {
    const [field, reason] = String(anomaly).split(":");
    if (field === "payments" && reason === "total_mismatch") {
      messages.add("I pagamenti rilevati non coincidono con il totale.");
    } else if (field === "payments" && reason === "incomplete") {
      messages.add("La ripartizione dei pagamenti è incompleta.");
    } else if (CASH_REVIEW_LABELS[field] && ANOMALY_MESSAGES[reason]) {
      messages.add(`${CASH_REVIEW_LABELS[field]}: ${ANOMALY_MESSAGES[reason]}.`);
    } else {
      messages.add("Sono presenti dati OCR da verificare sul documento originale.");
    }
  }
  for (const [field, details] of Object.entries(review.ocr_values?.diagnostics?.fields || {})) {
    if (details.status !== "ok" && CASH_REVIEW_LABELS[field] && ANOMALY_MESSAGES[details.status]) {
      messages.add(`${CASH_REVIEW_LABELS[field]}: ${ANOMALY_MESSAGES[details.status]}.`);
    } else if (details.status === "ok" && details.competing?.length > 1 && CASH_REVIEW_LABELS[field]) {
      messages.add(`${CASH_REVIEW_LABELS[field]}: da verificare tra più valori rilevati.`);
    }
  }
  return [...messages];
}

export function createLatestDocumentLoader(fetchJson, onSuccess, onError) {
  let generation = 0;
  return {
    invalidate() {
      generation += 1;
    },
    async load(month) {
      const current = ++generation;
      try {
        const [documents, reviews] = await Promise.all([
          fetchJson(`/api/documents?month=${month}`),
          fetchJson("/api/cash-closures/review"),
        ]);
        if (current === generation) onSuccess(documents, reviews, month);
      } catch (error) {
        if (current !== generation) return;
        onError(error, month);
        throw error;
      }
    },
  };
}

export function updateCashClosureList(reviews, result) {
  return result.status === "pending"
    ? reviews.map((review) => review.id === result.id ? result : review)
    : reviews.filter((review) => review.id !== result.id);
}

export async function reprocessCashClosure(fetch, intakeId, preview, refresh) {
  let response;
  try {
    response = await fetch(
      `/api/cash-closures/review/${intakeId}/reprocess${preview ? "" : "/preview"}`,
      {
        method: "POST",
        ...(preview ? {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            review_version: preview.review_version,
            extraction_version: preview.extraction_version,
          }),
        } : {}),
      }
    );
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Impossibile contattare il server. Controlla la connessione e riprova.");
    }
    throw error;
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const italianDetail = typeof detail === "string" &&
      /^(La scheda|La chiusura|Una chiusura|Il documento|Il risultato OCR|Documento originale|Chiusura da verificare)/.test(detail);
    throw new Error(italianDetail ? detail :
      response.status === 401 || response.status === 403
        ? "Sessione scaduta o permessi insufficienti. Accedi nuovamente e riprova."
        : "Impossibile rielaborare la chiusura. Aggiorna la pagina e riprova.");
  }
  if (!payload || typeof payload !== "object") {
    throw new Error("Risposta del server non valida. Aggiorna la pagina e riprova.");
  }
  if (preview) {
    try {
      await refresh(payload);
    } catch {
      throw new Error("Rielaborazione salvata, ma aggiornamento della scheda non riuscito. Ricarica la pagina.");
    }
  }
  return payload;
}

export function createCashClosureReviewForm(review) {
  return {
    date: review.date || "",
    closure_number: review.closure_number || "",
    total_amount: review.total_amount ?? "",
    cash_amount: review.cash_amount ?? "",
    card_amount: review.card_amount ?? "",
    receipts_count: review.receipts_count == null ? "" : String(review.receipts_count),
  };
}

export function buildCashClosureCorrections(review, form) {
  const original = createCashClosureReviewForm(review);
  return Object.fromEntries(
    REVIEW_FIELDS.filter((field) => form[field] !== original[field]).map((field) => [
      field,
      form[field] === "" ? null : form[field],
    ])
  );
}

function amountToCents(value) {
  if (value === null || value === undefined || value === "") return null;
  const match = String(value).trim().match(/^(\d*)(?:\.(\d{0,2}))?$/);
  if (!match || (!match[1] && !match[2])) return null;
  const cents = Number(match[1] || 0) * 100 + Number((match[2] || "").padEnd(2, "0"));
  return Number.isSafeInteger(cents) ? cents : null;
}

export function validateCashClosurePayments(total, cash, card) {
  const totalCents = amountToCents(total);
  const cashCents = amountToCents(cash);
  const cardCents = amountToCents(card);

  if (totalCents === null || cashCents === null || cardCents === null) {
    return {
      exceedsTotal: false,
      incomplete: true,
      unallocatedCents: null,
    };
  }

  const unallocatedCents = totalCents - cashCents - cardCents;
  return {
    exceedsTotal: unallocatedCents < 0,
    incomplete: false,
    unallocatedCents: unallocatedCents > 0 ? unallocatedCents : null,
  };
}
