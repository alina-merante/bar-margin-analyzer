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

const DASHBOARD_ERROR = "Impossibile caricare i dati. Riprova tra qualche istante.";

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

function normalizeDashboardData(raw = {}) {
  return {
    overview: raw.overview ?? { pnl_summary: { profit: 0, revenue: 0, expenses: 0 } },
    invoices: safeArray(raw.invoices),
    trend: safeArray(raw.trend),
    topProducts: raw.topProducts ?? { by_quantity: [] },
    expensesByCategory: raw.expensesByCategory ?? { items: [] },
    expensesBySupplier: raw.expensesBySupplier ?? { items: [] },
    insights: raw.insights ?? { insights: [] },
  };
}

function useDashboardData(month) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    data: normalizeDashboardData(),
  });

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      setState((prev) => ({ ...prev, loading: true, error: "" }));

      try {
        const [overview, invoices, trend, topProducts, expensesByCategory, expensesBySupplier, insights] =
          await Promise.all([
            fetchJsonOrThrow(`/api/analytics/overview?month=${month}`),
            fetchJsonOrThrow("/api/invoices"),
            fetchJsonOrThrow("/api/analytics/pnl/trend?months=6"),
            fetchJsonOrThrow(`/api/analytics/top-products?month=${month}`),
            fetchJsonOrThrow(`/api/analytics/expenses-by-category?month=${month}`),
            fetchJsonOrThrow(`/api/analytics/expenses-by-supplier?month=${month}`),
            fetchJsonOrThrow(`/api/analytics/insights?month=${month}`),
          ]);

        if (cancelled) return;

        setState({
          loading: false,
          error: "",
          data: normalizeDashboardData({
            overview,
            invoices,
            trend,
            topProducts,
            expensesByCategory,
            expensesBySupplier,
            insights,
          }),
        });
      } catch {
        if (cancelled) return;
        setState({ loading: false, error: DASHBOARD_ERROR, data: normalizeDashboardData() });
      }
    }

    loadDashboard();

    return () => {
      cancelled = true;
    };
  }, [month]);

  return state;
}

function DashboardMessage({ message, error = false }) {
  return <p className={`state-message ${error ? "state-error" : ""}`}>{message}</p>;
}

function KpiCard({ title, value, subtitle, negative = false }) {
  return (
    <article className="card kpi-card">
      <p className="label">{title}</p>
      <p className={`kpi-value ${negative ? "negative" : ""}`}>{value}</p>
      {subtitle ? <p className="small-muted">{subtitle}</p> : null}
    </article>
  );
}

function SectionCard({ title, children }) {
  return (
    <article className="card">
      <h2>{title}</h2>
      {children}
    </article>
  );
}

function EmptyState({ message }) {
  return <p className="small-muted">{message}</p>;
}

function TrendChart({ items }) {
  if (!items.length) {
    return <EmptyState message="Dati trend non disponibili." />;
  }

  const maxChartValue = Math.max(...items.map((item) => Number(item.revenue) || 0), 1);

  return (
    <div className="trend-chart">
      {items.map((item) => {
        const revenue = Number(item.revenue) || 0;
        return (
          <div key={item.month} className="bar-group">
            <div className="bar-track" title={`Ricavi ${item.month}: ${formatEuro(revenue)}`}>
              <div className="bar-fill" style={{ height: `${Math.max(8, (revenue / maxChartValue) * 100)}%` }} />
            </div>
            <p className="bar-label">{formatMonthShort(item.month)}</p>
          </div>
        );
      })}
    </div>
  );
}

function App() {
  const month = useMemo(() => getCurrentMonth(), []);
  const { loading, error, data } = useDashboardData(month);

  const pendingInvoices = data.invoices.filter((invoice) => invoice.status === "pending");
  const pendingInvoicesAmount = pendingInvoices.reduce((sum, invoice) => sum + (Number(invoice.total) || 0), 0);
  const recentInvoices = data.invoices.slice(0, 5);

  if (loading) {
    return <DashboardMessage message="Caricamento dashboard in corso..." />;
  }

  if (error) {
    return <DashboardMessage message={error} error />;
  }

  const profit = Number(data.overview.pnl_summary?.profit) || 0;
  const revenue = Number(data.overview.pnl_summary?.revenue) || 0;
  const expenses = Number(data.overview.pnl_summary?.expenses) || 0;

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Dashboard finanziaria</h1>
          <p className="small-muted">Periodo: {formatMonthLabel(month)}</p>
        </div>
      </header>

      <section className="kpi-grid">
        <KpiCard title="Margine netto" value={formatEuro(profit)} negative={profit < 0} />
        <KpiCard title="Ricavi totali" value={formatEuro(revenue)} />
        <KpiCard title="Costi totali" value={formatEuro(expenses)} />
        <KpiCard
          title="Fatture da pagare"
          value={formatEuro(pendingInvoicesAmount)}
          subtitle={`${pendingInvoices.length} in sospeso`}
        />
      </section>

      <section className="card">
        <h2>Trend ultimi 6 mesi</h2>
        <TrendChart items={data.trend} />
      </section>

      <section className="grid-two-columns">
        <SectionCard title="Prodotti più venduti">
          {data.topProducts.by_quantity.length ? (
            <ul className="list">
              {data.topProducts.by_quantity.slice(0, 5).map((product) => (
                <li key={product.product}>
                  <span>{product.product}</span>
                  <span>{(Number(product.quantity) || 0).toFixed(0)} unità</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="Nessun prodotto disponibile per questo periodo." />
          )}
        </SectionCard>

        <SectionCard title="Categorie di spesa">
          {data.expensesByCategory.items.length ? (
            <ul className="list">
              {data.expensesByCategory.items.slice(0, 5).map((category) => (
                <li key={category.category}>
                  <span>{category.category}</span>
                  <span>{formatEuro(Math.abs(Number(category.total_amount) || 0))}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="Nessuna spesa registrata per questo periodo." />
          )}
        </SectionCard>
      </section>

      <section className="grid-two-columns">
        <SectionCard title="Top fornitori">
          {data.expensesBySupplier.items.length ? (
            <ul className="list">
              {data.expensesBySupplier.items.slice(0, 5).map((supplier) => (
                <li key={`${supplier.counterparty}-${supplier.total_amount}`}>
                  <span>{supplier.counterparty || "N/D"}</span>
                  <span>{formatEuro(Math.abs(Number(supplier.total_amount) || 0))}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="Nessun fornitore disponibile per questo periodo." />
          )}
        </SectionCard>

        <SectionCard title="Fatture recenti">
          {recentInvoices.length ? (
            <ul className="list list-invoices">
              {recentInvoices.map((invoice) => (
                <li key={invoice.id}>
                  <span>{invoice.supplier}</span>
                  <span>{formatEuro(invoice.total)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="Nessuna fattura disponibile." />
          )}
        </SectionCard>
      </section>

      <section className="card">
        <h2>Insight automatici</h2>
        {data.insights.insights.length > 0 ? (
          <ul className="insights-list">
            {data.insights.insights.map((insight) => (
              <li key={insight}>{insight}</li>
            ))}
          </ul>
        ) : (
          <p className="small-muted">Nessun insight disponibile per questo periodo.</p>
        )}
      </section>
    </main>
  );
}

export default App;
