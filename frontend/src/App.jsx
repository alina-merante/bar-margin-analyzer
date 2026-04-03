import "./App.css";

export default function App() {
  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">☕</div>
          <div className="logo-text">BarManager</div>
          <div className="logo-sub">Gestione margini</div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-label">Principale</div>
          <a className="nav-item active" href="#">
            <span className="nav-icon">📊</span>
            Dashboard
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">🧾</span>
            Fatture
            <span className="nav-badge">3</span>
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">📦</span>
            Fornitori
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">🥐</span>
            Prodotti
          </a>

          <div className="nav-label">Documenti</div>
          <a className="nav-item" href="#">
            <span className="nav-icon">⬆️</span>
            Carica file
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">📁</span>
            Archivio
          </a>

          <div className="nav-label">Analisi</div>
          <a className="nav-item" href="#">
            <span className="nav-icon">📈</span>
            Report mese
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">⚙️</span>
            Impostazioni
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="month-selector">
            <span className="month-label">◀ Marzo 2025</span>
            <span className="month-arrow">▼</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="header">
          <div>
            <div className="header-title">Buongiorno, Marco ☕</div>
            <div className="header-sub">
              Panoramica marzo 2025 · Ultimo aggiornamento oggi alle 09:14
            </div>
          </div>

          <div className="header-actions">
            <button className="btn-outline">📄 Export PDF</button>
            <button className="btn-upload">⬆ Carica documento</button>
          </div>
        </div>

        <div className="kpi-grid">
          <div className="kpi-card accent">
            <div className="kpi-deco"></div>
            <div className="kpi-label">Margine netto</div>
            <div className="kpi-value">€ 4.820</div>
            <span className="kpi-change up">↑ +8.4%</span>
            <div className="kpi-sub">vs febbraio</div>

            <div className="margin-meter">
              <div className="margin-bar-wrap">
                <div className="margin-bar-fill"></div>
              </div>
              <div className="margin-labels">
                <span>0%</span>
                <span className="margin-highlight">62%</span>
                <span>100%</span>
              </div>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-deco"></div>
            <div className="kpi-label">Ricavi totali</div>
            <div className="kpi-value">€ 12.650</div>
            <span className="kpi-change up">↑ +5.2%</span>
            <div className="kpi-sub">847 scontrini emessi</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-deco"></div>
            <div className="kpi-label">Costi totali</div>
            <div className="kpi-value">€ 7.830</div>
            <span className="kpi-change down">↑ +1.8%</span>
            <div className="kpi-sub">23 fatture ricevute</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-deco"></div>
            <div className="kpi-label">Fatture da pagare</div>
            <div className="kpi-value">€ 1.940</div>
            <span className="kpi-change warn">⚠ 3 in scadenza</span>
            <div className="kpi-sub">Prossima: 5 aprile</div>
          </div>
        </div>

        <div className="main-grid">
          <div className="card">
            <div className="card-title">Ricavi vs Costi</div>
            <div className="card-sub">Andamento ultimi 6 mesi</div>

            <div className="chart-area">
              <div className="chart-bars">
                {[
                  ["Ott", 72, 55],
                  ["Nov", 80, 60],
                  ["Dic", 95, 72],
                  ["Gen", 65, 52],
                  ["Feb", 78, 58],
                  ["Mar", 100, 62, true],
                ].map(([mese, ricavi, costi, active]) => (
                  <div className="bar-group" key={mese}>
                    <div className="bar-pair">
                      <div
                        className={`bar ${active ? "active-ricavi" : "ricavi"}`}
                        style={{ height: `${ricavi}%` }}
                      ></div>
                      <div
                        className={`bar ${active ? "active-costi" : "costi"}`}
                        style={{ height: `${costi}%` }}
                      ></div>
                    </div>
                    <div className={`bar-month ${active ? "active-month" : ""}`}>
                      {mese}
                    </div>
                  </div>
                ))}
              </div>

              <div className="chart-legend">
                <div className="legend-item">
                  <div className="legend-dot legend-ricavi"></div> Ricavi
                </div>
                <div className="legend-item">
                  <div className="legend-dot legend-costi"></div> Costi
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-title">Prodotti più venduti</div>
            <div className="card-sub">Marzo 2025 · per quantità</div>

            <div className="product-list">
              {[
                ["☕ Caffè espresso", 100, "312", "€ 468"],
                ["🥛 Cappuccino", 78, "243", "€ 486"],
                ["🥐 Cornetto", 62, "194", "€ 291"],
                ["🍊 Succo fresco", 38, "118", "€ 354"],
                ["🫖 Tè e infusi", 22, "68", "€ 102"],
              ].map(([nome, width, qty, rev], i) => (
                <div className="product-item" key={nome}>
                  <div className="product-rank">{i + 1}</div>
                  <div className="product-info">
                    <div className="product-name">{nome}</div>
                    <div className="product-bar-wrap">
                      <div
                        className="product-bar-fill"
                        style={{ width: `${width}%` }}
                      ></div>
                    </div>
                  </div>
                  <div className="product-stat">
                    <div className="product-qty">{qty}</div>
                    <div className="product-rev">{rev}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">Categorie di spesa</div>
            <div className="card-sub">Totale costi marzo</div>

            <div className="donut-wrap">
              <div className="donut-chart">
                <svg viewBox="0 0 100 100" width="130" height="130">
                  <circle
                    cx="50"
                    cy="50"
                    r="35"
                    fill="none"
                    stroke="#c8813a"
                    strokeWidth="16"
                    strokeDasharray="83.5 148.7"
                    strokeDashoffset="0"
                    transform="rotate(-90 50 50)"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="35"
                    fill="none"
                    stroke="#e0d0bc"
                    strokeWidth="16"
                    strokeDasharray="48.3 184"
                    strokeDashoffset="-83.5"
                    transform="rotate(-90 50 50)"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="35"
                    fill="none"
                    stroke="#2d7a4f"
                    strokeWidth="16"
                    strokeDasharray="39.6 192.6"
                    strokeDashoffset="-131.8"
                    transform="rotate(-90 50 50)"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="35"
                    fill="none"
                    stroke="#5a3e28"
                    strokeWidth="16"
                    strokeDasharray="30.8 201.4"
                    strokeDashoffset="-171.4"
                    transform="rotate(-90 50 50)"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="35"
                    fill="none"
                    stroke="#d4b896"
                    strokeWidth="16"
                    strokeDasharray="17.6 214.5"
                    strokeDashoffset="-202.2"
                    transform="rotate(-90 50 50)"
                  />
                </svg>

                <div className="donut-center">
                  <div className="donut-center-value">€7.8k</div>
                  <div className="donut-center-label">totale</div>
                </div>
              </div>

              <div className="donut-legend">
                {[
                  ["☕ Caffè & torref.", "€2.975", "38%", "#c8813a"],
                  ["🥛 Lattiero-caseari", "€1.723", "22%", "#e0d0bc"],
                  ["🥐 Pasticceria", "€1.409", "18%", "#2d7a4f"],
                  ["🍹 Bevande", "€1.096", "14%", "#5a3e28"],
                  ["📦 Altro", "€626", "8%", "#d4b896"],
                ].map(([name, val, pct, color]) => (
                  <div className="donut-leg-item" key={name}>
                    <div
                      className="donut-leg-dot"
                      style={{ background: color }}
                    ></div>
                    <span className="donut-leg-name">{name}</span>
                    <span className="donut-leg-val">{val}</span>
                    <span className="donut-leg-pct">{pct}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="bottom-grid">
          <div className="card">
            <div className="card-title">Top Fornitori</div>
            <div className="card-sub">Per spesa · marzo 2025</div>

            <div className="supplier-list">
              {[
                ["☕", "Torrefazione Vergnano", "Caffè & miscele", "€ 1.840", "3 fatture", "#fff5e8"],
                ["🥛", "Cooperativa Latte Milano", "Latte & derivati", "€ 1.230", "4 fatture", "#f0f8f4"],
                ["🥐", "Pasticceria De Luca", "Cornetti & dolci", "€ 980", "8 consegne", "#fff8f0"],
                ["🍹", "Distributori Riuniti", "Bevande & soft drink", "€ 754", "2 fatture", "#f5f0ff"],
              ].map(([icon, name, cat, total, inv, bg]) => (
                <div className="supplier-item" key={name}>
                  <div className="supplier-avatar" style={{ background: bg }}>
                    {icon}
                  </div>
                  <div>
                    <div className="supplier-name">{name}</div>
                    <div className="supplier-cat">{cat}</div>
                  </div>
                  <div className="supplier-amount">
                    <div className="supplier-total">{total}</div>
                    <div className="supplier-invoices">{inv}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">Fatture recenti</div>
            <div className="card-sub">
              Stato pagamenti · ultimo aggiornamento oggi
            </div>

            <div className="invoice-list">
              <div className="invoice-item paid">
                <div className="invoice-dot"></div>
                <div className="invoice-info">
                  <div className="invoice-name">Torrefazione Vergnano</div>
                  <div className="invoice-date">Emessa: 1 mar · Pagata: 8 mar</div>
                </div>
                <div className="invoice-amount">€ 612</div>
                <div className="invoice-status">Pagata</div>
              </div>

              <div className="invoice-item due">
                <div className="invoice-dot"></div>
                <div className="invoice-info">
                  <div className="invoice-name">Pasticceria De Luca</div>
                  <div className="invoice-date">Emessa: 20 mar · Scade: 5 apr</div>
                </div>
                <div className="invoice-amount">€ 490</div>
                <div className="invoice-status">In scadenza</div>
              </div>

              <div className="invoice-item overdue">
                <div className="invoice-dot"></div>
                <div className="invoice-info">
                  <div className="invoice-name">Distributori Riuniti</div>
                  <div className="invoice-date">Emessa: 15 mar · Scaduta: 30 mar</div>
                </div>
                <div className="invoice-amount">€ 378</div>
                <div className="invoice-status">Scaduta</div>
              </div>

              <div className="invoice-item paid">
                <div className="invoice-dot"></div>
                <div className="invoice-info">
                  <div className="invoice-name">Cooperativa Latte</div>
                  <div className="invoice-date">Emessa: 5 mar · Pagata: 12 mar</div>
                </div>
                <div className="invoice-amount">€ 308</div>
                <div className="invoice-status">Pagata</div>
              </div>
            </div>

            <div className="upload-zone">
              <div className="upload-icon">📂</div>
              <div className="upload-title">Trascina qui i tuoi documenti</div>
              <div className="upload-sub">
                L'AI legge e categorizza tutto automaticamente
              </div>
              <div className="upload-types">
                <span className="upload-tag">PDF</span>
                <span className="upload-tag">XML SDI</span>
                <span className="upload-tag">Excel</span>
                <span className="upload-tag">CSV Cassa</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}