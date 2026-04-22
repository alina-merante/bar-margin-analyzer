import { useMemo, useState } from "react";

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(Number(value) || 0);
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
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
  if (!month) return month;
  const [year, monthNum] = month.split("-").map(Number);
  const date = new Date(year, monthNum - 1 + delta, 1);
  const nextMonth = String(date.getMonth() + 1).padStart(2, "0");
  return `${date.getFullYear()}-${nextMonth}`;
}

function getInvoiceStatusLabel(status, dueDate) {
  if (status === "paid") return "Pagata";
  if (dueDate && new Date(dueDate) < new Date()) return "Scaduta";
  return "In scadenza";
}

function getInvoiceStatusClass(status, dueDate) {
  if (status === "paid") return "paid";
  if (dueDate && new Date(dueDate) < new Date()) return "overdue";
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
}) {
  const [supplierFilter, setSupplierFilter] = useState("");

  const suppliers = useMemo(() => {
    const unique = [...new Set(invoices.map((i) => i.supplier).filter(Boolean))];
    return unique.sort((a, b) => a.localeCompare(b, "it"));
  }, [invoices]);

  const filteredInvoices = useMemo(() => {
    return invoices.filter((invoice) => {
      const matchesMonth = !month || invoice.issue_date?.slice(0, 7) === month;
      const matchesSupplier = !supplierFilter || invoice.supplier === supplierFilter;
      return matchesMonth && matchesSupplier;
    });
  }, [invoices, month, supplierFilter]);

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
                  {
                    filteredInvoices.filter((i) => i.status === "pending").length
                  }
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

              <div className="month-filter-pretty">
                <button
                  type="button"
                  className="month-nav-btn"
                  onClick={() => setMonth(shiftMonth(month, -1))}
                >
                  ◀
                </button>

                <div className="month-filter-value">{formatMonthHuman(month)}</div>

                <button
                  type="button"
                  className="month-nav-btn"
                  onClick={() => setMonth(shiftMonth(month, 1))}
                >
                  ▶
                </button>
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
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="small-muted">Nessuna fattura disponibile con i filtri selezionati.</p>
          )}
        </div>
      </section>
    </main>
  );
}