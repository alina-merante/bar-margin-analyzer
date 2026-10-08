
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AlertBanner from "../components/AlertBanner.jsx";
import {
  getCalendarDate,
  getInvoiceDateStatus,
  isInvoiceDue,
  isInvoiceInDueMonth,
  isInvoiceOverdue,
  isInvoiceOverdueInCurrentYear,
} from "../invoiceDateStatus";
import {
  countInvoicesByCategory,
  filterInvoiceList,
  mergeUniqueInvoices,
} from "../invoiceCollections";

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);
}

function getInvoiceRemainingAmount(invoice = {}) {
  const total = Number(invoice.total) || 0;
  const linkedAmount = Number(invoice.linked_amount) || 0;
  const remainingAmount = invoice.remaining_amount ?? total - linkedAmount;
  return Math.max(0, Number(remainingAmount) || 0);
}

function formatDate(value) {
  if (!value) return "-";

  const date = getCalendarDate(value);
  if (!date) return "-";

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

function normalizeSearchText(value = "") {
  return String(value)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getCategoryIcon(category = "") {
  const lower = category.toLowerCase();

  if (lower.includes("caff")) return "☕";
  if (lower.includes("latte") || lower.includes("lattiero")) return "🥛";
  if (lower.includes("dolci") || lower.includes("pane") || lower.includes("pastic")) {
    return "🥐";
  }
  if (lower.includes("bevande")) return "🍹";
  if (lower.includes("serviz") || lower.includes("manutenz")) return "🛠️";
  if (lower.includes("utenz") || lower.includes("energia") || lower.includes("luce")) {
    return "💡";
  }

  return "🧾";
}

function getCategoryTone(category = "") {
  const lower = category.toLowerCase();

  if (lower.includes("caff")) return "caffe";
  if (lower.includes("latte") || lower.includes("lattiero")) return "latte";
  if (lower.includes("dolci") || lower.includes("pane") || lower.includes("pastic")) {
    return "dolci";
  }
  if (lower.includes("bevande") || lower.includes("soft")) return "bevande";
  if (lower.includes("serviz") || lower.includes("manutenz")) return "servizi";
  if (
    lower.includes("utenz") ||
    lower.includes("serviz") ||
    lower.includes("energia") ||
    lower.includes("luce") ||
    lower.includes("gas")
  ) {
    return "utenze";
  }

  return "altro";
}

function getCategoryCardIcon(category = "") {
  return getCategoryTone(category) === "altro" ? "📦" : getCategoryIcon(category);
}

function getCategoryLabel(invoice, knownCategories = []) {
  const category = invoice.category?.trim();
  if (category) return category;

  const supplier = normalizeSearchText(invoice.supplier || "");
  const invoiceNumber = normalizeSearchText(invoice.invoice_number || "");

  const matchedKnownCategory = knownCategories.find((item) => {
    const normalizedCategory = normalizeSearchText(item);
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
    return "Caffè";
  }

  if (supplier.includes("caff") || supplier.includes("vergnano") || supplier.includes("torrefazione")) {
    return "Caffè";
  }
  if (supplier.includes("latte") || supplier.includes("lattiero")) return "Latticini";
  if (supplier.includes("dolci") || supplier.includes("pane") || supplier.includes("pastic")) {
    return "Pasticceria";
  }
  if (supplier.includes("bevande") || supplier.includes("drink") || supplier.includes("birra") || supplier.includes("wine")) {
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

  return "Altro";
}

function buildPdfPreviewUrl(url) {
  if (!url) return "";
  if (!/\.pdf($|[?#])/i.test(url)) return url;
  if (url.includes("#")) return url;
  return `${url}#toolbar=0&navpanes=0&scrollbar=1&view=FitH`;
}

function getInvoiceNumberDisplay(invoiceNumber) {
  const value = String(invoiceNumber || "").trim();
  if (!value) return "-";
  if (/^AUTO-\d+/i.test(value)) return "-";
  return value;
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
  issue_date: "",
  due_date: "",
  category: "",
  total: "",
  vat: "",
};

export default function InvoicesPage({
  month,
  invoices = [],
  invoiceCategories = [],
  invoiceReconciliationMessage,
  handleLoadTransactionCandidates,
  handleReconcileTransaction,
  invoiceUploadMessage,
  invoiceUploadError,
  dismissUploadFeedback,
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
  const [reconciliationInvoice, setReconciliationInvoice] = useState(null);
  const [reconciliationData, setReconciliationData] = useState(null);
  const [reconciliationLoading, setReconciliationLoading] = useState(false);
  const [reconciliationError, setReconciliationError] = useState("");
  const [candidateToConfirm, setCandidateToConfirm] = useState(null);
  const [reconciliationSaving, setReconciliationSaving] = useState(false);
  const reconciliationRequestRef = useRef(0);
  const [isYearView, setIsYearView] = useState(false);
  const [categoryDropdownOpen, setCategoryDropdownOpen] = useState(false);
  const [categorySearch, setCategorySearch] = useState("");
  const [draftCategoryFilter, setDraftCategoryFilter] = useState("");
  const categoryPopoverRef = useRef(null);
  const invoiceTableRef = useRef(null);

  const [searchParams] = useSearchParams();

useEffect(() => {
  const tab = searchParams.get("tab");
  if (tab === "overdue") {
    setStatusFilter("overdue");
    setIsYearView(false);
  } else if (tab === "year-overdue") {
    setStatusFilter("year-overdue");
    setIsYearView(true);
  }
}, [searchParams]);

  useEffect(() => {
    if (!categoryDropdownOpen) return undefined;

    function handlePointerDown(event) {
      if (!categoryPopoverRef.current?.contains(event.target)) {
        setCategoryDropdownOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [categoryDropdownOpen]);

  useEffect(() => {
    if (categoryDropdownOpen) {
      setDraftCategoryFilter(categoryFilter);
    }
  }, [categoryDropdownOpen, categoryFilter]);

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

  async function openReconciliation(invoice) {
    const requestId = reconciliationRequestRef.current + 1;
    reconciliationRequestRef.current = requestId;
    setReconciliationInvoice(invoice);
    setReconciliationData(null);
    setCandidateToConfirm(null);
    setReconciliationError("");
    setReconciliationLoading(true);

    try {
      const result = await handleLoadTransactionCandidates(invoice.id);
      if (reconciliationRequestRef.current === requestId) {
        setReconciliationData(result);
      }
    } catch (error) {
      if (reconciliationRequestRef.current === requestId) {
        setReconciliationError(error.message || "Impossibile caricare i movimenti candidati.");
      }
    } finally {
      if (reconciliationRequestRef.current === requestId) {
        setReconciliationLoading(false);
      }
    }
  }

  function closeReconciliation() {
    if (reconciliationSaving) return;
    dismissReconciliation();
  }

  function dismissReconciliation() {
    reconciliationRequestRef.current += 1;
    setReconciliationInvoice(null);
    setReconciliationData(null);
    setCandidateToConfirm(null);
    setReconciliationError("");
  }

  async function confirmReconciliation() {
    if (!reconciliationInvoice || !candidateToConfirm || reconciliationSaving) return;

    setReconciliationSaving(true);
    setReconciliationError("");
    try {
      await handleReconcileTransaction(reconciliationInvoice.id, candidateToConfirm.id);
      dismissReconciliation();
    } catch (error) {
      setReconciliationError(error.message || "Riconciliazione non riuscita.");
    } finally {
      setReconciliationSaving(false);
    }
  }

  useEffect(() => {
    if (!reconciliationInvoice || reconciliationSaving) return undefined;

    function handleEscape(event) {
      if (event.key !== "Escape" || reconciliationSaving) return;
      reconciliationRequestRef.current += 1;
      setReconciliationInvoice(null);
      setReconciliationData(null);
      setCandidateToConfirm(null);
      setReconciliationError("");
    }

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [reconciliationInvoice, reconciliationSaving]);

  function scrollToInvoicesTable() {
    requestAnimationFrame(() => {
      invoiceTableRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }

  async function submitManualInvoice() {
    if (!manualForm.issue_date.trim()) {
      setManualError("Inserisci la data della fattura.");
      return;
    }

    const requiredFields = [
      "supplier",
      "invoice_number",
      "issue_date",
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
        issue_date: manualForm.issue_date,
        due_date: manualForm.due_date,
        category: manualForm.category.trim(),
        total: Number(manualForm.total),
        vat: Number(manualForm.vat),
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

  const currentYear = new Date().getFullYear();

  const currentMonthInvoices = useMemo(() => {
    return invoices.filter((invoice) => isInvoiceInDueMonth(invoice, month));
  }, [invoices, month]);

  const yearOverdueInvoices = useMemo(
    () => invoices.filter(isInvoiceOverdueInCurrentYear),
    [invoices]
  );

  const invoicesForView = useMemo(() => {
    if (statusFilter === "year-overdue") {
      setIsYearView(true);
      return yearOverdueInvoices;
    }

    if (isYearView && ["paid", "due", "overdue"].includes(statusFilter)) {
      return yearOverdueInvoices.filter((invoice) => {
        const status = getInvoiceDateStatus(invoice);
        return status === statusFilter;
      });
    }

    if (statusFilter === "overdue") {
      return currentMonthInvoices.filter(isInvoiceOverdue);
    }

    return currentMonthInvoices;
  }, [currentMonthInvoices, yearOverdueInvoices, statusFilter, isYearView]);

  const paidInvoices = invoicesForView.filter((invoice) => invoice.status === "paid");
  const dueInvoices = invoicesForView.filter(isInvoiceDue);
  const overdueInvoices = invoicesForView.filter(isInvoiceOverdue);

  // Numero di fatture per i pulsanti filtri: sempre del mese corrente
  const monthPaidInvoices = currentMonthInvoices.filter((invoice) => invoice.status === "paid");
  const monthDueInvoices = currentMonthInvoices.filter(isInvoiceDue);
  const monthOverdueInvoices = currentMonthInvoices.filter(isInvoiceOverdue);

  // Importi totali sempre del mese corrente (per le cornici KPI)
  const monthTotalAmount = currentMonthInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const monthPaidAmount = monthPaidInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const monthDueAmount = monthDueInvoices.reduce(
    (sum, invoice) => sum + getInvoiceRemainingAmount(invoice),
    0
  );

  const monthOverdueAmount = monthOverdueInvoices.reduce(
    (sum, invoice) => sum + getInvoiceRemainingAmount(invoice),
    0
  );

  const yearOverdueTotal = yearOverdueInvoices.reduce(
    (sum, invoice) => sum + getInvoiceRemainingAmount(invoice),
    0
  );

  const knownCategoryNames = useMemo(() => {
    return invoiceCategories
      .map((category) => category?.name?.trim())
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "it"));
  }, [invoiceCategories]);

  const allVisibleInvoices = useMemo(
    () => mergeUniqueInvoices(currentMonthInvoices, yearOverdueInvoices),
    [currentMonthInvoices, yearOverdueInvoices]
  );

  const categoryOptions = useMemo(() => {
    const counts = new Map();

    knownCategoryNames.forEach((label) => {
      counts.set(label, 0);
    });

    countInvoicesByCategory(allVisibleInvoices, (invoice) =>
      getCategoryLabel(invoice, knownCategoryNames)
    ).forEach((count, label) => {
      counts.set(label, (counts.get(label) || 0) + count);
    });

    return Array.from(counts.entries())
      .map(([label, count]) => ({
        label,
        count,
        icon: getCategoryCardIcon(label),
        tone: getCategoryTone(label),
      }))
      .sort((a, b) => a.label.localeCompare(b.label, "it"));
  }, [allVisibleInvoices, knownCategoryNames]);

  const filteredCategoryOptions = useMemo(() => {
    const normalizedSearch = categorySearch.trim().toLowerCase();
    if (!normalizedSearch) return categoryOptions;

    return categoryOptions.filter((category) =>
      category.label.toLowerCase().includes(normalizedSearch)
    );
  }, [categoryOptions, categorySearch]);

  const selectedCategoryMeta = useMemo(() => {
    return categoryOptions.find((category) => category.label === categoryFilter) || null;
  }, [categoryOptions, categoryFilter]);

  const invoiceSearchScope = useMemo(() => {
    const normalizedSupplierSearch = supplierSearch.trim();
    return normalizedSupplierSearch ? allVisibleInvoices : invoicesForView;
  }, [supplierSearch, allVisibleInvoices, invoicesForView]);

  const filteredInvoices = useMemo(() => {
    const normalizedSupplierSearch = supplierSearch.trim().toLowerCase();
    const invoicesToFilter = normalizedSupplierSearch ? allVisibleInvoices : invoicesForView;

    return filterInvoiceList(invoicesToFilter, {
      supplierSearch,
      statusFilter,
      categoryFilter,
      categoryForInvoice: (invoice) => getCategoryLabel(invoice, knownCategoryNames),
    });
}, [invoicesForView, allVisibleInvoices, statusFilter, supplierSearch, categoryFilter, knownCategoryNames]);

  const paidAmount = paidInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const dueAmount = dueInvoices.reduce(
    (sum, invoice) => sum + getInvoiceRemainingAmount(invoice),
    0
  );

  const overdueAmount = overdueInvoices.reduce(
    (sum, invoice) => sum + getInvoiceRemainingAmount(invoice),
    0
  );

  const selectedInvoiceDocumentUrl = getInvoiceDocumentUrl(selectedInvoice);
  const selectedInvoiceIsImage = /\.(jpg|jpeg|png|webp)($|[?#])/i.test(selectedInvoiceDocumentUrl);
  const selectedInvoicePreviewUrl = buildPdfPreviewUrl(selectedInvoiceDocumentUrl);

  return (
    <main className="main invoices-dashboard-page">
      <section className="invoices-dashboard-header">
        <div>
          <h1 className="invoices-dashboard-title">Fatture 🧾</h1>
          <p className="invoices-dashboard-subtitle">
            {statusFilter === "year-overdue" ? (
              `Arretrati anno ${currentYear} · ${yearOverdueInvoices.length} fatture`
            ) : (
              formatMonthHuman(month)
            )}
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
          <div className="invoice-kpi-value">{formatEuro(monthTotalAmount)}</div>
          <span className="invoice-kpi-pill blue">
            {currentMonthInvoices.length} documenti
          </span>
        </article>

        <article className="invoice-kpi-card">
          <div className="invoice-kpi-label">Pagate</div>
          <div className="invoice-kpi-value">{formatEuro(monthPaidAmount)}</div>
          <span className="invoice-kpi-pill green">✓ {monthPaidInvoices.length} fatture</span>
        </article>

        <article className="invoice-kpi-card">
          <div className="invoice-kpi-label">In scadenza</div>
          <div className="invoice-kpi-value">{formatEuro(monthDueAmount)}</div>
          {monthDueInvoices.length ? (
            <span className="invoice-kpi-pill yellow">⏰ {monthDueInvoices.length} fatture</span>
          ) : (
            <span className="invoice-kpi-pill green">✓ Nessuna fattura in scadenza</span>
          )}
        </article>

        <article className="invoice-kpi-card dark">
          <div className="invoice-kpi-label">Scadute</div>
          <div className="invoice-kpi-value">{formatEuro(monthOverdueAmount)}</div>
          <span className={`invoice-kpi-pill ${monthOverdueInvoices.length ? "red" : "green"}`}>
            {monthOverdueInvoices.length ? "⚠ Pagamento urgente" : "✓ Nessuna fattura scaduta"}
          </span>
        </article>

        <article
          className={`invoice-kpi-card overdue ${yearOverdueInvoices.length ? "has-arrears" : "clear"}`}
          style={{ cursor: "pointer" }}
          onClick={() => {
            setStatusFilter("year-overdue");
            setIsYearView(true);
            setCategoryFilter("");
          }}
        >
          <div className="invoice-kpi-label">Arretrati {currentYear}</div>
          <div className="invoice-kpi-value">{formatEuro(yearOverdueTotal)}</div>
          {yearOverdueInvoices.length ? (
            <span className="invoice-kpi-pill red">
              ⚠ {yearOverdueInvoices.length} fatture
            </span>
          ) : (
            <span className="invoice-kpi-pill green">✓ Nessun arretrato</span>
          )}
        </article>
      </section>

      <section className="invoice-filters-row">
        <button
          type="button"
          className={`invoice-status-filter ${statusFilter === "all" ? "active" : ""}`}
          onClick={() => {
            setStatusFilter("all");
            setIsYearView(false);
            setCategoryFilter("");
          }}
        >
          Tutte ({currentMonthInvoices.length})
        </button>

        <button
          type="button"
          className={`invoice-status-filter ${statusFilter === "paid" ? "active" : ""}`}
          onClick={() => {
            setStatusFilter("paid");
            setIsYearView(false);
            setCategoryFilter("");
          }}
        >
          ✓ Pagate ({monthPaidInvoices.length})
        </button>

        <button
          type="button"
          className={`invoice-status-filter ${statusFilter === "due" ? "active" : ""}`}
          onClick={() => {
            setStatusFilter("due");
            setIsYearView(false);
            setCategoryFilter("");
          }}
        >
          ⏰ In scadenza ({monthDueInvoices.length})
        </button>

        <button
          type="button"
          className={`invoice-status-filter ${
            statusFilter === "overdue" ? "active danger" : ""
          }`}
          onClick={() => {
            setStatusFilter("overdue");
            setIsYearView(false);
            setCategoryFilter("");
          }}
        >
          ✗ Scadute ({monthOverdueInvoices.length})
        </button>

        <div className="invoice-category-filter-bar">
          <div className="invoice-category-dropdown-wrapper" ref={categoryPopoverRef}>
            <button
              type="button"
              className={`invoice-status-filter invoice-category-dropdown-btn ${categoryDropdownOpen ? "open" : ""}`}
              onClick={() => setCategoryDropdownOpen((open) => !open)}
            >
              <span className="invoice-category-dropdown-btn-icon">🏷️</span>
              <span className="invoice-category-dropdown-btn-label">
                {selectedCategoryMeta?.label || "Categoria"}
              </span>
              <span className="invoice-category-dropdown-btn-arrow">▼</span>
            </button>

            {categoryDropdownOpen ? (
              <div className="invoice-category-popover-menu">
                <div className="invoice-category-popover-header">
                  <div>
                    <div className="invoice-category-popover-title">Seleziona categoria</div>
                    <div className="invoice-category-popover-subtitle">
                      {filteredInvoices.length} fatture trovate
                    </div>
                  </div>

                  <div className="invoice-category-search-wrap">
                    <span>🔍</span>
                    <input
                      type="text"
                      value={categorySearch}
                      onChange={(event) => setCategorySearch(event.target.value)}
                      placeholder="Cerca categoria..."
                    />
                  </div>
                </div>

                <div className="invoice-category-grid">
                  {filteredCategoryOptions.length ? (
                    filteredCategoryOptions.map((category) => (
                      <button
                        key={category.label}
                        type="button"
                        className={`invoice-category-card ${category.tone} ${
                          draftCategoryFilter === category.label ? "active" : ""
                        }`}
                        onClick={() => setDraftCategoryFilter(category.label)}
                      >
                        <span className="invoice-category-card-icon">{category.icon}</span>
                        <span className="invoice-category-card-name">{category.label}</span>
                        <span className="invoice-category-card-count">
                          {category.count} {category.count === 1 ? "fattura" : "fatture"}
                        </span>
                      </button>
                    ))
                  ) : (
                    <div className="invoice-category-empty-state">
                      Nessuna categoria compatibile con la ricerca.
                    </div>
                  )}
                </div>

                <div className="invoice-category-popover-footer">
                  <button
                    type="button"
                    className="invoice-category-reset-btn"
                    onClick={() => {
                      setCategoryFilter("");
                      setDraftCategoryFilter("");
                      setCategorySearch("");
                      setCategoryDropdownOpen(false);
                    }}
                  >
                    ✕ Reset filtro
                  </button>

                  <button
                    type="button"
                    className="invoice-category-apply-btn"
                    onClick={() => {
                      setStatusFilter("all");
                      setIsYearView(false);
                      setCategoryFilter(draftCategoryFilter);
                      setCategoryDropdownOpen(false);
                      scrollToInvoicesTable();
                    }}
                  >
                    Applica
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="invoice-search-box">
            🔍
            <input
              value={supplierSearch}
              onChange={(event) => setSupplierSearch(event.target.value)}
              placeholder="Cerca fornitore..."
            />
          </div>
        </div>

        <button
          type="button"
          className={`invoice-status-filter ${
            statusFilter === "year-overdue" ? "active danger" : ""
          }`}
          onClick={() => {
            setStatusFilter("year-overdue");
            setIsYearView(true);
            setCategoryFilter("");
          }}
        >
          📅 Arretrati {currentYear} ({yearOverdueInvoices.length})
        </button>

      </section>

      {invoiceUploadMessage ? (
        <AlertBanner
          variant="success"
          onClose={() => dismissUploadFeedback?.("invoiceMessage")}
        >
          {invoiceUploadMessage}
        </AlertBanner>
      ) : null}

      {invoiceReconciliationMessage ? (
        <p className="upload-feedback success" role="status">{invoiceReconciliationMessage}</p>
      ) : null}

      {invoiceUploadError ? (
        <AlertBanner
          variant={invoiceUploadError.variant}
          title={invoiceUploadError.title}
          onClose={() => dismissUploadFeedback?.("invoiceError")}
        >
          {invoiceUploadError.message}
        </AlertBanner>
      ) : null}

      {invoiceDeleteError ? (
        <p className="upload-feedback error">{invoiceDeleteError}</p>
      ) : null}

      <section className="invoice-modern-table-card" ref={invoiceTableRef}>
        <div className="invoice-clean-table-head">
          <div>FORNITORE</div>
          <div>N° FATTURA</div>
          <div>SCADENZA</div>
          <div>CATEGORIA</div>
          <div>TOTALE</div>
          <div>VISUALIZZA</div>
          <div>PAGAMENTO</div>
          <div>ELIMINA</div>
        </div>

        {filteredInvoices.length ? (
          filteredInvoices.map((invoice) => {
            const status = getInvoiceDateStatus(invoice);
            const linkedAmount = Number(invoice.linked_amount) || 0;
            const remainingAmount = getInvoiceRemainingAmount(invoice);
            const isPartiallyPaid = linkedAmount > 0 && remainingAmount > 0;

            return (
              <div className={`invoice-clean-table-row ${status}`} key={invoice.id}>
                <div className="invoice-modern-supplier">{invoice.supplier || "Fornitore"}</div>

                <div className="invoice-modern-number">
                  {getInvoiceNumberDisplay(invoice.invoice_number)}
                </div>

                <div
                  className={`invoice-modern-due ${
                    statusFilter === "year-overdue" ? "invoice-modern-due-year-overdue" : ""
                  }`}
                >
                  {formatDate(invoice.due_date)}
                  {status === "overdue" ? (
                    <small className="invoice-due-status overdue">Scaduta</small>
                  ) : null}
                  {status === "due" ? (
                    <small className="invoice-due-status due">In scadenza</small>
                  ) : null}
                </div>

                <div className="invoice-modern-category">
                  {getCategoryIcon(getCategoryLabel(invoice, knownCategoryNames))} {getCategoryLabel(
                    invoice,
                    knownCategoryNames
                  )}
                </div>

                <div className="invoice-modern-total">
                  <strong>{formatEuro(invoice.total)}</strong>
                </div>

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

                <div className="invoice-action-cell invoice-payment-cell">
                  {invoice.status === "paid" ? (
                    <span className="invoice-payment-paid">✓ Pagata</span>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="invoice-reconcile-btn"
                        onClick={() => openReconciliation(invoice)}
                      >
                        Abbina pagamento
                      </button>
                      {isPartiallyPaid ? (
                        <small className="invoice-payment-summary">
                          Pagato {formatEuro(linkedAmount)} · Residuo {formatEuro(remainingAmount)}
                        </small>
                      ) : null}
                    </>
                  )}
                </div>

                <div className="invoice-action-cell">
                  <button
                    type="button"
                    className={`invoice-icon-btn delete ${Number(invoice.linked_amount) > 0 ? "disabled" : ""}`}
                    disabled={Number(invoice.linked_amount) > 0}
                    onClick={() => {
                      if (window.confirm("Vuoi eliminare questa fattura?")) {
                        handleDeleteInvoice(invoice.id);
                      }
                    }}
                    title={
                      Number(invoice.linked_amount) > 0
                        ? "Fattura non eliminabile: contiene pagamenti riconciliati."
                        : "Elimina fattura"
                    }
                    aria-label={
                      Number(invoice.linked_amount) > 0
                        ? "Fattura non eliminabile perché contiene pagamenti riconciliati"
                        : "Elimina fattura"
                    }
                  >
                    🗑️
                  </button>
                </div>
              </div>
            );
          })
        ) : (
          <p className="small-muted">Nessuna fattura disponibile con i filtri selezionati.</p>
        )}

        {filteredInvoices.length ? (
          <div className="invoice-table-footer">
            Mostrate {filteredInvoices.length} di {invoiceSearchScope.length} fatture
          </div>
        ) : null}
      </section>

      {reconciliationInvoice ? (
        <div
          className="invoice-reconciliation-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeReconciliation();
          }}
        >
          <section
            className="invoice-reconciliation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="invoice-reconciliation-title"
          >
            <header className="invoice-reconciliation-head">
              <div>
                <p className="invoice-reconciliation-eyebrow">RICONCILIAZIONE BANCARIA</p>
                <h2 id="invoice-reconciliation-title">Abbina pagamento</h2>
                <p>Seleziona un movimento e conferma l’abbinamento alla fattura.</p>
              </div>
              <button
                type="button"
                className="invoice-reconciliation-close"
                onClick={closeReconciliation}
                disabled={reconciliationSaving}
                aria-label="Chiudi"
              >
                ✕
              </button>
            </header>

            <div className="invoice-reconciliation-summary">
              <div>
                <span>Fornitore</span>
                <strong>{reconciliationInvoice.supplier || "Fornitore"}</strong>
              </div>
              <div>
                <span>Fattura</span>
                <strong>{getInvoiceNumberDisplay(reconciliationInvoice.invoice_number)}</strong>
              </div>
              <div>
                <span>Totale</span>
                <strong>{formatEuro(reconciliationInvoice.total)}</strong>
              </div>
              <div>
                <span>Già pagato</span>
                <strong>
                  {formatEuro(reconciliationData?.linked_amount ?? reconciliationInvoice.linked_amount ?? 0)}
                </strong>
              </div>
              <div>
                <span>Residuo</span>
                <strong className="invoice-reconciliation-residual">
                  {formatEuro(reconciliationData?.remaining_amount ?? reconciliationInvoice.remaining_amount ?? 0)}
                </strong>
              </div>
            </div>

            {reconciliationLoading ? (
              <p className="invoice-reconciliation-state" role="status">Caricamento movimenti...</p>
            ) : null}

            {reconciliationError ? (
              <p className="invoice-reconciliation-error" role="alert">{reconciliationError}</p>
            ) : null}

            {!reconciliationLoading && reconciliationData?.candidates?.length === 0 ? (
              <p className="invoice-reconciliation-state">Nessun movimento bancario compatibile.</p>
            ) : null}

            {reconciliationData?.candidates?.length > 0 ? (
              <div className="invoice-reconciliation-candidates">
                {reconciliationData.candidates.map((candidate, index) => (
                  <article className="invoice-reconciliation-candidate" key={candidate.id}>
                    <div className="invoice-reconciliation-candidate-main">
                      <div className="invoice-reconciliation-candidate-meta">
                        <time dateTime={candidate.date}>{formatDate(candidate.date)}</time>
                        {index === 0 ? <span className="invoice-suggested-badge">Suggerito</span> : null}
                      </div>
                      <strong>{candidate.counterparty}</strong>
                      <p>{candidate.description}</p>
                    </div>
                    <div className="invoice-reconciliation-candidate-action">
                      <strong>
                        {formatEuro(candidate.payment_amount ?? Math.abs(Number(candidate.amount) || 0))}
                      </strong>
                      <button
                        type="button"
                        className="invoice-reconcile-btn"
                        onClick={() => setCandidateToConfirm(candidate)}
                        disabled={reconciliationSaving}
                      >
                        Abbina
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}

            {candidateToConfirm ? (
              <div className="invoice-reconciliation-confirm" role="group" aria-labelledby="invoice-reconciliation-confirm-title">
                <h3 id="invoice-reconciliation-confirm-title">Conferma abbinamento</h3>
                <p>
                  Collega il movimento del <strong>{formatDate(candidateToConfirm.date)}</strong>,
                  <strong> {candidateToConfirm.counterparty}</strong> per{" "}
                  <strong>
                    {formatEuro(candidateToConfirm.payment_amount ?? Math.abs(Number(candidateToConfirm.amount) || 0))}
                  </strong>{" "}
                  alla fattura <strong>{getInvoiceNumberDisplay(reconciliationInvoice.invoice_number)}</strong> di{" "}
                  <strong> {reconciliationInvoice.supplier}</strong> ({formatEuro(reconciliationInvoice.total)}).
                </p>
                <div className="invoice-reconciliation-confirm-actions">
                  <button
                    type="button"
                    className="invoice-reconciliation-cancel"
                    onClick={() => setCandidateToConfirm(null)}
                    disabled={reconciliationSaving}
                  >
                    Annulla
                  </button>
                  <button
                    type="button"
                    className="invoice-reconcile-btn primary"
                    onClick={confirmReconciliation}
                    disabled={reconciliationSaving}
                  >
                    {reconciliationSaving ? "Abbinamento..." : "Conferma abbinamento"}
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}

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
            {selectedInvoiceIsImage ? (
              <img
                src={selectedInvoiceDocumentUrl}
                alt="Fattura"
              />
            ) : (
              <>
                <div className="invoice-preview-toolbar">
                  <a
                    href={selectedInvoiceDocumentUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="invoice-preview-open-link"
                  >
                    Apri originale
                  </a>
                </div>

                <iframe
                  title="Documento fattura"
                  src={selectedInvoicePreviewUrl}
                />
              </>
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

              <label className="invoice-manual-date-field">
                Data fattura
                <input
                  type="date"
                  required
                  aria-label="Data fattura"
                  value={manualForm.issue_date}
                  onChange={(event) => updateManualForm("issue_date", event.target.value)}
                />
              </label>

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