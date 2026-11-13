import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import AlertBanner from "../components/AlertBanner.jsx";
import CameraCapture from "../components/CameraCapture.jsx";
import { useProtectedFiles } from "../ApiContext";

import {
  HISTORY_DATE_KIND_CIVIL,
  HISTORY_DATE_KIND_TIMESTAMP,
  compareHistoryEntriesDesc,
  formatCivilDate,
  formatHistoryDate,
} from "../historyDates.js";
import {
  buildCashClosureCorrections,
  CASH_REVIEW_LABELS,
  cashClosureWarnings,
  createCashClosureReviewForm,
  validateCashClosurePayments,
} from "../cashClosureReview.js";

function formatHistoryEntryDate(value, kind) {
  if (!value) return "Nessun file caricato";
  return formatHistoryDate(value, kind);
}

function formatBankTransactionDate(start, end) {
  if (!start) return "";

  const startDate = formatCivilDate(start);

  if (!end || end === start) return startDate;

  return `${startDate} – ${formatCivilDate(end)}`;
}

function formatUploadMessage(message) {
  return message.replace(
    /^Import BANK completato:\s*(\d+)\s+righe importate\./,
    (_, count) => {
      const importedCount = Number(count);
      const movementLabel = importedCount === 1 ? "movimento" : "movimenti";
      const importedLabel = importedCount === 1 ? "importato" : "importati";

      return `${importedCount} ${movementLabel} bancari ${importedLabel} correttamente.`;
    }
  );
}

