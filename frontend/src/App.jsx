import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import "./App.css";
import Sidebar from "./components/Sidebar";
import UploadPage from "./pages/UploadPage";
import InvoicesPage from "./pages/InvoicesPage";

const CATEGORY_COLORS = ["#c8813a", "#d8c7af", "#2d7a4f", "#6b4529", "#eadcc8"];

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

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(Number(value) || 0);
}

function formatMonthLabel(month) {
  if (!month) return "-";
  const [year, monthNum] = month.split("-").map(Number);
  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, monthNum - 1, 1));
}

function formatMonthShort(month) {
  if (!month) return "-";
  const [year, monthNum] = month.split("-").map(Number);
  return new Intl.DateTimeFormat("it-IT", {
    month: "short",
  }).format(new Date(year, monthNum - 1, 1));
}

function EmptyState({ message }) {
  return <p className="small-muted">{message}</p>;
}

function DashboardPageContent({
  month,
  loading = false,
  error = "",
  pnl = { revenue: 0, expenses: 0, profit: 0 },
  pendingInvoices = [],
  pendingInvoicesAmount = 0,
  trend = [],
  topProductsList = [],
  categoryItems = [],
  supplierItems = [],
  recentInvoices = [],
  insightItems = [],
  profitChange = null,
}) {
  const safePendingInvoices = Array.isArray(pendingInvoices) ? pendingInvoices : [];
  const safeTrend = Array.isArray(trend) ? trend : [];
  const safeTopProducts = Array.isArray(topProductsList) ? topProductsList : [];
  const safeCategoryItems = Array.isArray(categoryItems) ? categoryItems : [];
  const safeSupplierItems = Array.isArray(supplierItems) ? supplierItems : [];
  const safeRecentInvoices = Array.isArray(recentInvoices) ? recentInvoices : [];
  const safeInsightItems = Array.isArray(insightItems) ? insightItems : [];

  const maxProductQty = Math.max(
    ...safeTopProducts.map((item) => Number(item.quantity) || 0),
    1
  );

  const trendMaxValue = Math.max(
    ...safeTrend.flatMap((item) => [
      Number(item.revenue) || 0,
      Number(item.expenses) || 0,
    ]),
    1
  );

  const donutData = safeCategoryItems.map((item) => ({
    name: item.category,
    value: Math.abs(Number(item.total_amount ?? item.expenses) || 0),
  }));

  const donutTotal = donutData.reduce((sum, item) => sum + item.value, 0);

  if (loading) {
    return (
      <main className="main">
        <div className="card">
          <div className="card-title">Caricamento dashboard</div>
          <div className="card-sub">
            Sto recuperando i dati del mese selezionato.
          </div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="main">
        <div className="card">
          <div className="card-title">Errore caricamento</div>
          <div className="card-sub">{error}</div>
        </div>
      </main>
    );
  }

  return (
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
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card accent">
          <div className="kpi-deco"></div>
          <div className="kpi-label">Margine netto</div>
          <div className="kpi-value">{formatEuro(pnl.profit)}</div>
          <span
            className={`kpi-change ${
              profitChange == null ? "warn" : profitChange >= 0 ? "up" : "down"
            }`}
          >
            {profitChange == null
              ? "• nessun confronto"
              : `${profitChange >= 0 ? "↑" : "↓"} ${Math.abs(profitChange).toFixed(
                  1
                )}%`}
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
                        ? (Math.max(Number(pnl.profit), 0) / Number(pnl.revenue)) *
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
          <span className="kpi-change up">↑ ricavi registrati</span>
          <div className="kpi-sub">{safeTopProducts.length} prodotti in classifica</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-deco"></div>
          <div className="kpi-label">Costi totali</div>
          <div className="kpi-value">{formatEuro(pnl.expenses)}</div>
          <span className="kpi-change down">↑ spese registrate</span>
          <div className="kpi-sub">{safeCategoryItems.length} categorie presenti</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-deco"></div>
          <div className="kpi-label">Fatture da pagare</div>
          <div className="kpi-value">{formatEuro(pendingInvoicesAmount)}</div>
          <span className="kpi-change warn">
            ⚠ {safePendingInvoices.length} in sospeso
          </span>
          <div className="kpi-sub">
            {safePendingInvoices.length > 0
              ? "Controllo richiesto"
              : "Nessuna pendenza"}
          </div>
        </div>
      </div>

      <div className="main-grid">
        <div className="card">
          <div className="card-title">Andamento ricavi vs costi</div>
          <div className="card-sub">Andamento ultimi 6 mesi</div>

          <div className="chart-area">
            <div className="chart-bars">
              {safeTrend.length ? (
                safeTrend.map((item, index) => {
                  const revenue = Number(item.revenue) || 0;
                  const expenses = Number(item.expenses) || 0;
                  const revenueHeight = Math.max(10, (revenue / trendMaxValue) * 100);
                  const expensesHeight = Math.max(10, (expenses / trendMaxValue) * 100);
                  const isActive = index === safeTrend.length - 1;

                  return (
                    <div className="bar-group" key={item.month}>
                      <div className="bar-pair">
                        <div
                          className={`bar ${isActive ? "active-ricavi" : "ricavi"}`}
                          style={{ height: `${revenueHeight}%` }}
                          title={`Ricavi ${formatMonthLabel(item.month)}: ${formatEuro(
                            revenue
                          )}`}
                        ></div>
                        <div
                          className={`bar ${isActive ? "active-costi" : "costi"}`}
                          style={{ height: `${expensesHeight}%` }}
                          title={`Costi ${formatMonthLabel(item.month)}: ${formatEuro(
                            expenses
                          )}`}
                        ></div>
                      </div>
                      <div className={`bar-month ${isActive ? "active-month" : ""}`}>
                        {formatMonthShort(item.month)}
                      </div>
                    </div>
                  );
                })
              ) : (
                <EmptyState message="Trend non disponibile." />
              )}
            </div>

            {safeTrend.length ? (
              <div className="chart-legend">
                <div className="legend-item">
                  <div className="legend-dot legend-ricavi"></div> Ricavi
                </div>
                <div className="legend-item">
                  <div className="legend-dot legend-costi"></div> Costi
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="card">
          <div className="card-title">Prodotti top</div>
          <div className="card-sub">{formatMonthLabel(month)} · per quantità</div>

          <div className="product-list">
            {safeTopProducts.length ? (
              safeTopProducts.slice(0, 5).map((product, i) => {
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
          <div className="card-title">Spese per categoria</div>
          <div className="card-sub">Totale costi {formatMonthLabel(month)}</div>

          {donutData.length ? (
            <div className="premium-donut-section">
              <div className="premium-donut-chart-wrap">
                <div className="premium-donut-chart">
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie
                        data={donutData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={62}
                        outerRadius={110}
                        paddingAngle={0}
                        stroke="none"
                      >
                        {donutData.map((entry, index) => (
                          <Cell
                            key={`${entry.name}-${index}`}
                            fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value, name) => [formatEuro(value), name]}
                      />
                    </PieChart>
                  </ResponsiveContainer>

                  <div className="premium-donut-center">
                    <div className="premium-donut-total">
                      {formatEuro(donutTotal)}
                    </div>
                    <div className="premium-donut-total-label">totale</div>
                  </div>
                </div>
              </div>

              <div className="premium-donut-legend">
                {donutData.map((item, index) => {
                  const pct =
                    donutTotal > 0 ? Math.round((item.value / donutTotal) * 100) : 0;

                  return (
                    <div className="premium-donut-row" key={item.name}>
                      <div className="premium-donut-left">
                        <span
                          className="premium-donut-dot"
                          style={{
                            backgroundColor:
                              CATEGORY_COLORS[index % CATEGORY_COLORS.length],
                          }}
                        />
                        <span className="premium-donut-name">{item.name}</span>
                      </div>

                      <div className="premium-donut-right">
                        <span className="premium-donut-value">
                          {formatEuro(item.value)}
                        </span>
                        <span className="premium-donut-pct">{pct}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <EmptyState message="Nessuna spesa registrata per questo periodo." />
          )}
        </div>
      </div>

      <div className="bottom-grid">
        <div className="card">
          <div className="card-title">Fornitori principali</div>
          <div className="card-sub">Per spesa · {formatMonthLabel(month)}</div>

          <div className="supplier-list">
            {safeSupplierItems.length ? (
              safeSupplierItems.slice(0, 4).map((supplier, index) => {
                const icons = ["☕", "🥛", "🥐", "🍹"];
                const bgs = ["#fff5e8", "#f0f8f4", "#fff8f0", "#f5f0ff"];

                return (
                  <div
                    className="supplier-item"
                    key={`${supplier.counterparty || supplier.supplier}-${index}`}
                  >
                    <div
                      className="supplier-avatar"
                      style={{ background: bgs[index % bgs.length] }}
                    >
                      {icons[index % icons.length]}
                    </div>

                    <div>
                      <div className="supplier-name">
                        {supplier.counterparty || supplier.supplier || "N/D"}
                      </div>
                      <div className="supplier-cat">Fornitore del mese</div>
                    </div>

                    <div className="supplier-amount">
                      <div className="supplier-total">
                        {formatEuro(
                          Math.abs(
                            Number(
                              supplier.total_amount ?? supplier.expenses ?? 0
                            )
                          )
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
            {safeRecentInvoices.length ? (
              safeRecentInvoices.slice(0, 4).map((invoice) => {
                const status =
                  invoice.status === "paid"
                    ? "paid"
                    : invoice.due_date && new Date(invoice.due_date) < new Date()
                    ? "overdue"
                    : "due";

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
        </div>
      </div>

      <div className="card">
        <div className="card-title">Insight automatici</div>
        <div className="card-sub">Suggerimenti e segnali per il mese selezionato</div>

        {safeInsightItems.length ? (
          <ul className="insights-list">
            {safeInsightItems.map((insight) => (
              <li key={insight}>{insight}</li>
            ))}
          </ul>
        ) : (
          <EmptyState message="Nessun insight disponibile per questo periodo." />
        )}
      </div>
    </main>
  );
}

export default function App() {
  const [month, setMonth] = useState(getCurrentMonth());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [overview, setOverview] = useState({ pnl_summary: { revenue: 0, expenses: 0, profit: 0 } });
  const [invoices, setInvoices] = useState([]);
  const [trend, setTrend] = useState([]);
  const [topProducts, setTopProducts] = useState({ by_quantity: [] });
  const [expensesByCategory, setExpensesByCategory] = useState({ items: [] });
  const [expensesBySupplier, setExpensesBySupplier] = useState({ items: [] });
  const [insights, setInsights] = useState({ insights: [] });
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [invoiceUploadMessage, setInvoiceUploadMessage] = useState("");
  const [invoiceUploadError, setInvoiceUploadError] = useState("");
  const [invoiceUploading, setInvoiceUploading] = useState(false);

async function handleInvoiceDocumentUpload(file) {
  if (!file) return;

  try {
    setInvoiceUploading(true);
    setInvoiceUploadError("");
    setInvoiceUploadMessage("");

    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/invoices/extract", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(errorBody || `Upload fattura fallito (${response.status})`);
    }

    const result = await response.json();

    const extractedMonth = result.issue_date?.slice(0, 7) || month;

    setInvoiceUploadMessage(
      `Fattura acquisita: ${result.supplier || "fornitore rilevato"} · ${
        result.invoice_number || "numero non disponibile"
      }`
    );

    if (result.issue_date) {
      setMonth(extractedMonth);
    }

    await loadDashboardData(extractedMonth);
  } catch (err) {
    console.error(err);
    setInvoiceUploadError(
      "Errore durante il caricamento della fattura o nell'estrazione dati."
    );
  } finally {
    setInvoiceUploading(false);
  }
}

  async function loadDashboardData(selectedMonth) {
    const [
      overviewData,
      invoicesData,
      trendData,
      topProductsData,
      expensesByCategoryData,
      expensesBySupplierData,
      insightsData,
    ] = await Promise.all([
      fetchJsonOrThrow(`/api/analytics/overview?month=${selectedMonth}`),
      fetchJsonOrThrow("/api/invoices"),
      fetchJsonOrThrow(`/api/analytics/pnl/trend?months=6`),
      fetchJsonOrThrow(`/api/analytics/top-products?month=${selectedMonth}`),
      fetchJsonOrThrow(`/api/analytics/expenses-by-category?month=${selectedMonth}`),
      fetchJsonOrThrow(`/api/analytics/expenses-by-supplier?month=${selectedMonth}`),
      fetchJsonOrThrow(`/api/analytics/insights?month=${selectedMonth}`),
    ]);

    setOverview(
      overviewData ?? {
        pnl_summary: { revenue: 0, expenses: 0, profit: 0 },
      }
    );
    setInvoices(safeArray(invoicesData));
    setTrend(safeArray(trendData));
    setTopProducts(topProductsData ?? { by_quantity: [] });
    setExpensesByCategory(
      expensesByCategoryData?.items
        ? expensesByCategoryData
        : { items: safeArray(expensesByCategoryData?.top_expense_categories) }
    );
    setExpensesBySupplier(
      expensesBySupplierData?.items
        ? expensesBySupplierData
        : { items: safeArray(expensesBySupplierData?.top_suppliers) }
    );
    setInsights(insightsData ?? { insights: [] });
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError("");
        await loadDashboardData(month);
      } catch {
        if (!cancelled) {
          setError("Impossibile caricare i dati.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [month]);

  async function handleUpload(file, type) {
    if (!file) return;

    try {
      setUploading(true);
      setUploadError("");
      setUploadMessage("");

      const formData = new FormData();
      formData.append("file", file);

      const endpoint =
        type === "pos" ? "/api/imports/pos-csv" : "/api/imports/bank-csv";

      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(errorBody || `Upload fallito (${response.status})`);
      }

      const result = await response.json();
      setUploadMessage(
        `Import ${type.toUpperCase()} completato: ${result.imported_rows ?? 0} righe importate.`
      );

      await loadDashboardData(month);
    } catch (err) {
      console.error(err);
      setUploadError("Errore durante l'import del file.");
    } finally {
      setUploading(false);
    }
  }

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

  const pnl = overview?.pnl_summary ?? { revenue: 0, expenses: 0, profit: 0 };
  const topProductsList = safeArray(topProducts.by_quantity).slice(0, 5);
  const categoryItems = safeArray(expensesByCategory.items).slice(0, 5);
  const supplierItems = safeArray(expensesBySupplier.items).slice(0, 4);
  const recentInvoices = safeArray(invoices).slice(0, 4);
  const insightItems = safeArray(insights.insights);

  const previousTrend = trend.length >= 2 ? trend[trend.length - 2] : null;
  const currentTrend = trend.length >= 1 ? trend[trend.length - 1] : null;

  const profitChange =
    previousTrend && Number(previousTrend.profit) !== 0
      ? (((Number(currentTrend?.profit) || 0) - Number(previousTrend.profit)) /
          Math.abs(Number(previousTrend.profit))) *
        100
      : null;

  const currentMonthInvoices = invoices.filter(
    (invoice) => invoice.issue_date?.slice(0, 7) === month
  );

  const latestInvoiceDate = currentMonthInvoices.length
    ? currentMonthInvoices.map((invoice) => invoice.issue_date).sort().at(-1)
    : null;

  const latestBankUploadDate = expensesBySupplier.items?.length ? `${month}-01` : null;
  const latestPosUploadDate = topProducts.by_quantity?.length ? `${month}-01` : null;

  return (
    <BrowserRouter>
      <div className="dashboard-shell">
        <Sidebar
          month={month}
          setMonth={setMonth}
          pendingInvoices={pendingInvoices.length}
        />

        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          <Route
            path="/dashboard"
            element={
              <DashboardPageContent
                month={month}
                loading={loading}
                error={error}
                pnl={pnl}
                pendingInvoices={pendingInvoices}
                pendingInvoicesAmount={pendingInvoicesAmount}
                trend={trend}
                topProductsList={topProductsList}
                categoryItems={categoryItems}
                supplierItems={supplierItems}
                recentInvoices={recentInvoices}
                insightItems={insightItems}
                profitChange={profitChange}
              />
            }
          />
          <Route
            path="/invoices"
            element={
              <InvoicesPage
                month={month}
                setMonth={setMonth}
                invoices={invoices}
                invoiceUploadMessage={invoiceUploadMessage}
                invoiceUploadError={invoiceUploadError}
                invoiceUploading={invoiceUploading}
                handleInvoiceDocumentUpload={handleInvoiceDocumentUpload}
              />
            }
          />
          <Route
            path="/upload"
            element={
              <UploadPage
                month={month}
                handleUpload={handleUpload}
                uploading={uploading}
                uploadMessage={uploadMessage}
                uploadError={uploadError}
                latestPosUploadDate={latestPosUploadDate}
                latestBankUploadDate={latestBankUploadDate}
                invoiceCountThisMonth={currentMonthInvoices.length}
                latestInvoiceDate={latestInvoiceDate}
              />
            }
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}