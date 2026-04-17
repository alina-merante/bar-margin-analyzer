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
}) {
  return (
    <main className="main upload-page">
      <section className="upload-hero">
        <h1 className="upload-page-title">Carica Documenti ⬆️</h1>
        <p className="upload-page-subtitle">
        </p>
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
                onChange={(e) => handleUpload(e.target.files?.[0], "pos")}
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
                onChange={(e) => handleUpload(e.target.files?.[0], "bank")}
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
          {uploading ? (
            <p className="upload-feedback">Import in corso...</p>
          ) : null}
          {uploadMessage ? (
            <p className="upload-feedback success">{uploadMessage}</p>
          ) : null}
          {uploadError ? (
            <p className="upload-feedback error">{uploadError}</p>
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

            <div className="upload-mini-box">
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

            <div className="upload-mini-box">
              <div className="upload-mini-box-icon">📊</div>
              <div className="upload-mini-box-title">Carica prima nota</div>
              <div className="upload-mini-box-sub">
                Registro entrate e uscite
              </div>
            </div>

            <div className="upload-mini-footer">
              Ultima:{" "}
              <strong>
                {formatShortDate(latestInvoiceDate || `${month}-01`)}
              </strong>
            </div>
          </article>

          <article className="upload-mini-card">
            <div className="upload-mini-icon violet">📎</div>
            <h3>Altro documento</h3>
            <p>L'AI lo classifica automaticamente</p>

            <div className="upload-mini-box">
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
            <button className="history-tab active">Tutti</button>
            <button className="history-tab">Fatture</button>
            <button className="history-tab">Cassa</button>
            <button className="history-tab">Altro</button>
          </div>

          <div className="upload-history-item">
            <div className="upload-history-left">
              <div className="upload-history-icon">📄</div>
              <div>
                <div className="upload-history-name">
                  Esempio documento caricato
                </div>
                <div className="upload-history-meta">
                  Caricato oggi · in attesa di collegamento backend
                </div>
              </div>
            </div>
            <div className="upload-history-status">Elaborato</div>
          </div>
        </div>
      </section>
    </main>
  );
}