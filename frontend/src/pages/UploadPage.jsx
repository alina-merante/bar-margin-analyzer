import { useState } from "react";
import { useNavigate } from "react-router-dom";

function formatShortDate(value) {
  if (!value) return "Nessun file caricato";

  return new Intl.DateTimeFormat("it-IT", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
}

function formatMonthLabel(month) {
  if (!month) return "-";

  const [year, monthNum] = month.split("-").map(Number);

  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, monthNum - 1, 1));
}

function getDocumentPreviewUrl(document) {
  const rawUrl = document?.preview_url || document?.file_url || "";

  if (!rawUrl) return "";
  if (rawUrl.startsWith("http")) return rawUrl;

  return `/api${rawUrl}`;
}

export default function UploadPage({
  month,
  handleUpload,
  uploading,
  uploadMessage,
  uploadError,
  latestPosUploadDate,
  latestBankUploadDate,
  invoiceCountThisMonth,
  latestInvoiceDate,
  handleInvoiceDocumentUpload,

  documents = [],
  handleGenericDocumentUpload,
  handleDeleteDocument,
  documentUploading,
  documentUploadMessage,
  documentUploadError,
  documentDeleteError,
}) {
  const navigate = useNavigate();

  const [activeHistoryTab, setActiveHistoryTab] = useState("all");
  const [selectedOtherDocument, setSelectedOtherDocument] = useState(null);
  const [localDocumentMessage, setLocalDocumentMessage] = useState("");

  const selectedOtherDocumentUrl = getDocumentPreviewUrl(selectedOtherDocument);

function openOtherDocumentPreview(document) {
  setSelectedOtherDocument(document);
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

    if (handleGenericDocumentUpload) {
      await handleGenericDocumentUpload(file);
    }

    setActiveHistoryTab("cash");
  }

  async function handleOtherDocument(file) {
    if (!file) return;

    if (handleGenericDocumentUpload) {
      await handleGenericDocumentUpload(file);
    }

    setActiveHistoryTab("other");
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
              <span className="upload-doc-tag">CSV</span>
              <span className="upload-doc-tag">Excel .xlsx</span>
              <span className="upload-doc-tag">TXT</span>
            </div>

            <label className="upload-dropzone">
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.txt"
                hidden
                onChange={(e) => {
                  handleUpload(e.target.files?.[0], "pos");
                  setActiveHistoryTab("cash");
                  e.target.value = "";
                }}
              />
              <div className="upload-dropzone-icon">📂</div>
              <div className="upload-dropzone-title">Trascina export cassa</div>
              <div className="upload-dropzone-sub">
                oppure <span>clicca per selezionare</span>
              </div>
            </label>

            <div className="upload-doc-footer">
              <div className="upload-doc-meta">
                <span className="upload-doc-meta-label">Ultimo caricato:</span>
                <strong>{formatShortDate(latestPosUploadDate)}</strong>
              </div>
              <div className="upload-doc-status">✓ Elaborato correttamente</div>
            </div>
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
                onChange={(e) => {
                  handleUpload(e.target.files?.[0], "bank");
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

            <div className="upload-doc-footer">
              <div className="upload-doc-meta">
                <span className="upload-doc-meta-label">Ultimo caricato:</span>
                <strong>{formatShortDate(latestBankUploadDate)}</strong>
              </div>
              <div className="upload-doc-status">✓ Elaborato correttamente</div>
            </div>
          </article>
        </div>

        <div className="upload-feedback-area">
          {uploading || documentUploading ? (
            <p className="upload-feedback">Import in corso...</p>
          ) : null}

          {uploadMessage ? (
            <p className="upload-feedback success">{uploadMessage}</p>
          ) : null}

          {uploadError ? (
            <p className="upload-feedback error">{uploadError}</p>
          ) : null}

          {documentUploadMessage ? (
            <p className="upload-feedback success">{documentUploadMessage}</p>
          ) : null}

          {documentUploadError ? (
            <p className="upload-feedback error">{documentUploadError}</p>
          ) : null}

          {documentDeleteError ? (
            <p className="upload-feedback error">{documentDeleteError}</p>
          ) : null}

          {localDocumentMessage ? (
            <p className="upload-feedback error">{localDocumentMessage}</p>
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
              accept=".pdf,.jpg,.jpeg,.png,.xml,.webp"
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
              onClick={() =>
                document.getElementById("invoice-upload-input")?.click()
              }
            >
              <div className="upload-mini-box-icon">📄</div>
              <div className="upload-mini-box-title">Carica fattura</div>
              <div className="upload-mini-box-sub">PDF o file XML SDI</div>
            </div>

            <div className="upload-mini-footer">
              Questo mese: <strong>{invoiceCountThisMonth}</strong> fatture
              caricate
            </div>
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
              onClick={() =>
                document.getElementById("cash-document-upload-input")?.click()
              }
            >
              <div className="upload-mini-box-icon">📊</div>
              <div className="upload-mini-box-title">Carica prima nota</div>
              <div className="upload-mini-box-sub">
                Registro entrate e uscite
              </div>
            </div>

            <div className="upload-mini-footer">
              Ultima:{" "}
              <strong>{formatShortDate(latestInvoiceDate || `${month}-01`)}</strong>
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
              onClick={() =>
                document.getElementById("other-document-upload-input")?.click()
              }
            >
              <div className="upload-mini-box-icon">📂</div>
              <div className="upload-mini-box-title">Carica documento</div>
              <div className="upload-mini-box-sub">
                Qualsiasi formato supportato
              </div>
            </div>

            <div className="upload-mini-footer">
              PDF · Excel · CSV · XML · TXT
            </div>
          </article>
        </div>
      </section>

      <section className="upload-section">
        <div className="upload-history-card">
          <h2>Storico documenti caricati</h2>
          <p>{formatMonthLabel(month)} · documenti elaborati</p>

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
                navigate("/invoices");
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
              className={`history-tab ${activeHistoryTab === "other" ? "active" : ""}`}
              onClick={() => setActiveHistoryTab("other")}
            >
              Altro
            </button>
          </div>

          {activeHistoryTab === "other" ? (
            documents.length ? (
              <div className="upload-history-table">
                <div className="upload-history-table-head other-docs-table">
                  <div>Documento</div>
                  <div>Tipo</div>
                  <div>Categoria rilevata</div>
                  <div>Risultato AI</div>
                  <div>Stato</div>
                  <div>Visualizza</div>
                  <div>Elimina</div>
                </div>

                {documents.map((document) => (
                  <div
                    className="upload-history-table-row other-docs-table"
                    key={document.id}
                  >
                    <div className="upload-history-name">
                      {document.original_filename}
                    </div>
                    <div>{document.document_type}</div>
                    <div>{document.category}</div>
                    <div>{document.result}</div>
                    <div className="upload-history-status">{document.status}</div>

                    <div className="upload-history-action-cell">
                      <button
                        type="button"
                        className="invoice-icon-btn"
                        onClick={() => openOtherDocumentPreview(document)}
                        title="Visualizza documento"
                      >
                        👁️
                      </button>
                    </div>

                    <div className="upload-history-action-cell">
                      <button
                        type="button"
                        className="invoice-icon-btn delete"
                        onClick={() => handleDeleteDocument(document.id)}
                        title="Elimina documento"
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
                    Nessun altro documento caricato
                  </div>
                  <div className="upload-history-meta">
                    Carica un documento dalla sezione “Altro documento” per
                    vedere qui il risultato AI.
                  </div>
                </div>

                <div className="upload-history-status waiting">In attesa</div>
              </div>
            )
          ) : (
            <div className="upload-history-item">
              <div className="upload-history-left">
                <div className="upload-history-icon">
                  {activeHistoryTab === "invoices"
                    ? "🧾"
                    : activeHistoryTab === "cash"
                    ? "📒"
                    : "📄"}
                </div>

                <div>
                  <div className="upload-history-name">
                    {activeHistoryTab === "invoices"
                      ? "Archivio fatture"
                      : activeHistoryTab === "cash"
                      ? "Archivio cassa e prima nota"
                      : "Esempio documento caricato"}
                  </div>

                  <div className="upload-history-meta">
                    {activeHistoryTab === "invoices"
                      ? `${invoiceCountThisMonth} fatture caricate questo mese`
                      : activeHistoryTab === "cash"
                      ? `Ultimo caricamento cassa: ${formatShortDate(
                          latestPosUploadDate
                        )}`
                      : "Caricato oggi · in attesa di collegamento backend"}
                  </div>
                </div>
              </div>

              <div className="upload-history-status">Elaborato</div>
            </div>
          )}
        </div>
      </section>

      {selectedOtherDocument ? (
        <div className="invoice-preview-backdrop">
          <div className="invoice-preview-modal only-document">
            <button
              type="button"
              className="invoice-preview-floating-close"
              onClick={() => setSelectedOtherDocument(null)}
            >
              ✕
            </button>

            <div className="invoice-preview-body invoice-preview-body-only-document">
              <div className="invoice-preview-document full">
                {selectedOtherDocumentUrl ? (
  <img
    src={selectedOtherDocumentUrl}
    alt="Documento"
    className="document-preview-image"
  />
) : (
  <div className="invoice-preview-empty">
    <div>📎</div>
    <h3>Documento non disponibile</h3>
    <p>
      Il documento è stato salvato, ma non è disponibile un file di anteprima.
    </p>
  </div>
)}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}