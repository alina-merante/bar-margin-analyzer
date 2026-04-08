import { useEffect, useMemo, useState } from "react";
import "./App.css";

const CURRENCY = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
});

const MONTH_LABEL = new Intl.DateTimeFormat("it-IT", {
  month: "long",
  year: "numeric",
});

const MONTH_SHORT = new Intl.DateTimeFormat("it-IT", {
  month: "short",
});

function formatEuro(value) {
  return CURRENCY.format(Number(value) || 0);
}

function formatMonthLabel(month) {
  if (!month) return "-";
  const [year, monthNum] = month.split("-").map(Number);
  return MONTH_LABEL.format(new Date(year, monthNum - 1, 1));
}

function formatMonthShort(month) {
  if (!month) return "-";
  const [year, monthNum] = month.split("-").map(Number);
  return MONTH_SHORT.format(new Date(year, monthNum - 1, 1));
}

function getCurrentMonth() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

async function fetchJsonOrThrow(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Errore API (${response.status})`);
  }
  return response.json();
}

function EmptyState({ message }) {
  return <p className="small-muted">{message}</p>;
}

function TrendBars({ items }) {
  if (!items.length) {
    return <EmptyState message="Dati trend non disponibili." />;
  }

  const maxValue = Math.max(
    ...items.flatMap((item) => [
      Number(item.revenue) || 0,
      Number(item.expenses) || 0,
    ]),
    1
  );

  return (
    <>
      <div className="chart-bars">
        {items.map((item, index) => {
          const revenue = Number(item.revenue) || 0;
          const expenses = Number(item.expenses) || 0;
          const revenueHeight = Math.max(10, (revenue / maxValue) * 100);
          const expensesHeight = Math.max(10, (expenses / maxValue) * 100);
          const isActive = index === items.length - 1;

          return (
            <div className="bar-group" key={item.month}>
              <div className="bar-pair">
                <div
                  className={`bar ${isActive ? "active-ricavi" : "ricavi"}`}
                  style={{ height: `${revenueHeight}%` }}
                  title={`Ricavi ${item.month}: ${formatEuro(revenue)}`}
                />
                <div
                  className={`bar ${isActive ? "active-costi" : "costi"}`}
                  style={{ height: `${expensesHeight}%` }}
                  title={`Costi ${item.month}: ${formatEuro(expenses)}`}
                />
              </div>
              <div className={`bar-month ${isActive ? "active-month" : ""}`}>
                {formatMonthShort(item.month)}
              </div>
            </div>
          );
        })}
      </div>

      <div className="chart-legend">
        <div className="legend-item">
          <div className="legend-dot legend-ricavi"></div> Ricavi
        </div>
        <div className="legend-item">
          <div className="legend-dot legend-costi"></div> Costi
        </div>
      </div>
    </>
  );
}

function getInvoiceVisualStatus(invoice) {
  if (invoice.status === "paid") return "paid";
  const today = new Date();
  const dueDate = invoice.due_date ? new Date(invoice.due_date) : null;
  if (dueDate && dueDate < today) return "overdue";
  return "due";
}

export default function App() {
  const [month, setMonth] = useState(getCurrentMonth());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [overview, setOverview] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [trend, setTrend] = useState([]);
  const [topProducts, setTopProducts] = useState({ by_quantity: [] });
  const [expensesByCategory, setExpensesByCategory] = useState({ items: [] });
  const [expensesBySupplier, setExpensesBySupplier] = useState({ items: [] });
  const [insights, setInsights] = useState({ insights: [] });

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      try {
        setLoading(true);
        setError("");

        const [
          overviewData,
          invoicesData,
          trendData,
          topProductsData,
          expensesByCategoryData,
          expensesBySupplierData,
          insightsData,
        ] = await Promise.all([
          fetchJsonOrThrow(`/api/analytics/overview?month=${month}`),
          fetchJsonOrThrow("/api/invoices"),
          fetchJsonOrThrow("/api/analytics/pnl/trend?months=6"),
          fetchJsonOrThrow(`/api/analytics/top-products?month=${month}`),
          fetchJsonOrThrow(`/api/analytics/expenses-by-category?month=${month}`),
          fetchJsonOrThrow(`/api/analytics/expenses-by-supplier?month=${month}`),
          fetchJsonOrThrow(`/api/analytics/insights?month=${month}`),
        ]);

        if (cancelled) return;

        setOverview(
          overviewData ?? {
            pnl_summary: { revenue: 0, expenses: 0, profit: 0 },
          }
        );
        setInvoices(safeArray(invoicesData));
        setTrend(safeArray(trendData));
        setTopProducts(topProductsData ?? { by_quantity: [] });
        setExpensesByCategory(expensesByCategoryData ?? { items: [] });
        setExpensesBySupplier(expensesBySupplierData ?? { items: [] });
        setInsights(insightsData ?? { insights: [] });
      } catch {
        if (cancelled) return;
        setError("Impossibile caricare i dati della dashboard.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadDashboard();

    return () => {
      cancelled = true;
    };
  }, [month]);

  const pnl = overview?.pnl_summary ?? { revenue: 0, expenses: 0, profit: 0 };

  const pendingInvoices = useMemo(
    () => invoices.filter((invoice) => invoice.status === "pending"),
    [invoices]
  );

  const pendingInvoicesAmount = useMemo(
    () =>
      pendingInvoices.reduce(
        (sum, invoice) => sum + (Number(invoice.total) || 0),
        0
      ),
    [pendingInvoices]
  );

  const recentInvoices = invoices.slice(0, 4);
  const topProductsList = safeArray(topProducts.by_quantity).slice(0, 5);
  const categoryItems = safeArray(expensesByCategory.items).slice(0, 5);
  const supplierItems = safeArray(expensesBySupplier.items).slice(0, 4);
  const insightItems = safeArray(insights.insights);

  const maxProductQty = Math.max(
    ...topProductsList.map((item) => Number(item.quantity) || 0),
    1
  );

  const previousTrend = trend.length >= 2 ? trend[trend.length - 2] : null;
  const currentTrend = trend.length >= 1 ? trend[trend.length - 1] : null;

  const profitChange =
    previousTrend && Number(previousTrend.profit) !== 0
      ? (((Number(currentTrend?.profit) || 0) - Number(previousTrend.profit)) /
          Math.abs(Number(previousTrend.profit))) *
        100
      : null;

  if (loading) {
    return (
      <main className="main">
        <p>Caricamento dashboard...</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="main">
        <p>{error}</p>
      </main>
    );
  }

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
            <span className="nav-icon">📊</span> Dashboard
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">🧾</span> Fatture
            <span className="nav-badge">{pendingInvoices.length}</span>
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">📦</span> Fornitori
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">🥐</span> Prodotti
          </a>

          <div className="nav-label">Documenti</div>
          <a className="nav-item" href="#">
            <span className="nav-icon">⬆️</span> Carica file
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">📁</span> Archivio
          </a>

          <div className="nav-label">Analisi</div>
          <a className="nav-item" href="#">
            <span className="nav-icon">📈</span> Report mese
          </a>
          <a className="nav-item" href="#">
            <span className="nav-icon">⚙️</span> Impostazioni
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="month-selector">
            <input
              className="month-input"
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="header">
          <div>
            <div className="header-title">Buongiorno ☕</div>
            <div className="header-sub">
              Panoramica {formatMonthLabel(month)} · Ultimo aggiornamento sui dati
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
            <div className="kpi-value">{formatEuro(pnl.profit)}</div>
            <span
              className={`kpi-change ${
                profitChange == null
                  ? "warn"
                  : profitChange >= 0
                  ? "up"
                  : "down"
              }`}
            >
              {profitChange == null
                ? "• nessun confronto"
                : `${profitChange >= 0 ? "↑" : "↓"} ${Math.abs(
                    profitChange
                  ).toFixed(1)}%`}
            </span>
            <div className="kpi-sub">vs mese precedente</div>

            <div className="margin-meter">
              <div className="margin-bar-wrap">
                <div
                  className="margin-bar-fill"
                  style={{
                    width: `${Math.max(
                      8,
                      Math.min(
                        100,
                        Number(pnl.revenue) > 0
                          ? (Math.max(Number(pnl.profit), 0) /
                              Number(pnl.revenue)) *
                              100
                          : 8
                      )
                    )}%`,
                  }}
                ></div>
              </div>
              <div className="margin-labels">
                <span>0%</span>
                <span className="margin-highlight">
                  {Number(pnl.revenue) > 0
                    ? `${Math.max(
                        0,
                        (Number(pnl.profit) / Number(pnl.revenue)) * 100
                      ).toFixed(0)}%`
                    : "0%"}
                </span>
                <span>100%</span>
              </div>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-deco"></div>
            <div className="kpi-label">Ricavi totali</div>
            <div className="kpi-value">{formatEuro(pnl.revenue)}</div>
            <span className="kpi-change up">↑ ricavi mese</span>
            <div className="kpi-sub">
              {topProductsList.length} prodotti in classifica
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-deco"></div>
            <div className="kpi-label">Costi totali</div>
            <div className="kpi-value">{formatEuro(pnl.expenses)}</div>
            <span className="kpi-change down">↑ spese registrate</span>
            <div className="kpi-sub">
              {categoryItems.length} categorie presenti
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-deco"></div>
            <div className="kpi-label">Fatture da pagare</div>
            <div className="kpi-value">{formatEuro(pendingInvoicesAmount)}</div>
            <span className="kpi-change warn">
              ⚠ {pendingInvoices.length} in sospeso
            </span>
            <div className="kpi-sub">
              {pendingInvoices.length > 0
                ? "Controllo richiesto"
                : "Nessuna pendenza"}
            </div>
          </div>
        </div>

        <div className="main-grid">
          <div className="card">
            <div className="card-title">Ricavi vs Costi</div>
            <div className="card-sub">Andamento ultimi 6 mesi</div>
            <div className="chart-area">
              <TrendBars items={trend} />
            </div>
          </div>

          <div className="card">
            <div className="card-title">Prodotti più venduti</div>
            <div className="card-sub">
              {formatMonthLabel(month)} · per quantità
            </div>

            <div className="product-list">
              {topProductsList.length ? (
                topProductsList.map((product, i) => {
                  const width =
                    ((Number(product.quantity) || 0) / maxProductQty) * 100;

                  return (
                    <div className="product-item" key={product.product}>
                      <div className="product-rank">{i + 1}</div>
                      <div className="product-info">
                        <div className="product-name">{product.product}</div>
                        <div className="product-bar-wrap">
                          <div
                            className="product-bar-fill"
                            style={{ width: `${Math.max(10, width)}%` }}
                          ></div>
                        </div>
                      </div>
                      <div className="product-stat">
                        <div className="product-qty">
                          {(Number(product.quantity) || 0).toFixed(0)}
                        </div>
                        <div className="product-rev">
                          {formatEuro(product.revenue)}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <EmptyState message="Nessun prodotto disponibile per questo periodo." />
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-title">Categorie di spesa</div>
            <div className="card-sub">Totale costi del mese</div>
            <div className="donut-wrap">
              {categoryItems.length ? (
                <div className="donut-legend">
                  {categoryItems.map((item, index) => {
                    const colors = [
                      "#c8813a",
                      "#e0d0bc",
                      "#2d7a4f",
                      "#5a3e28",
                      "#d4b896",
                    ];
                    const value = Math.abs(Number(item.total_amount) || 0);
                    const total = categoryItems.reduce(
                      (sum, current) =>
                        sum + Math.abs(Number(current.total_amount) || 0),
                      0
                    );
                    const pct = total > 0 ? Math.round((value / total) * 100) : 0;

                    return (
                      <div className="donut-leg-item" key={item.category}>
                        <div
                          className="donut-leg-dot"
                          style={{ background: colors[index % colors.length] }}
                        ></div>
                        <span className="donut-leg-name">{item.category}</span>
                        <span className="donut-leg-val">{formatEuro(value)}</span>
                        <span className="donut-leg-pct">{pct}%</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyState message="Nessuna spesa registrata per questo periodo." />
              )}
            </div>
          </div>
        </div>

        <div className="bottom-grid">
          <div className="card">
            <div className="card-title">Top Fornitori</div>
            <div className="card-sub">Per spesa · {formatMonthLabel(month)}</div>

            <div className="supplier-list">
              {supplierItems.length ? (
                supplierItems.map((supplier, index) => {
                  const icons = ["☕", "🥛", "🥐", "🍹"];
                  const bgs = ["#fff5e8", "#f0f8f4", "#fff8f0", "#f5f0ff"];

                  return (
                    <div
                      className="supplier-item"
                      key={`${supplier.counterparty}-${index}`}
                    >
                      <div
                        className="supplier-avatar"
                        style={{ background: bgs[index % bgs.length] }}
                      >
                        {icons[index % icons.length]}
                      </div>
                      <div>
                        <div className="supplier-name">
                          {supplier.counterparty || "N/D"}
                        </div>
                        <div className="supplier-cat">Fornitore del mese</div>
                      </div>
                      <div className="supplier-amount">
                        <div className="supplier-total">
                          {formatEuro(
                            Math.abs(Number(supplier.total_amount) || 0)
                          )}
                        </div>
                        <div className="supplier-invoices">spesa registrata</div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <EmptyState message="Nessun fornitore disponibile per questo periodo." />
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-title">Fatture recenti</div>
            <div className="card-sub">
              Stato pagamenti · ultimo aggiornamento disponibile
            </div>

            <div className="invoice-list">
              {recentInvoices.length ? (
                recentInvoices.map((invoice) => {
                  const status = getInvoiceVisualStatus(invoice);

                  return (
                    <div className={`invoice-item ${status}`} key={invoice.id}>
                      <div className="invoice-dot"></div>
                      <div className="invoice-info">
                        <div className="invoice-name">{invoice.supplier}</div>
                        <div className="invoice-date">
                          Emessa: {invoice.issue_date} · Scade: {invoice.due_date}
                        </div>
                      </div>
                      <div className="invoice-amount">
                        {formatEuro(invoice.total)}
                      </div>
                      <div className="invoice-status">
                        {status === "paid"
                          ? "Pagata"
                          : status === "overdue"
                          ? "Scaduta"
                          : "In scadenza"}
                      </div>
                    </div>
                  );
                })
              ) : (
                <EmptyState message="Nessuna fattura disponibile." />
              )}
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

        <div className="card">
          <div className="card-title">Insight automatici</div>
          <div className="card-sub">
            Suggerimenti e segnali per il mese selezionato
          </div>

          {insightItems.length ? (
            <ul className="insights-list">
              {insightItems.map((insight) => (
                <li key={insight}>{insight}</li>
              ))}
            </ul>
          ) : (
            <EmptyState message="Nessun insight disponibile per questo periodo." />
          )}
        </div>
      </main>
    </div>
  );
}