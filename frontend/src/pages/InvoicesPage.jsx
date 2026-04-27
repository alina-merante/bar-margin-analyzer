import { useEffect, useMemo, useState } from "react";

const MONTH_NAMES = [
  { value: "01", label: "Gennaio" },
  { value: "02", label: "Febbraio" },
  { value: "03", label: "Marzo" },
  { value: "04", label: "Aprile" },
  { value: "05", label: "Maggio" },
  { value: "06", label: "Giugno" },
  { value: "07", label: "Luglio" },
  { value: "08", label: "Agosto" },
  { value: "09", label: "Settembre" },
  { value: "10", label: "Ottobre" },
  { value: "11", label: "Novembre" },
  { value: "12", label: "Dicembre" },
];

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(Number(value) || 0);
}

function formatDate(value) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "long",
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

function shiftMonth(month, delta) {
  const baseMonth = month || new Date().toISOString().slice(0, 7);
  const [year, monthNum] = baseMonth.split("-").map(Number);

  const date = new Date(year, monthNum - 1 + delta, 1);
  const nextMonth = String(date.getMonth() + 1).padStart(2, "0");

  return `${date.getFullYear()}-${nextMonth}`;
}

function getInvoiceMonthKey(issueDate) {
  if (!issueDate) return "";

  if (typeof issueDate === "string") {
    const isoMatch = issueDate.match(/^(\d{4})-(\d{2})/);
    if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}`;

    const italianMatch = issueDate.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
    if (italianMatch) return `${italianMatch[3]}-${italianMatch[2]}`;
  }

  const date = new Date(issueDate);
  if (Number.isNaN(date.getTime())) return "";

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");

  return `${year}-${month}`;
}

function buildYearOptions(invoices = [], selectedMonth) {
  const years = new Set();

  invoices.forEach((invoice) => {
    const invoiceMonth = getInvoiceMonthKey(invoice.issue_date);
    const year = invoiceMonth.slice(0, 4);

    if (year) years.add(year);
  });

  if (selectedMonth) {
    years.add(selectedMonth.slice(0, 4));
  }

  const currentYear = new Date().getFullYear();

  for (let i = 0; i < 6; i += 1) {
    years.add(String(currentYear - i));
  }

  return [...years].sort((a, b) => Number(b) - Number(a));
}

function getInvoiceStatusLabel(status, dueDate) {
  if (status === "paid") return "Pagata";

  const date = dueDate ? new Date(dueDate) : null;

  if (date && !Number.isNaN(date.getTime()) && date < new Date()) {
    return "Scaduta";
  }

  return "In scadenza";
}

function getInvoiceStatusClass(status, dueDate) {
  if (status === "paid") return "paid";

  const date = dueDate ? new Date(dueDate) : null;

  if (date && !Number.isNaN(date.getTime()) && date < new Date()) {
    return "overdue";
  }

  return "due";
}

export default function InvoicesPage({
  month,
  setMonth,
  invoices = [],
  invoiceUploadMessage,
  invoiceUploadError,
  invoiceUploading,
  handleInvoiceDocumentUpload,
  handleDeleteInvoice,
  invoiceDeleteError,
}) {
  const initialMonth = month || new Date().toISOString().slice(0, 7);

  const [supplierFilter, setSupplierFilter] = useState("");
  const [isMonthPickerOpen, setIsMonthPickerOpen] = useState(false);
  const [pickerYear, setPickerYear] = useState(initialMonth.slice(0, 4));

  useEffect(() => {
    if (!month) {
      setMonth(initialMonth);
      return;
    }

    setPickerYear(month.slice(0, 4));
  }, [month, setMonth, initialMonth]);

  const suppliers = useMemo(() => {
    const unique = [...new Set(invoices.map((i) => i.supplier).filter(Boolean))];

    return unique.sort((a, b) => a.localeCompare(b, "it"));
  }, [invoices]);

  const filteredInvoices = useMemo(() => {
    return invoices.filter((invoice) => {
      const invoiceMonth = getInvoiceMonthKey(invoice.issue_date);
      const matchesMonth = !month || invoiceMonth === month;
      const matchesSupplier =
        !supplierFilter || invoice.supplier === supplierFilter;

      return matchesMonth && matchesSupplier;
    });
  }, [invoices, month, supplierFilter]);

  const yearOptions = buildYearOptions(invoices, month);
  const selectedMonthNumber = month?.slice(5, 7) || "01";

  function applyMonthYear(nextMonthNumber, nextYear) {
    setMonth(`${nextYear}-${nextMonthNumber}`);
    setIsMonthPickerOpen(false);
  }

  function goToPreviousMonth() {
    setMonth(shiftMonth(month, -1));
  }

  function goToNextMonth() {
    setMonth(shiftMonth(month, 1));
  }

  return (
    <main className="main invoices-page">
      <section className="upload-hero">
        <h1 className="upload-page-title">Fatture 🧾</h1>
        <p className="upload-page-subtitle">
          Carica una foto o un PDF della fattura e l&apos;AI estrae automaticamente i dati
        </p>
      </section>

      <section className="upload-section">
        <div className="upload-section-label">📥 Acquisizione fatture</div>

        <div className="invoice-top-grid">
          <article className="upload-doc-card warm">
            <div className="upload-doc-head">
              <div className="upload-doc-icon">🧾</div>
              <div>
                <h2 className="upload-doc-title">Carica fattura</h2>
                <p className="upload-doc-text">
                  Puoi caricare foto, scansioni o PDF. Il sistema prova a leggere automaticamente
                  fornitore, numero, date e importi.
                </p>
              </div>
            </div>

            <div className="upload-doc-tags">
              <span className="upload-doc-tag">PDF</span>
              <span className="upload-doc-tag">JPG</span>
              <span className="upload-doc-tag">PNG</span>
              <span className="upload-doc-tag">XML SDI</span>
            </div>

            <label className="upload-dropzone">
              <input
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.xml"
                hidden
                onChange={(e) => handleInvoiceDocumentUpload(e.target.files?.[0])}
              />
              <div className="upload-dropzone-icon">📂</div>
              <div className="upload-dropzone-title">Trascina fattura o foto</div>
              <div className="upload-dropzone-sub">
                oppure <span>clicca per selezionare</span>
              </div>
            </label>

            <div className="upload-feedback-area">
              {invoiceUploading ? (
                <p className="upload-feedback">Estrazione dati in corso...</p>
              ) : null}

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
          </article>

          <article className="upload-doc-card cool">
            <div className="upload-doc-head">
              <div className="upload-doc-icon">📊</div>
              <div>
                <h2 className="upload-doc-title">Riepilogo fatture</h2>
                <p className="upload-doc-text">
                  Vista operativa delle fatture acquisite nel mese selezionato.
                </p>
              </div>
            </div>

            <div className="invoice-summary-grid">
              <div className="invoice-summary-box">
                <div className="invoice-summary-label">Totali</div>
                <div className="invoice-summary-value">{filteredInvoices.length}</div>
              </div>

              <div className="invoice-summary-box">
                <div className="invoice-summary-label">Da pagare</div>
                <div className="invoice-summary-value">
                  {filteredInvoices.filter((i) => i.status === "pending").length}
                </div>
              </div>

              <div className="invoice-summary-box">
                <div className="invoice-summary-label">Importo totale</div>
                <div className="invoice-summary-value">
                  {formatEuro(
                    filteredInvoices.reduce(
                      (sum, invoice) => sum + (Number(invoice.total) || 0),
                      0
                    )
                  )}
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="upload-section">
        <div className="upload-section-label">🔎 Filtri</div>

        <div className="invoice-filters-card">
          <div className="invoice-filters-grid">
            <div className="invoice-filter-field">
              <label>Mese selezionato</label>

              <div className="month-filter-pretty month-filter-popup-wrap">
                <button
                  type="button"
                  className="month-nav-btn"
                  onClick={goToPreviousMonth}
                  title="Mese precedente"
                >
                  ◀
                </button>

                <button
                  type="button"
                  className="month-filter-trigger"
                  onClick={() => setIsMonthPickerOpen((prev) => !prev)}
                >
                  <span>{formatMonthHuman(month)}</span>
                  <span className="month-filter-trigger-icon">▾</span>
                </button>

                <button
                  type="button"
                  className="month-nav-btn"
                  onClick={goToNextMonth}
                  title="Mese successivo"
                >
                  ▶
                </button>

                {isMonthPickerOpen ? (
                  <div className="month-picker-popover">
                    <div className="month-picker-popover-title">
                      Seleziona periodo
                    </div>

                    <div className="month-picker-year-list">
                      {yearOptions.map((year) => (
                        <button
                          key={year}
                          type="button"
                          className={`month-picker-year-btn ${
                            pickerYear === year ? "active" : ""
                          }`}
                          onClick={() => setPickerYear(year)}
                        >
                          {year}
                        </button>
                      ))}
                    </div>

                    <div className="month-picker-grid">
                      {MONTH_NAMES.map((item) => (
                        <button
                          key={item.value}
                          type="button"
                          className={`month-picker-month-btn ${
                            selectedMonthNumber === item.value &&
                            month?.slice(0, 4) === pickerYear
                              ? "active"
                              : ""
                          }`}
                          onClick={() => applyMonthYear(item.value, pickerYear)}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="invoice-filter-field">
              <label>Fornitore</label>

              <select
                value={supplierFilter}
                onChange={(e) => setSupplierFilter(e.target.value)}
              >
                <option value="">Tutti i fornitori</option>

                {suppliers.map((supplier) => (
                  <option key={supplier} value={supplier}>
                    {supplier}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </section>

      <section className="upload-section">
        <div className="upload-section-label">📋 Elenco fatture</div>

        <div className="invoice-list-card">
          {filteredInvoices.length ? (
            <div className="invoice-table">
              <div className="invoice-table-head">
                <div>Fornitore</div>
                <div>Numero</div>
                <div>Emissione</div>
                <div>Scadenza</div>
                <div>Totale</div>
                <div>Stato</div>
                <div>Azioni</div>
              </div>

              {filteredInvoices.map((invoice) => {
                const visualStatus = getInvoiceStatusClass(
                  invoice.status,
                  invoice.due_date
                );

                return (
                  <div className="invoice-table-row" key={invoice.id}>
                    <div>{invoice.supplier || "-"}</div>
                    <div>{invoice.invoice_number || "-"}</div>
                    <div>{formatDate(invoice.issue_date)}</div>
                    <div>{formatDate(invoice.due_date)}</div>
                    <div>{formatEuro(invoice.total)}</div>

                    <div>
                      <span className={`invoice-status ${visualStatus}`}>
                        {getInvoiceStatusLabel(invoice.status, invoice.due_date)}
                      </span>
                    </div>

                    <div>
                      <button
                        type="button"
                        className="invoice-delete-btn"
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
              })}
            </div>
          ) : (
            <p className="small-muted">
              Nessuna fattura disponibile con i filtri selezionati.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}