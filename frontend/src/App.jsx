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

function formatEuro(value) {
  return CURRENCY.format(Number(value) || 0);
}

function formatMonthLabel(month) {
  if (!month) return "-";
  const [year, monthNum] = month.split("-").map(Number);
  return MONTH_LABEL.format(new Date(year, monthNum - 1, 1));
}

function getCurrentMonth() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function DashboardError({ message }) {
  return <p className="state-message state-error">{message}</p>;
}

function DashboardLoading() {
  return <p className="state-message">Caricamento dashboard in corso...</p>;
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

function App() {
  const month = useMemo(() => getCurrentMonth(), []);
  const [state, setState] = useState({
    loading: true,
    error: "",
    data: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      setState({ loading: true, error: "", data: null });

      try {
        const [
          overviewRes,
          invoicesRes,
          trendRes,
          topProductsRes,
          expensesByCategoryRes,
          expensesBySupplierRes,
          insightsRes,
        ] = await Promise.all([
          fetch(`/api/analytics/overview?month=${month}`),
          fetch("/api/invoices"),
          fetch("/api/analytics/pnl/trend?months=6"),
          fetch(`/api/analytics/top-products?month=${month}`),
          fetch(`/api/analytics/expenses-by-category?month=${month}`),
          fetch(`/api/analytics/expenses-by-supplier?month=${month}`),
          fetch(`/api/analytics/insights?month=${month}`),
        ]);

        const responses = [
          overviewRes,
          invoicesRes,
          trendRes,
          topProductsRes,
          expensesByCategoryRes,
          expensesBySupplierRes,
          insightsRes,
        ];

        const failedResponse = responses.find((r) => !r.ok);
        if (failedResponse) {
          throw new Error(`Errore API (${failedResponse.status})`);
        }

        const [overview, invoices, trend, topProducts, expensesByCategory, expensesBySupplier, insights] =
          await Promise.all(responses.map((r) => r.json()));

        if (cancelled) {
          return;
        }

        setState({
          loading: false,
          error: "",
          data: {
            overview,
            invoices,
            trend,
            topProducts,
            expensesByCategory,
            expensesBySupplier,
            insights,
          },
        });
      } catch {
        if (cancelled) {
          return;
        }

        setState({
          loading: false,
          error: "Impossibile caricare i dati. Riprova tra qualche istante.",
          data: null,
        });
      }
    }

    loadDashboard();

    return () => {
      cancelled = true;
    };
  }, [month]);

  if (state.loading) {
    return <DashboardLoading />;
  }

  if (state.error || !state.data) {
    return <DashboardError message={state.error} />;
  }

  const { overview, invoices, trend, topProducts, expensesByCategory, expensesBySupplier, insights } = state.data;

  const pendingInvoices = invoices.filter((invoice) => invoice.status === "pending");
  const pendingInvoicesAmount = pendingInvoices.reduce((sum, invoice) => sum + invoice.total, 0);

  const chartBars = trend.length > 0 ? trend : [];
  const maxChartValue = Math.max(...chartBars.map((item) => item.revenue), 1);

  const recentInvoices = invoices.slice(0, 5);

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Dashboard finanziaria</h1>
          <p className="small-muted">Periodo: {formatMonthLabel(month)}</p>
        </div>
      </header>

      <section className="kpi-grid">
        <KpiCard
          title="Margine netto"
          value={formatEuro(overview.pnl_summary.profit)}
          negative={overview.pnl_summary.profit < 0}
        />
        <KpiCard title="Ricavi totali" value={formatEuro(overview.pnl_summary.revenue)} />
        <KpiCard title="Costi totali" value={formatEuro(overview.pnl_summary.expenses)} />
        <KpiCard
          title="Fatture da pagare"
          value={formatEuro(pendingInvoicesAmount)}
          subtitle={`${pendingInvoices.length} in sospeso`}
        />
      </section>

      <section className="card">
        <h2>Trend ultimi 6 mesi</h2>
        <div className="trend-chart">
          {chartBars.map((item) => (
            <div key={item.month} className="bar-group">
              <div className="bar-track" title={`Ricavi ${item.month}: ${formatEuro(item.revenue)}`}>
                <div
                  className="bar-fill"
                  style={{ height: `${Math.max(8, (item.revenue / maxChartValue) * 100)}%` }}
                />
              </div>
              <p className="bar-label">{item.month.slice(5)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="grid-two-columns">
        <article className="card">
          <h2>Prodotti più venduti</h2>
          <ul className="list">
            {topProducts.by_quantity.slice(0, 5).map((product) => (
              <li key={product.product}>
                <span>{product.product}</span>
                <span>{product.quantity.toFixed(0)} unità</span>
              </li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h2>Categorie di spesa</h2>
          <ul className="list">
            {expensesByCategory.items.slice(0, 5).map((category) => (
              <li key={category.category}>
                <span>{category.category}</span>
                <span>{formatEuro(Math.abs(category.total_amount))}</span>
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="grid-two-columns">
        <article className="card">
          <h2>Top fornitori</h2>
          <ul className="list">
            {expensesBySupplier.items.slice(0, 5).map((supplier) => (
              <li key={supplier.counterparty}>
                <span>{supplier.counterparty || "N/D"}</span>
                <span>{formatEuro(Math.abs(supplier.total_amount))}</span>
              </li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h2>Fatture recenti</h2>
          <ul className="list list-invoices">
            {recentInvoices.map((invoice) => (
              <li key={invoice.id}>
                <span>{invoice.supplier}</span>
                <span>{formatEuro(invoice.total)}</span>
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="card">
        <h2>Insight automatici</h2>
        {insights.insights.length > 0 ? (
          <ul className="insights-list">
            {insights.insights.map((insight) => (
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