function normalizeInvoiceText(value = "") {
  return String(value)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getInvoiceNumberDisplay(invoiceNumber) {
  const value = String(invoiceNumber || "").trim();
  if (!value) return "";
  if (/^AUTO-\d+/i.test(value)) return "";
  return value;
}

function getInvoiceCustomerName(invoice = {}) {
  const genericNames = new Set([
    "",
    "sconosciuto",
    "cliente",
    "fornitore",
    "n a",
    "na",
    "-",
  ]);

  const candidates = [
    invoice.supplier,
    invoice.customer_name,
    invoice.customer,
    invoice.counterparty,
    invoice.vendor,
    invoice.ragione_sociale,
    invoice.intestatario,
  ];

  for (const candidate of candidates) {
    const raw = String(candidate || "").trim();
    if (!raw) continue;

    const normalized = normalizeInvoiceText(raw);
    if (!genericNames.has(normalized)) {
      return raw;
    }
  }

  return "Cliente non indicato";
}

function formatInvoiceCategory(invoice = {}, knownCategories = []) {
  const category = String(invoice.category || "").trim();
  if (category) return category;

  const supplier = normalizeInvoiceText(invoice.supplier || "");
  const invoiceNumber = normalizeInvoiceText(invoice.invoice_number || "");

  const matchedKnownCategory = knownCategories.find((item) => {
    const normalizedCategory = normalizeInvoiceText(item);
    if (!normalizedCategory) return false;

    if (supplier.includes(normalizedCategory)) return true;

    const categoryTokens = normalizedCategory
      .split(" ")
      .filter((token) => token.length >= 4);

    return categoryTokens.some((token) => supplier.includes(token));
  });

  if (matchedKnownCategory) return matchedKnownCategory;

  if (
    supplier === "cliente" &&
    (invoiceNumber.startsWith("tc ") || invoiceNumber.startsWith("tc-"))
  ) {
    return "Caffe";
  }

  if (
    supplier.includes("caff") ||
    supplier.includes("vergnano") ||
    supplier.includes("torrefazione")
  ) {
    return "Caffe";
  }
  if (supplier.includes("latte") || supplier.includes("lattiero")) return "Latticini";
  if (supplier.includes("dolci") || supplier.includes("pane") || supplier.includes("pastic")) {
    return "Pasticceria";
  }
  if (
    supplier.includes("bevande") ||
    supplier.includes("drink") ||
    supplier.includes("birra") ||
    supplier.includes("wine")
  ) {
    return "Bevande";
  }
  if (supplier.includes("serviz") || supplier.includes("copywriter") || supplier.includes("consul")) {
    return "Servizi";
  }
  if (
    supplier.includes("utenz") ||
    supplier.includes("energia") ||
    supplier.includes("luce") ||
    supplier.includes("gas")
  ) {
    return "Utenze";
  }

  if (supplier) return "Altro";

  return "Categoria non assegnata";
}

function getDocumentPreviewUrl(document) {
  return document?.preview_url || document?.file_url || "";
}

function getDocumentFileUrl(document) {
  return document?.file_url || "";
}

// Componente React per gestire il caricamento e gli errori delle immagini
function DocumentPreview({ document }) {
  const [imageErrors, setImageErrors] = useState(new Set());
  const preview = useProtectedFiles([getDocumentPreviewUrl(document)]);
  const file = useProtectedFiles([getDocumentFileUrl(document)]);

  // Azzera gli errori quando il documento cambia
  useEffect(() => {
    setImageErrors(new Set());
  }, [document?.id]);

  if (!document) return null;

  const documentType = (document.document_type || "").toUpperCase();
  const fileUrl = file.urls[0];
  
  // Split preview URLs solo se esiste e non è vuota
  const previewUrls = preview.urls;

  if (preview.loading || file.loading) return <p>Caricamento documento...</p>;
  if (preview.error || file.error) return <p role="alert">{preview.error || file.error}</p>;

  // Handler per errore di caricamento immagine
  const handleImageError = (url) => {
    setImageErrors(prev => new Set([...prev, url]));
  };

  // Handler per caricamento riuscito
  const handleImageLoad = (url) => {
    setImageErrors(prev => {
      const newSet = new Set(prev);
      newSet.delete(url);
      return newSet;
    });
  };

  // Immagini direttamente visualizzabili (PNG, JPG, JPEG, WebP)
  if (["PNG", "JPG", "JPEG", "WEBP"].includes(documentType)) {
    // Usa preview_url se disponibile, altrimenti file_url
    const imagesToShow = previewUrls.length > 0 ? previewUrls : (fileUrl ? [fileUrl] : []);
    
    if (imagesToShow.length > 0) {
      // Se TUTTE le immagini hanno errore, mostra fallback
      const allImagesHaveErrors = imagesToShow.length > 0 && 
                                  imagesToShow.every(url => imageErrors.has(url));

      if (allImagesHaveErrors) {
        return (
          <div className="document-preview-unavailable">
            <div>📎</div>
            <h3>Anteprima non disponibile</h3>
            <p>Il file originale non è stato trovato. Contatta l'amministratore.</p>
          </div>
        );
      }

      return (
        <div className="document-preview-scroll">
          {imagesToShow.map((url, index) => (
            !imageErrors.has(url) && (
              <img
                key={url}
                src={url}
                alt={`${document.original_filename || "Documento"} ${imagesToShow.length > 1 ? `- Pagina ${index + 1}` : ""}`}
                className="document-preview-image"
                onLoad={(e) => {
                  handleImageLoad(url);
                  e.target.style.opacity = "1";
                }}
                onError={() => handleImageError(url)}
                style={{ opacity: "0.5", transition: "opacity 0.3s ease" }}
              />
            )
          ))}
        </div>
      );
    }
    // Se no preview_url e no file_url, mostra unavailable
    return (
      <div className="document-preview-unavailable">
        <div>📎</div>
        <h3>Anteprima non disponibile</h3>
        <p>Il documento è stato salvato, ma non è disponibile un'anteprima.</p>
      </div>
    );
  }

  // PDF - mostra immagini preview (già convertite dal backend)
  if (documentType === "PDF") {
    if (previewUrls.length > 0) {
      // Se TUTTE le immagini PDF hanno errore
      const allImagesHaveErrors = previewUrls.length > 0 && 
                                  previewUrls.every(url => imageErrors.has(url));

      if (allImagesHaveErrors) {
        return (
          <div className="document-preview-unavailable">
            <div>📎</div>
            <h3>Anteprima non disponibile</h3>
            <p>Il file PDF è stato salvato, ma l'anteprima non è disponibile.</p>
          </div>
        );
      }

      return (
        <div className="document-preview-scroll">
          {previewUrls.map((url, index) => (
            !imageErrors.has(url) && (
              <img
                key={url}
                src={url}
                alt={`PDF - Pagina ${index + 1}`}
                className="document-preview-image"
                onLoad={(e) => {
                  handleImageLoad(url);
                  e.target.style.opacity = "1";
                }}
                onError={() => handleImageError(url)}
                style={{ opacity: "0.5", transition: "opacity 0.3s ease" }}
              />
            )
          ))}
        </div>
      );
    }
    // Fallback per PDF senza preview
    return (
      <div className="document-preview-unavailable">
        <div>📎</div>
        <h3>Anteprima non disponibile</h3>
        <p>Il file PDF è stato salvato, ma l'anteprima non è disponibile.</p>
      </div>
    );
  }

  // TXT/CSV - mostra come link al file originale
  if (documentType === "TXT" || documentType === "CSV") {
    if (fileUrl) {
      return (
        <div className="document-preview-text-link">
          <div>📄</div>
          <h3>Documento testuale</h3>
          <p>Questo è un file di testo. Scaricalo per visualizzarne il contenuto.</p>
          <a href={fileUrl} download={document.original_filename} className="document-download-link">
            Scarica {documentType}
          </a>
        </div>
      );
    }
    // Fallback se no file_url per TXT
    return (
      <div className="document-preview-unavailable">
        <div>📄</div>
        <h3>Anteprima non disponibile</h3>
        <p>Il file di testo è stato salvato, ma non è più accessibile.</p>
      </div>
    );
  }

  // Fallback per formati non supportati
  return (
    <div className="document-preview-unavailable">
      <div>📎</div>
      <h3>Anteprima non disponibile</h3>
      <p>Il documento è stato salvato, ma non è disponibile un'anteprima per il formato {documentType || "sconosciuto"}.</p>
      {fileUrl && (
        <a href={fileUrl} download={document.original_filename} className="document-download-link">
          Scarica documento
        </a>
      )}
    </div>
  );
}


export function CashClosureReprocessComparison({ preview, busy, onConfirm, onCancel }) {
  return (
    <div className="cash-review-anomalies">
      <strong>Confronta i valori prima di confermare</strong>
      <p>La conferma sostituisce i valori attuali, incluse eventuali correzioni manuali. I valori precedenti restano nello storico.</p>
      <div className="cash-review-comparison-scroll">
      <table className="cash-review-comparison">
        <thead><tr><th>Campo</th><th>Valore attuale</th><th>Nuova lettura OCR</th></tr></thead>
        <tbody>
          {Object.entries(CASH_REVIEW_LABELS).map(([field, label]) => (
            <tr key={field}>
              <th scope="row">{label}</th>
              <td>{preview.previous[field] ?? "Non rilevato"}</td>
              <td>{preview.proposed[field] ?? "Non rilevato"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="cash-review-actions">
        <button type="button" disabled={busy} onClick={onConfirm}>
          Conferma rielaborazione
        </button>
        <button type="button" disabled={busy} onClick={onCancel}>
          Annulla
        </button>
      </div>
    </div>
  );
}

export function CashClosureReviewCard({
  review,
  onCorrect,
  onApprove,
  onReject,
  onReprocess,
}) {
  const [form, setForm] = useState(() => createCashClosureReviewForm(review));
  const [baseline, setBaseline] = useState(review);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState("");

  const corrections = buildCashClosureCorrections(baseline, form);
  const hasChanges = Object.keys(corrections).length > 0;
  const changedExternally = JSON.stringify(review) !== JSON.stringify(baseline);
  useEffect(() => {
    if (changedExternally && !hasChanges && !preview && !busy) {
      setBaseline(review);
      setForm(createCashClosureReviewForm(review));
    }
  }, [review, changedExternally, hasChanges, preview, busy]);
  const warnings = cashClosureWarnings(review);
  const paymentValidation = validateCashClosurePayments(
    form.total_amount,
    form.cash_amount,
    form.card_amount
  );
  const original = useProtectedFiles([review.document.file_url]);
  const previewUrl = original.urls[0];

  async function submit(action) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (action === "correct") {
        const result = await onCorrect(review.id, corrections);
        setBaseline(result);
        setForm(createCashClosureReviewForm(result));
        setMessage("Correzioni salvate. La chiusura rimane in attesa di approvazione.");
      } else if (action === "approve") {
        await onApprove(review.id);
      } else {
        await onReject(review.id);
      }
    } catch (requestError) {
      setError(requestError instanceof TypeError
        ? "Impossibile contattare il server. Controlla la connessione e riprova."
        : requestError.message || "Operazione non riuscita.");
    } finally {
      setBusy(false);
    }
  }

  function updateField(field, value) {
    setPreview(null);
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function reprocess(confirm = false) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await onReprocess(review.id, confirm ? preview : null);
      if (confirm) {
        setBaseline(result);
        setForm(createCashClosureReviewForm(result));
        setPreview(null);
        setMessage("Rielaborazione completata. Verifica i dati prima dell'approvazione.");
      } else {
        setPreview(result);
      }
    } catch (requestError) {
      setPreview(null);
      setError(requestError instanceof TypeError
        ? "Impossibile contattare il server. Controlla la connessione e riprova."
        : requestError.message || "Rielaborazione non riuscita.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="cash-review-card">
      <header className="cash-review-heading">
        <div>
          <h3>{review.document.original_filename}</h3>
          <p>Caricata il {new Date(review.created_at).toLocaleString("it-IT")}</p>
        </div>
        {previewUrl && <a href={previewUrl} target="_blank" rel="noreferrer">
          Apri documento originale
        </a>}
        {original.error && <p role="alert">{original.error}</p>}
      </header>

      {warnings.length > 0 ? (
        <div className="cash-review-anomalies">
          <strong>Campi da controllare</strong>
          <ul>
            {warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </div>
      ) : null}
      {review.receipts_total != null ? (
        <p>Totale scontrini rilevato: {review.receipts_total} € (non è il totale complessivo).</p>
      ) : null}

      <fieldset className="cash-review-fields" disabled={busy || !!preview}>
        <label>
          Data
          <input
            type="date"
            value={form.date}
            onChange={(event) => updateField("date", event.target.value)}
          />
        </label>
        <label>
          Numero chiusura
          <input
            value={form.closure_number}
            onChange={(event) => updateField("closure_number", event.target.value)}
          />
        </label>
        <label>
          Totale
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.total_amount}
            onChange={(event) => updateField("total_amount", event.target.value)}
          />
        </label>
        <label>
          Contanti
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.cash_amount}
            onChange={(event) => updateField("cash_amount", event.target.value)}
          />
        </label>
        <label>
          POS
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.card_amount}
            onChange={(event) => updateField("card_amount", event.target.value)}
          />
        </label>
        <label>
          Numero scontrini
          <input
            type="number"
            min="0"
            max="999999"
            step="1"
            value={form.receipts_count}
            onChange={(event) => updateField("receipts_count", event.target.value)}
          />
        </label>
      </fieldset>
      <p className="cash-review-hint">
        Un campo vuoto significa importo non noto; inserisci 0,00 solo se il documento riporta zero.
      </p>
      {paymentValidation.exceedsTotal ? (
        <p className="cash-review-error" role="alert">
          La somma di contanti e POS supera il totale della chiusura. Correggi gli importi prima di approvare.
        </p>
      ) : paymentValidation.incomplete && form.total_amount !== "" ? (
        <div className="cash-review-anomalies" role="status">
          Ripartizione incompleta: uno o più importi non sono noti e non vengono considerati pari a zero.
        </div>
      ) : paymentValidation.unallocatedCents !== null ? (
        <div className="cash-review-anomalies" role="status">
          Importo non attribuito:{" "}
          {new Intl.NumberFormat("it-IT", {
            style: "currency",
            currency: "EUR",
          }).format(paymentValidation.unallocatedCents / 100)}.
        </div>
      ) : null}
      {error ? <p className="cash-review-error" role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
      {busy ? <p role="status">Operazione in corso, attendi...</p> : null}
      {changedExternally && (hasChanges || preview) && !busy ? (
        <p className="cash-review-error" role="alert">
          La scheda è stata aggiornata. Annulla le modifiche o il confronto e verifica i nuovi dati prima di continuare.
        </p>
      ) : null}
      {preview && !changedExternally ? (
        <CashClosureReprocessComparison
          preview={preview}
          busy={busy}
          onConfirm={() => reprocess(true)}
          onCancel={() => setPreview(null)}
        />
      ) : null}
      {preview && changedExternally ? (
        <div className="cash-review-actions">
          <button type="button" disabled={busy} onClick={() => setPreview(null)}>Annulla confronto</button>
        </div>
      ) : null}
      {hasChanges ? <p className="cash-review-hint">Salva o annulla le modifiche prima di rielaborare l'OCR.</p> : null}
      <div className="cash-review-actions">
        <button type="button" disabled={busy || hasChanges || !!preview || changedExternally} onClick={() => reprocess()}>
          Rielabora OCR
        </button>
        <button
          type="button"
          disabled={busy || !!preview || !hasChanges || changedExternally}
          onClick={() => submit("correct")}
        >
          Salva correzioni
        </button>
        {hasChanges ? (
          <button type="button" disabled={busy} onClick={() => {
            setBaseline(review);
            setForm(createCashClosureReviewForm(review));
          }}>
            Annulla modifiche
          </button>
        ) : null}
        <button
          type="button"
          disabled={
            busy ||
            !review.can_approve ||
            changedExternally ||
            !!preview ||
            paymentValidation.exceedsTotal ||
            hasChanges ||
            !form.date ||
            !form.closure_number.trim() ||
            form.total_amount === ""
          }
          onClick={() => submit("approve")}
        >
          Approva
        </button>
        {!review.can_approve ? (
          <p className="cash-review-hint">L'approvazione è riservata al proprietario del bar o all'amministratore globale.</p>
        ) : null}
        <button
          type="button"
          className="cash-review-reject"
          disabled={busy || !!preview || changedExternally}
          onClick={() => submit("reject")}
        >
          Rifiuta
        </button>
      </div>
    </article>
  );
}

export default function UploadPage({
  month,
  handleUpload,
  uploading,
  uploadMessage,
  uploadError,
  handleInvoiceDocumentUpload,
  invoiceCategories = [],
  invoices = [],
  handleDeleteInvoice,
  clearDocumentMessages,
  dismissUploadFeedback,

  documents = [],
  cashClosureReviews = [],
  cashClosureLoading = false,
  cashClosureLoadError = "",
  cashClosureRefreshWarning = "",
  retryCashClosureLoad,
  handleCorrectCashClosure,
  handleApproveCashClosure,
  handleRejectCashClosure,
  handleReprocessCashClosure,
  handleGenericDocumentUpload,
  handleDeleteDocument,
  documentUploading,
  documentUploadMessage,
  documentUploadError,
  documentUploadWarnings,
  documentDeleteError,
}) {
  const navigate = useNavigate();

  const [activeHistoryTab, setActiveHistoryTab] = useState("all");
  const [cashClosureFilter, setCashClosureFilter] = useState("month");
  const [selectedOtherDocument, setSelectedOtherDocument] = useState(null);
  const [selectedInvoiceWithoutDocument, setSelectedInvoiceWithoutDocument] = useState(null);
  const documentPreviewRef = useRef(null);
  const invoiceWithoutDocumentPreviewRef = useRef(null);
  const [documentToDelete, setDocumentToDelete] = useState(null);
  const [deletingDocument, setDeletingDocument] = useState(false);
  const [, setLocalDocumentMessage] = useState("");

  useEffect(() => {
    if (!selectedOtherDocument && !selectedInvoiceWithoutDocument) return undefined;

    function handlePreviewPointerDown(event) {
      const clickedInsideDocumentPreview =
        documentPreviewRef.current?.contains(event.target) ||
        invoiceWithoutDocumentPreviewRef.current?.contains(event.target);
      if (!clickedInsideDocumentPreview) {
        setSelectedOtherDocument(null);
        setSelectedInvoiceWithoutDocument(null);
      }
    }

    function handlePreviewKeyDown(event) {
      if (event.key === "Escape") {
        setSelectedOtherDocument(null);
        setSelectedInvoiceWithoutDocument(null);
      }
    }

    document.addEventListener("pointerdown", handlePreviewPointerDown);
    document.addEventListener("keydown", handlePreviewKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePreviewPointerDown);
      document.removeEventListener("keydown", handlePreviewKeyDown);
    };
  }, [selectedOtherDocument, selectedInvoiceWithoutDocument]);

  useEffect(() => {
    setSelectedOtherDocument(null);
    setSelectedInvoiceWithoutDocument(null);
  }, [activeHistoryTab]);

  const [cashUploadError, setCashUploadError] = useState("");
  const [otherUploadError, setOtherUploadError] = useState("");

  const uploadWarnings = Array.isArray(documentUploadWarnings)
    ? documentUploadWarnings.filter((warning) => typeof warning === "string" && warning.trim())
    : [];

  function dismiss(kind) {
    dismissUploadFeedback?.(kind);
  }

  const currentMonthInvoices = useMemo(() => {
    return invoices.filter((invoice) => invoice.due_date?.slice(0, 7) === month);
  }, [invoices, month]);

  const knownInvoiceCategoryNames = useMemo(() => {
    return invoiceCategories
      .map((category) => category?.name || category?.category || category)
      .map((value) => String(value || "").trim())
      .filter(Boolean);
  }, [invoiceCategories]);

  const historyEntries = useMemo(() => {
    const documentEntries = documents.map((document) => {
      const effectiveDate =
        ["bank", "cash", "cash_closure"].includes(document.section)
          ? document.effective_date
          : null;

      return {
        id: `document-${document.id}`,
        kind: "document",
        tab: ["cash", "cash_closure"].includes(document.section) ? "cash" : document.section === "bank" ? "bank" : "other",
        title: document.original_filename,
        subtitle:
          document.section === "bank"
            ? "Movimenti bancari"
            : ["cash", "cash_closure"].includes(document.section)
              ? "Chiusura di cassa"
              : document.category,
        typeLabel: document.document_type,
        dateValue: effectiveDate || document.created_at,
        dateKind: effectiveDate ? HISTORY_DATE_KIND_CIVIL : HISTORY_DATE_KIND_TIMESTAMP,
        dateLabel:
          document.section === "bank" && effectiveDate
            ? formatBankTransactionDate(effectiveDate, document.effective_date_end)
            : formatHistoryEntryDate(
                effectiveDate || document.created_at,
                effectiveDate ? HISTORY_DATE_KIND_CIVIL : HISTORY_DATE_KIND_TIMESTAMP
              ),
        statusLabel: document.status,
        raw: document,
      };
    });

    const invoiceEntries = currentMonthInvoices.map((invoice) => ({
      id: `invoice-${invoice.id}`,
      kind: "invoice",
      tab: "invoices",
      title: getInvoiceCustomerName(invoice),
      detailLabel: getInvoiceNumberDisplay(invoice.invoice_number)
        ? `N. ${getInvoiceNumberDisplay(invoice.invoice_number)}`
        : "Fattura fornitore",
      subtitle: formatInvoiceCategory(invoice, knownInvoiceCategoryNames),
      typeLabel: "FATTURA",
      dateValue: invoice.issue_date,
      dateKind: HISTORY_DATE_KIND_CIVIL,
      dateLabel: formatHistoryEntryDate(invoice.issue_date, HISTORY_DATE_KIND_CIVIL),
      statusLabel: invoice.status === "paid" ? "Pagata" : invoice.status === "pending" ? "Da pagare" : invoice.status,
      raw: invoice,
    }));

    return [...documentEntries, ...invoiceEntries].sort(compareHistoryEntriesDesc);
  }, [documents, currentMonthInvoices, knownInvoiceCategoryNames]);

  const visibleHistoryEntries = useMemo(() => {
    if (activeHistoryTab === "all") return historyEntries;
    return historyEntries.filter((entry) => entry.tab === activeHistoryTab);
  }, [activeHistoryTab, historyEntries]);

function openHistoryEntry(entry) {
  if (entry.kind === "invoice") {
    const invoice = entry.raw;
    if (
      !invoice.file_url &&
      !invoice.document_url &&
      !invoice.document_path &&
      !invoice.url
    ) {
      setSelectedInvoiceWithoutDocument(invoice);
      return;
    }
    navigate("/invoices");
    return;
  }

  setSelectedOtherDocument(entry.raw);
}

async function deleteHistoryEntry(entry) {
  if (entry.kind === "invoice") {
    if (!handleDeleteInvoice) return;
    const invoiceNumber = entry.raw.invoice_number?.trim() || "non indicato";
    const supplier = entry.raw.supplier?.trim();
    const supplierLabel = supplier ? ` Fornitore: ${supplier}.` : "";
    if (
      !window.confirm(
        `Vuoi eliminare definitivamente la fattura n. ${invoiceNumber}?${supplierLabel}`
      )
    ) {
      return;
    }
    await handleDeleteInvoice(entry.raw.id);
    return;
  }

  setDocumentToDelete(entry.raw);
}

async function confirmDeleteDocument() {
  if (!documentToDelete || !handleDeleteDocument || deletingDocument) return;

  try {
    setDeletingDocument(true);
    const deleted = await handleDeleteDocument(documentToDelete.id);
    if (deleted) setDocumentToDelete(null);
  } finally {
    setDeletingDocument(false);
  }
}

  async function uploadInvoiceAndGoToInvoices(file) {
    if (!file || !handleInvoiceDocumentUpload) return;

    try {
      setLocalDocumentMessage("");
      await handleInvoiceDocumentUpload(file);
      navigate("/invoices");
    } catch (err) {
      console.error(err);
      setLocalDocumentMessage("Errore durante il caricamento della fattura.");
    }
  }

  async function handleCashDocument(file) {
  if (!file) return;

  setCashUploadError("");
  setOtherUploadError("");
  clearDocumentMessages?.();

  if (file.size > 20 * 1024 * 1024) {
    setCashUploadError(
      `Il PDF è troppo grande (${(file.size / 1024 / 1024).toFixed(1)} MB). Va compresso prima di caricarlo.`
    );
    return;
  }

const uploaded = await handleGenericDocumentUpload(file, "cash");
if (uploaded) setActiveHistoryTab("cash");
}

async function handleOtherDocument(file) {
  if (!file) return;

  setCashUploadError("");
  setOtherUploadError("");
  clearDocumentMessages?.();

  if (file.size > 20 * 1024 * 1024) {
    setOtherUploadError(
      `Il PDF è troppo grande (${(file.size / 1024 / 1024).toFixed(1)} MB). Va compresso prima di caricarlo.`
    );
    return;
  }

const uploaded = await handleGenericDocumentUpload(file, "other");
if (uploaded) setActiveHistoryTab("other");
}

  return (
    <main className="main upload-page">
      <section className="upload-hero">
        <h1 className="upload-page-title">Carica Documenti ⬆️</h1>
        <p className="upload-page-subtitle"></p>
      </section>

      <section className="upload-section">
        <div className="upload-section-label">⚡ Operazioni quotidiane</div>

        <div className="upload-primary-grid">
          <article className="upload-doc-card warm">
            <div className="upload-doc-head">
              <div className="upload-doc-icon">🧾</div>
              <div>
                <h2 className="upload-doc-title">Cassa giornaliera</h2>
                <p className="upload-doc-text">
                  Export giornaliero dal registratore di cassa. Caricalo ogni
                  sera dopo la chiusura.
                </p>
              </div>
            </div>

            <div className="upload-doc-tags">
              <span className="upload-doc-tag">PDF</span>
              <span className="upload-doc-tag">Immagine</span>
              <span className="upload-doc-tag">CSV/Excel</span>
            </div>

            <input
              id="daily-cash-upload-input"
              type="file"
              accept=".csv,.xlsx,.xls,.txt,.pdf,.jpg,.jpeg,.png,.webp"
              hidden
              onClick={(event) => event.stopPropagation()}
              onChange={async (event) => {
                const file = event.target.files?.[0];
                event.target.value = "";

                if (!file) return;

                await handleCashDocument(file);
              }}
            />

            <div
              className="upload-dropzone"
              onClick={(event) => {
                event.stopPropagation();
                document.getElementById("daily-cash-upload-input")?.click();
              }}
            >
              <div className="upload-dropzone-icon">📂</div>
              <div className="upload-dropzone-title">Trascina export cassa</div>
              <div className="upload-dropzone-sub">
                oppure <span>clicca per selezionare</span>
              </div>
            </div>
            <CameraCapture
              className="upload-camera-btn"
              label="Scatta foto chiusura di cassa"
              onCapture={handleCashDocument}
            />
          </article>

          <article className="upload-doc-card cool">
            <div className="upload-doc-head">
              <div className="upload-doc-icon">🏦</div>
              <div>
                <h2 className="upload-doc-title">Movimenti bancari</h2>
                <p className="upload-doc-text">
                  Estratto conto o export movimenti dalla banca. Caricalo
                  settimanalmente o mensilmente.
                </p>
              </div>
            </div>

            <div className="upload-doc-tags">
              <span className="upload-doc-tag">PDF</span>
              <span className="upload-doc-tag">CSV banca</span>
              <span className="upload-doc-tag">Excel</span>
            </div>

            <label className="upload-dropzone">
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.pdf"
                hidden
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    await handleUpload(file, "bank");
                    setActiveHistoryTab("bank");
                  }
                  e.target.value = "";
                }}
              />
              <div className="upload-dropzone-icon">📂</div>
              <div className="upload-dropzone-title">
                Trascina movimenti banca
              </div>
              <div className="upload-dropzone-sub">
                oppure <span>clicca per selezionare</span>
              </div>
            </label>
          </article>
        </div>

        <div className="upload-feedback-area">
          {uploading || documentUploading ? (
            <p className="upload-feedback">Caricamento in corso...</p>
          ) : null}

          {uploadMessage ? (
            <AlertBanner variant="success" onClose={() => dismiss("uploadMessage")}>
              {formatUploadMessage(uploadMessage)}
            </AlertBanner>
          ) : null}

          {uploadError ? (
            <AlertBanner
              variant={uploadError.variant}
              title={uploadError.title}
              onClose={() => dismiss("uploadError")}
            >
              {uploadError.message}
            </AlertBanner>
          ) : null}

          {documentUploadMessage ? (
            <AlertBanner variant="success" onClose={() => dismiss("documentMessage")}>
              {documentUploadMessage}
            </AlertBanner>
          ) : null}

          {uploadWarnings.length > 0 ? (
            <AlertBanner
              variant="warning"
              title="Controlla i dati letti"
              onClose={() => dismiss("documentWarnings")}
            >
              {uploadWarnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </AlertBanner>
          ) : null}

          {documentUploadError ? (
            <AlertBanner
              variant={documentUploadError.variant}
              title={documentUploadError.title}
              onClose={() => dismiss("documentError")}
            >
              {documentUploadError.message}
            </AlertBanner>
          ) : null}

          {documentDeleteError ? (
            <AlertBanner
              variant="error"
              title="Eliminazione non riuscita"
              onClose={() => dismiss("documentDeleteError")}
            >
              {documentDeleteError}
            </AlertBanner>
          ) : null}

          {cashUploadError ? (
            <AlertBanner
              variant="error"
              title="File troppo grande"
              onClose={() => setCashUploadError("")}
            >
              {cashUploadError}
            </AlertBanner>
          ) : null}

        </div>
      </section>

      <section className="upload-section">
        <div className="upload-section-label">🧾 Documenti contabili</div>

        <div className="upload-secondary-grid">
          <article className="upload-mini-card">
            <div className="upload-mini-icon">🧾</div>
            <h3>Fatture fornitori</h3>
            <p>PDF · XML (fatturazione elettronica SDI)</p>

            <input
              id="invoice-upload-input"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.xml,.webp,.heic,.heif"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];

                if (file) {
                  uploadInvoiceAndGoToInvoices(file);
                }

                event.target.value = "";
              }}
            />

            <div
              className="upload-mini-box"
              onClick={(event) => {
                event.stopPropagation();
                document.getElementById("invoice-upload-input")?.click();
              }}
            >
              <div className="upload-mini-box-icon">📄</div>
              <div className="upload-mini-box-title">Carica fattura</div>
              <div className="upload-mini-box-sub">PDF o file XML SDI</div>
            </div>
            <CameraCapture
              className="upload-camera-btn"
              label="Scatta foto fattura"
              onCapture={uploadInvoiceAndGoToInvoices}
            />
          </article>

          <article className="upload-mini-card">
            <div className="upload-mini-icon green">📒</div>
            <h3>Pagamenti in contanti</h3>
            <p>Excel · CSV · PDF</p>

            <input
              id="cash-document-upload-input"
              type="file"
              accept=".csv,.xlsx,.xls,.pdf"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];

                handleCashDocument(file);
                event.target.value = "";
              }}
            />

            <div
              className="upload-mini-box"
              onClick={(event) => {
                event.stopPropagation();
                document.getElementById("cash-document-upload-input")?.click();
              }}
            >
              <div className="upload-mini-box-icon">📊</div>
              <div className="upload-mini-box-title">Carica prima nota</div>
              <div className="upload-mini-box-sub">
                Registro entrate e uscite
              </div>
            </div>
          </article>

          <article className="upload-mini-card">
            <div className="upload-mini-icon violet">📎</div>
            <h3>Altro documento</h3>
            <p>L'AI lo classifica automaticamente</p>

            <input
              id="other-document-upload-input"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.csv,.xlsx,.xls,.xml,.txt,.webp"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];

                handleOtherDocument(file);
                event.target.value = "";
              }}
            />

            <div
              className="upload-mini-box"
              onClick={(event) => {
                event.stopPropagation();
                document.getElementById("other-document-upload-input")?.click();
              }}
            >
              <div className="upload-mini-box-icon">📂</div>
              <div className="upload-mini-box-title">Carica documento</div>
              <div className="upload-mini-box-sub">
                Qualsiasi formato supportato
              </div>
            </div>

            {otherUploadError ? (
              <AlertBanner
                variant="error"
                title="File troppo grande"
                onClose={() => setOtherUploadError("")}
              >
                {otherUploadError}
              </AlertBanner>
            ) : null}
          </article>
        </div>
      </section>

      <section className="upload-section">
        <div className="upload-history-card">
          <h2>Chiusure da verificare</h2>
          <fieldset className="cash-review-filter">
            <legend>Mostra chiusure</legend>
            <label>
              <input type="radio" name="cash-closure-filter" checked={cashClosureFilter === "month"}
                onChange={() => setCashClosureFilter("month")} />
              Mese selezionato ({month})
            </label>
            <label>
              <input type="radio" name="cash-closure-filter" checked={cashClosureFilter === "all"}
                onChange={() => setCashClosureFilter("all")} />
              Tutte le chiusure pendenti
            </label>
          </fieldset>
          {cashClosureFilter === "all" ? (
            <p>Le chiusure senza data sono disponibili solo in questa vista.</p>
          ) : null}
          {cashClosureRefreshWarning ? <p role="alert">{cashClosureRefreshWarning}</p> : null}
          {cashClosureLoadError ? (
            <div role="alert">
              <p>{cashClosureLoadError}</p>
              <button type="button" onClick={retryCashClosureLoad}>Riprova</button>
            </div>
          ) : null}
          {cashClosureLoading ? <p role="status">Caricamento delle chiusure...</p> : null}
          {cashClosureReviews.length ? (
            <div className="cash-review-list">
              {cashClosureReviews.map((review) => (
                <div key={review.id} hidden={
                  cashClosureFilter === "month" && review.date?.slice(0, 7) !== month
                }>
                  <CashClosureReviewCard
                    review={review}
                    onCorrect={handleCorrectCashClosure}
                    onApprove={handleApproveCashClosure}
                    onReject={handleRejectCashClosure}
                    onReprocess={handleReprocessCashClosure}
                  />
                </div>
              ))}
            </div>
          ) : null}
          {!cashClosureLoading && !cashClosureLoadError && (
            cashClosureFilter === "month"
              ? !cashClosureReviews.some((review) => review.date?.slice(0, 7) === month)
              : !cashClosureReviews.length
          ) ? (
            <p>{cashClosureFilter === "month"
              ? "Nessuna chiusura da verificare nel mese selezionato. Seleziona tutte le chiusure pendenti per vedere anche quelle senza data."
              : "Nessuna chiusura in attesa di verifica."}</p>
          ) : null}
        </div>
      </section>

      <section className="upload-section">
        <div className="upload-history-card">
          <h2>Storico documenti caricati</h2>

          <div className="upload-history-tabs">
            <button
              type="button"
              className={`history-tab ${activeHistoryTab === "all" ? "active" : ""}`}
              onClick={() => setActiveHistoryTab("all")}
            >
              Tutti
            </button>

            <button
              type="button"
              className={`history-tab ${
                activeHistoryTab === "invoices" ? "active" : ""
              }`}
              onClick={() => {
                setActiveHistoryTab("invoices");
                //navigate("/invoices");
              }}
            >
              Fatture
            </button>

            <button
              type="button"
              className={`history-tab ${activeHistoryTab === "cash" ? "active" : ""}`}
              onClick={() => setActiveHistoryTab("cash")}
            >
              Cassa
            </button>

            <button
              type="button"
              className={`history-tab ${activeHistoryTab === "bank" ? "active" : ""}`}
              onClick={() => setActiveHistoryTab("bank")}
            >
              Banca
            </button>

            <button
              type="button"
              className={`history-tab ${activeHistoryTab === "other" ? "active" : ""}`}
              onClick={() => setActiveHistoryTab("other")}
            >
              Altro
            </button>
          </div>

          {visibleHistoryEntries.length ? (
            <div className="upload-history-table">
              <div className="upload-history-table-head other-docs-table">
                <div>Documento</div>
                <div>Categoria</div>
                <div>Data</div>
                <div>Stato</div>
                <div>Visualizza</div>
                <div>Elimina</div>
              </div>

              {visibleHistoryEntries.map((entry) => (
                  <div
                    className="upload-history-table-row other-docs-table"
                    key={entry.id}
                  >
                    <div className="upload-history-name">
                      {entry.title}
                      {entry.detailLabel ? (
                        <div className="upload-history-meta">{entry.detailLabel}</div>
                      ) : null}
                    </div>
                    <div className="upload-history-category">
                      {entry.subtitle || "-"}
                    </div>
                    <div>{entry.dateLabel}</div>
                    <div className="upload-history-status">{entry.statusLabel}</div>

                    <div className="upload-history-action-cell">
                      <button
                        type="button"
                        className="invoice-icon-btn"
                        onClick={() => openHistoryEntry(entry)}
                        title={entry.kind === "invoice" ? "Apri fatture" : "Visualizza documento"}
                      >
                        👁️
                      </button>
                    </div>

                    <div className="upload-history-action-cell">
                      <button
                        type="button"
                        className="invoice-icon-btn delete"
                        onClick={() => deleteHistoryEntry(entry)}
                        title={entry.kind === "invoice" ? "Elimina fattura" : "Elimina documento"}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
              ))}
            </div>
          ) : (
            <div className="upload-history-empty">
              <div className="upload-history-icon">📎</div>

              <div>
                <div className="upload-history-name">
                  Nessun documento caricato
                </div>
                <div className="upload-history-meta">
                  Qui trovi fatture, cassa, banca e altri documenti del mese selezionato.
                </div>
              </div>

              <div className="upload-history-status waiting">In attesa</div>
            </div>
          )}
        </div>
      </section>

      {selectedOtherDocument ? (
        <div className="invoice-preview-backdrop">
          <div className="invoice-preview-modal only-document" ref={documentPreviewRef}>
            <button
              type="button"
              className="invoice-preview-floating-close"
              onClick={() => setSelectedOtherDocument(null)}
            >
              ✕
            </button>

            <div className="invoice-preview-body invoice-preview-body-only-document">
              <div className="invoice-preview-document full">
                <DocumentPreview document={selectedOtherDocument} />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {selectedInvoiceWithoutDocument ? (
        <div
          className="invoice-preview-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setSelectedInvoiceWithoutDocument(null);
            }
          }}
        >
          <section
            className="document-info-modal"
            ref={invoiceWithoutDocumentPreviewRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="manual-invoice-document-title"
          >
            <h2 id="manual-invoice-document-title">Documento non disponibile</h2>
            <p>
              Questa fattura è stata inserita manualmente e non ha un file associato.
            </p>
            <div className="document-delete-confirm-actions">
              <button
                type="button"
                onClick={() => setSelectedInvoiceWithoutDocument(null)}
              >
                Chiudi
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {documentToDelete ? (
        <div className="document-delete-confirm-backdrop">
          <section
            className="document-delete-confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="document-delete-confirm-title"
          >
            <h2 id="document-delete-confirm-title">Eliminare il documento?</h2>
            <p>
              Il documento <strong>{documentToDelete.original_filename}</strong> sarà
              eliminato definitivamente. Questa operazione non può essere annullata.
            </p>
            {documentDeleteError ? (
              <p className="upload-feedback error" role="alert">
                {documentDeleteError}
              </p>
            ) : null}
            <div className="document-delete-confirm-actions">
              <button
                type="button"
                onClick={() => setDocumentToDelete(null)}
                disabled={deletingDocument}
              >
                Annulla
              </button>
              <button
                type="button"
                className="danger"
                onClick={confirmDeleteDocument}
                disabled={deletingDocument || !handleDeleteDocument}
              >
                {deletingDocument ? "Eliminazione..." : "Elimina definitivamente"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}