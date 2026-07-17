
import { useEffect, useMemo, useRef, useState } from "react";
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

function normalizeSearchText(value = "") {
  return String(value)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
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

function isCurrentYearOverdue(invoice) {
  if (invoice.status === "paid") return false;
  if (!invoice.due_date) return false;

  const dueDate = new Date(invoice.due_date);
  if (Number.isNaN(dueDate.getTime())) return false;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return dueDate < today && dueDate.getFullYear() === new Date().getFullYear();
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
  due_date: "",
  category: "",
  total: "",
  vat: "",
};

export default function InvoicesPage({
  month,
  invoices = [],
  invoiceCategories = [],
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

  function scrollToInvoicesTable() {
    requestAnimationFrame(() => {
      invoiceTableRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
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

  const currentYear = new Date().getFullYear();

  const currentMonthInvoices = useMemo(() => {
    return invoices.filter((invoice) => getInvoiceMonthKey(invoice.due_date) === month);
  }, [invoices, month]);

  const yearOverdueInvoices = useMemo(
    () => invoices.filter(isCurrentYearOverdue),
    [invoices]
  );

  const invoicesForView = useMemo(() => {
    if (statusFilter === "year-overdue") {
      setIsYearView(true);
      return yearOverdueInvoices;
    }

    if (isYearView && ["paid", "due", "overdue"].includes(statusFilter)) {
      return yearOverdueInvoices.filter((invoice) => {
        const status = getInvoiceStatus(invoice);
        return status === statusFilter;
      });
    }

    if (statusFilter === "overdue") {
      return currentMonthInvoices.filter(isOverdue);
    }

    return currentMonthInvoices;
  }, [currentMonthInvoices, yearOverdueInvoices, statusFilter, isYearView]);

  const paidInvoices = invoicesForView.filter((invoice) => invoice.status === "paid");
  const dueInvoices = invoicesForView.filter(isDue);
  const overdueInvoices = invoicesForView.filter(isOverdue);

  // Numero di fatture per i pulsanti filtri: sempre del mese corrente
  const monthPaidInvoices = currentMonthInvoices.filter((invoice) => invoice.status === "paid");
  const monthDueInvoices = currentMonthInvoices.filter(isDue);
  const monthOverdueInvoices = currentMonthInvoices.filter(isOverdue);

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
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const monthOverdueAmount = monthOverdueInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const yearOverdueTotal = yearOverdueInvoices.reduce(
    (sum, invoice) => sum + (Number(invoice.total) || 0),
    0
  );

  const knownCategoryNames = useMemo(() => {
    return invoiceCategories
      .map((category) => category?.name?.trim())
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "it"));
  }, [invoiceCategories]);

  const categoryOptions = useMemo(() => {
    const allInvoices = [...currentMonthInvoices, ...yearOverdueInvoices];
    const counts = new Map();

    knownCategoryNames.forEach((label) => {
      counts.set(label, 0);
    });

    allInvoices.forEach((invoice) => {
      const label = getCategoryLabel(invoice, knownCategoryNames);
      if (!label) return;
      counts.set(label, (counts.get(label) || 0) + 1);
    });

    return Array.from(counts.entries())
      .map(([label, count]) => ({
        label,
        count,
        icon: getCategoryCardIcon(label),
        tone: getCategoryTone(label),
      }))
      .sort((a, b) => a.label.localeCompare(b.label, "it"));
  }, [currentMonthInvoices, yearOverdueInvoices, knownCategoryNames]);

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

  const allVisibleInvoices = useMemo(() => {
    return [...currentMonthInvoices, ...yearOverdueInvoices];
  }, [currentMonthInvoices, yearOverdueInvoices]);

  const invoiceSearchScope = useMemo(() => {
    const normalizedSupplierSearch = supplierSearch.trim();
    return normalizedSupplierSearch ? allVisibleInvoices : invoicesForView;
  }, [supplierSearch, allVisibleInvoices, invoicesForView]);

  const filteredInvoices = useMemo(() => {
    const normalizedSupplierSearch = supplierSearch.trim().toLowerCase();
    const invoicesToFilter = normalizedSupplierSearch ? allVisibleInvoices : invoicesForView;

    return invoicesToFilter.filter((invoice) => {
      const status = getInvoiceStatus(invoice);
      const matchesStatus =
        normalizedSupplierSearch ||
        statusFilter === "all" ||
        statusFilter === "year-overdue" ||
        status === statusFilter;

      const matchesSupplier =
        !normalizedSupplierSearch ||
        invoice.supplier?.toLowerCase().includes(normalizedSupplierSearch);

      const matchesCategory =
        !categoryFilter || getCategoryLabel(invoice, knownCategoryNames) === categoryFilter;

      return matchesStatus && matchesSupplier && matchesCategory;
    });
}, [invoicesForView, allVisibleInvoices, statusFilter, supplierSearch, categoryFilter, knownCategoryNames]);

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
              <>
                {formatMonthHuman(month)} · {currentMonthInvoices.length} fatture · {" "}
                {formatEuro(totalAmount)} totale
              </>
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
          <span className="invoice-kpi-pill yellow">⏰ {monthDueInvoices.length} fatture</span>
        </article>

        <article className="invoice-kpi-card dark">
          <div className="invoice-kpi-label">Scadute</div>
          <div className="invoice-kpi-value">{formatEuro(monthOverdueAmount)}</div>
          <span className="invoice-kpi-pill red">⚠ Pagamento urgente</span>
        </article>

        <article
          className="invoice-kpi-card overdue"
          style={{ cursor: "pointer" }}
          onClick={() => {
            setStatusFilter("year-overdue");
            setIsYearView(true);
            setCategoryFilter("");
          }}
        >
          <div className="invoice-kpi-label">Arretrati {currentYear}</div>
          <div className="invoice-kpi-value">{formatEuro(yearOverdueTotal)}</div>
          <span className="invoice-kpi-pill notification-dot">
            {yearOverdueInvoices.length}
          </span>
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
        <p className="upload-feedback success">{invoiceUploadMessage}</p>
      ) : null}

      {invoiceUploadError ? (
        <p className="upload-feedback error">{invoiceUploadError}</p>
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
          <div>ELIMINA</div>
        </div>

        {filteredInvoices.length ? (
          filteredInvoices.map((invoice) => {
            const status = getInvoiceStatus(invoice);

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
                </div>

                <div className="invoice-modern-category">
                  {getCategoryIcon(getCategoryLabel(invoice, knownCategoryNames))} {getCategoryLabel(
                    invoice,
                    knownCategoryNames
                  )}
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
          <p className="small-muted">Nessuna fattura disponibile con i filtri selezionati.</p>
        )}

        {filteredInvoices.length ? (
          <div className="invoice-table-footer">
            Mostrate {filteredInvoices.length} di {invoiceSearchScope.length} fatture
          </div>
        ) : null}
      </section>

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