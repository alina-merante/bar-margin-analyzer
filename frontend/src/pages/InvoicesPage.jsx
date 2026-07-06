
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);
}

function formatDate(value) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function formatMonthHuman(month) {
  if (!month) return "-";

  const [year, monthNum] = month.split("-").map(Number);

  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, monthNum - 1, 1));
}

function getInvoiceMonthKey(dateValue) {
  if (!dateValue) return "";

  if (typeof dateValue === "string") {
    const isoMatch = dateValue.match(/^(\d{4})-(\d{2})/);
    if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}`;
  }

  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return "";

  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function isOverdue(invoice) {
  if (invoice.status === "paid") return false;
  if (!invoice.due_date) return false;
  return new Date(invoice.due_date) < new Date();
}

function isDue(invoice) {
  if (invoice.status === "paid") return false;
  if (!invoice.due_date) return true;
  return new Date(invoice.due_date) >= new Date();
}

function getInvoiceStatus(invoice) {
  if (invoice.status === "paid") return "paid";
  if (isOverdue(invoice)) return "overdue";
  return "due";
}

function getStatusLabel(invoice) {
  const status = getInvoiceStatus(invoice);

  if (status === "paid") return "Pagata";
  if (status === "overdue") return "Scaduta";
  return "In scadenza";
}

function getCategoryIcon(category = "") {
  const lower = category.toLowerCase();

  if (lower.includes("caff")) return "☕";
  if (lower.includes("latte") || lower.includes("lattiero")) return "🥛";
  if (lower.includes("dolci") || lower.includes("pane")) return "🥐";
  if (lower.includes("bevande")) return "🍹";

  return "🧾";
}

function getInvoiceDocumentUrl(invoice) {
  const rawUrl =
    invoice?.file_url ||
    invoice?.document_url ||
    invoice?.document_path ||
    invoice?.url ||
    "";

  if (!rawUrl) return "";

  if (rawUrl.startsWith("http")) return rawUrl;

  return `/api${rawUrl}`;
}

const EMPTY_MANUAL_FORM = {
  supplier: "",
  invoice_number: "",
  due_date: "",
  category: "",
  total: "",
  vat: "",
};

export default function InvoicesPage({
  month,
  invoices = [],
  invoiceUploadMessage,
  invoiceUploadError,
  invoiceUploading,
  handleDeleteInvoice,
  invoiceDeleteError,
  handleCreateManualInvoice,
  handleInvoiceDocumentUpload,
}) {
  const [statusFilter, setStatusFilter] = useState("all");
  const [supplierSearch, setSupplierSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState(null);

  const [searchParams] = useSearchParams();

useEffect(() => {
  if (searchParams.get("tab") === "overdue") {
    setStatusFilter("overdue");
  }
}, [searchParams]);

  const [manualForm, setManualForm] = useState(EMPTY_MANUAL_FORM);
  const [manualError, setManualError] = useState("");
  const [manualSaving, setManualSaving] = useState(false);

  function updateManualForm(field, value) {
    setManualForm((prev) => ({
      ...prev,
      [field]: value,
    }));

    if (manualError) setManualError("");
  }

  function closeManualModal() {
    if (manualSaving) return;

    setManualOpen(false);
    setManualError("");
    setManualForm(EMPTY_MANUAL_FORM);
  }

  function closeInvoicePreview() {
    setSelectedInvoice(null);
  }

  async function submitManualInvoice() {
    const requiredFields = [
      "supplier",
      "invoice_number",
      "due_date",
      "category",
      "total",
      "vat",
    ];

    const hasEmptyFields = requiredFields.some(
      (field) => !String(manualForm[field] || "").trim()
    );

    if (hasEmptyFields) {
      setManualError("Compila tutti i campi prima di salvare la fattura.");
      return;
    }

    if (Number(manualForm.total) <= 0) {
      setManualError("Il totale deve essere maggiore di zero.");
      return;
    }

    if (Number(manualForm.vat) < 0) {
      setManualError("L'IVA non può essere negativa.");
      return;
    }

    // Non richiediamo più la data di emissione: la scadenza è la data principale

    if (!handleCreateManualInvoice) {
      setManualError("Funzione di salvataggio manuale non collegata.");
      return;
    }

    try {
      setManualSaving(true);
      setManualError("");

      await handleCreateManualInvoice({
        supplier: manualForm.supplier.trim(),
        invoice_number: manualForm.invoice_number.trim(),
        due_date: manualForm.due_date,
        category: manualForm.category.trim(),
        total: Number(manualForm.total),
        vat: Number(manualForm.vat),
        status: "pending",
      });

      setManualForm(EMPTY_MANUAL_FORM);
      setManualOpen(false);
    } catch (err) {
      console.error(err);
      setManualError("Errore durante il salvataggio della fattura.");
    } finally {
      setManualSaving(false);
    }
  }

  const currentMonthInvoices = useMemo(() => {
    return invoices.filter((invoice) => getInvoiceMonthKey(invoice.due_date) === month);
  }, [invoices, month]);

const invoicesForView = useMemo(() => {
  if (statusFilter === "overdue") {
    return currentMonthInvoices.filter(isOverdue);
  }

  return currentMonthInvoices;
}, [invoices, currentMonthInvoices, statusFilter]);

const paidInvoices = invoicesForView.filter((invoice) => invoice.status === "paid");
const dueInvoices = invoicesForView.filter(isDue);
const overdueInvoices = invoicesForView.filter(isOverdue);

  const categories = useMemo(() => {
  return [
    ...new Set(invoicesForView.map((invoice) => invoice.category).filter(Boolean)),
  ].sort((a, b) => a.localeCompare(b, "it"));
}, [invoicesForView]);

  const filteredInvoices = useMemo(() => {
    return invoicesForView.filter((invoice) => {
      const status = getInvoiceStatus(invoice);
      const matchesStatus = statusFilter === "all" || status === statusFilter;

      const matchesSupplier =
        !supplierSearch ||
        invoice.supplier?.toLowerCase().includes(supplierSearch.toLowerCase());

      const matchesCategory = !categoryFilter || invoice.category === categoryFilter;

      return matchesStatus && matchesSupplier && matchesCategory;
    });
}, [invoicesForView, statusFilter, supplierSearch, categoryFilter]);

const totalAmount = invoicesForView.reduce(
      (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const paidAmount = paidInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const dueAmount = dueInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const overdueAmount = overdueInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const selectedInvoiceDocumentUrl = getInvoiceDocumentUrl(selectedInvoice);

  return (
    <main className="main invoices-dashboard-page">
      <section className="invoices-dashboard-header">
        <div>
          <h1 className="invoices-dashboard-title">Fatture 🧾</h1>
          <p className="invoices-dashboard-subtitle">
            {formatMonthHuman(month)} · {currentMonthInvoices.length} fatture ·{" "}
            {formatEuro(totalAmount)} totale
          </p>
        </div>

        <div className="invoices-dashboard-actions">
          <button
            type="button"
            className="invoice-manual-btn"
            onClick={() => setManualOpen(true)}
          >
            ✏️ Inserisci manuale
          </button>

          <label className="invoice-upload-btn">
            ⬆️ Carica fattura
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.xml"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];

                if (file && handleInvoiceDocumentUpload) {
                  handleInvoiceDocumentUpload(file);
                }

                event.target.value = "";
              }}
            />
          </label>
        </div>
      </section>

      <section className="invoice-kpi-grid">
        <article className="invoice-kpi-card">
          <div className="invoice-kpi-label">Totale fatture</div>
          <div className="invoice-kpi-value">{formatEuro(totalAmount)}</div>
          <span className="invoice-kpi-pill blue">
            {currentMonthInvoices.length} documenti
          </span>
        </article>

        <article className="invoice-kpi-card">
          <div className="invoice-kpi-label">Pagate</div>
          <div className="invoice-kpi-value">{formatEuro(paidAmount)}</div>
          <span className="invoice-kpi-pill green">✓ {paidInvoices.length} fatture</span>
        </article>

        <article className="invoice-kpi-card">
          <div className="invoice-kpi-label">In scadenza</div>
          <div className="invoice-kpi-value">{formatEuro(dueAmount)}</div>
          <span className="invoice-kpi-pill yellow">⏰ {dueInvoices.length} fatture</span>
        </article>

        <article className="invoice-kpi-card dark">
          <div className="invoice-kpi-label">Scadute</div>
          <div className="invoice-kpi-value">{formatEuro(overdueAmount)}</div>
          <span className="invoice-kpi-pill red">⚠ Pagamento urgente</span>
        </article>
      </section>

      <section className="invoice-filters-row">
        <button
          type="button"
          className={`invoice-status-filter ${statusFilter === "all" ? "active" : ""}`}
          onClick={() => setStatusFilter("all")}
        >
          Tutte ({currentMonthInvoices.length})
        </button>

        <button
          type="button"
          className={`invoice-status-filter ${statusFilter === "paid" ? "active" : ""}`}
          onClick={() => setStatusFilter("paid")}
        >
          ✓ Pagate ({paidInvoices.length})
        </button>

        <button
          type="button"
          className={`invoice-status-filter ${statusFilter === "due" ? "active" : ""}`}
          onClick={() => setStatusFilter("due")}
        >
          ⏰ In scadenza ({dueInvoices.length})
        </button>

        <button
          type="button"
          className={`invoice-status-filter ${
            statusFilter === "overdue" ? "active danger" : ""
          }`}
          onClick={() => setStatusFilter("overdue")}
        >
          ✗ Scadute ({overdueInvoices.length})
        </button>

        <div className="invoice-search-box">
          🔍
          <input
            value={supplierSearch}
            onChange={(event) => setSupplierSearch(event.target.value)}
            placeholder="Cerca fornitore..."
          />
        </div>

        <select
          className="invoice-category-select"
          value={categoryFilter}
          onChange={(event) => setCategoryFilter(event.target.value)}
        >
          <option value="">Categoria</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </section>

      <section className="invoice-modern-table-card">
      <div className="invoice-clean-table-head">
        <div>FORNITORE</div>
        <div>N° FATTURA</div>
        <div>SCADENZA</div>
        <div>CATEGORIA</div>
        <div>TOTALE</div>
        <div>VISUALIZZA</div>
        <div>ELIMINA</div>
      </div>

        {filteredInvoices.length ? (
          filteredInvoices.map((invoice) => {
            const status = getInvoiceStatus(invoice);

            return (
              <div className={`invoice-clean-table-row ${status}`} key={invoice.id}>
                <div className="invoice-modern-supplier">
                  {invoice.supplier || "Fornitore"}
                </div>

                <div className="invoice-modern-number">
                  {invoice.invoice_number || "-"}
                </div>

                <div className="invoice-modern-due">{formatDate(invoice.due_date)}</div>

                <div className="invoice-modern-category">
                  {getCategoryIcon(invoice.category)} {invoice.category || "Altro"}
                </div>

                <div className="invoice-modern-total">{formatEuro(invoice.total)}</div>

            <div className="invoice-action-cell">
              <button
                type="button"
                className="invoice-icon-btn"
                onClick={() => setSelectedInvoice(invoice)}
                title="Visualizza fattura"
              >
                👁️
              </button>
            </div>

            <div className="invoice-action-cell">
              <button
                type="button"
                className="invoice-icon-btn delete"
                onClick={() => {
                  if (window.confirm("Vuoi eliminare questa fattura?")) {
                    handleDeleteInvoice(invoice.id);
                  }
                }}
                title="Elimina fattura"
              >
                🗑️
              </button>
            </div>
              </div>
            );
          })
        ) : (
          <p className="small-muted">
            Nessuna fattura disponibile con i filtri selezionati.
          </p>
        )}

        {filteredInvoices.length ? (
          <div className="invoice-table-footer">
            Mostrate {filteredInvoices.length} di {currentMonthInvoices.length} fatture
          </div>
        ) : null}
      </section>

      <div className="upload-feedback-area">
        {invoiceUploading ? <p className="upload-feedback">Caricamento in corso...</p> : null}

        {invoiceUploadMessage ? (
          <p className="upload-feedback success">{invoiceUploadMessage}</p>
        ) : null}

        {invoiceDeleteError ? (
          <p className="upload-feedback error">{invoiceDeleteError}</p>
        ) : null}

        {invoiceUploadError ? (
          <p className="upload-feedback error">{invoiceUploadError}</p>
        ) : null}
      </div>

     {selectedInvoice ? (
  <div className="invoice-preview-backdrop">
    <div className="invoice-preview-modal only-document">
      <button
        type="button"
        className="invoice-preview-floating-close"
        onClick={closeInvoicePreview}
      >
        ✕
      </button>

      <div className="invoice-preview-body invoice-preview-body-only-document">
        {selectedInvoiceDocumentUrl ? (
          <div className="invoice-preview-document full">
            {selectedInvoiceDocumentUrl.match(/\.(jpg|jpeg|png|webp)$/i) ? (
              <img
                src={selectedInvoiceDocumentUrl}
                alt="Fattura"
              />
            ) : (
              <iframe
                title="Documento fattura"
                src={selectedInvoiceDocumentUrl}
              />
            )}
          </div>
        ) : (
          <div className="invoice-preview-empty">
            <div>🧾</div>
            <h3>Documento non disponibile</h3>
            <p>
              Questa fattura non ha un file associato.
            </p>
          </div>
        )}
      </div>
    </div>
  </div>
) : null}

      {manualOpen ? (
        <div className="invoice-manual-modal-backdrop">
          <div className="invoice-manual-modal">
            <div className="invoice-manual-modal-head">
              <div>
                <h2>Inserisci fattura manuale</h2>
                <p>Compila tutti i campi per salvare la fattura.</p>
              </div>

              <button type="button" onClick={closeManualModal} disabled={manualSaving}>
                ✕
              </button>
            </div>

            <div className="invoice-manual-grid">
              <input
                value={manualForm.supplier}
                onChange={(event) => updateManualForm("supplier", event.target.value)}
                placeholder="Fornitore"
              />

              <input
                value={manualForm.invoice_number}
                onChange={(event) =>
                  updateManualForm("invoice_number", event.target.value)
                }
                placeholder="Numero fattura"
              />

              <input
                type="date"
                value={manualForm.due_date}
                onChange={(event) => updateManualForm("due_date", event.target.value)}
              />

              <input
                value={manualForm.category}
                onChange={(event) => updateManualForm("category", event.target.value)}
                placeholder="Categoria"
              />

              <input
                type="number"
                min="0"
                step="0.01"
                value={manualForm.total}
                onChange={(event) => updateManualForm("total", event.target.value)}
                placeholder="Totale"
              />

              <input
                type="number"
                min="0"
                step="0.01"
                value={manualForm.vat}
                onChange={(event) => updateManualForm("vat", event.target.value)}
                placeholder="IVA"
              />
            </div>

            {manualError ? <p className="upload-feedback error">{manualError}</p> : null}

            <div className="invoice-manual-actions">
              <button type="button" onClick={closeManualModal} disabled={manualSaving}>
                Annulla
              </button>

              <button
                type="button"
                className="invoice-upload-btn"
                onClick={submitManualInvoice}
                disabled={manualSaving}
              >
                {manualSaving ? "Salvataggio..." : "Salva fattura"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}