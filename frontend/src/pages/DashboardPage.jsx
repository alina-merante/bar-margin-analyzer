import { useMemo } from "react";

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

export default function DashboardPage({
  month,
  pnl,
  trend,
  topProductsList,
  pendingInvoices,
  pendingInvoicesAmount,
  invoices,
}) {
  // 🔴 FATTURE CRITICHE
  const criticalInvoices = useMemo(() => {
    return invoices.filter((inv) => {
      if (inv.status === "paid") return false;

      if (!inv.due_date) return true;

      return new Date(inv.due_date) < new Date();
    });
  }, [invoices]);

  // 🧠 PROMEMORIA INTELLIGENTI
  const reminders = useMemo(() => {
    const list = [];

    if (!topProductsList.length) {
      list.push("⚠️ Nessun dato vendite per questo mese");
    }

    if (!trend.length) {
      list.push("⚠️ Andamento non disponibile");
    }

    if (pendingInvoices.length > 0) {
      list.push(`🧾 Hai ${pendingInvoices.length} fatture da pagare`);
    }

    const overdue = criticalInvoices.filter(
      (i) => i.due_date && new Date(i.due_date) < new Date()
    );

    if (overdue.length > 0) {
      list.push(`🚨 ${overdue.length} fatture sono scadute`);
    }

    if (!list.length) {
      list.push("✅ Tutto sotto controllo");
    }

    return list;
  }, [pendingInvoices, criticalInvoices, trend, topProductsList]);

  const trendMax = Math.max(
    ...trend.flatMap((t) => [Number(t.revenue) || 0, Number(t.expenses) || 0]),
    1
  );

  return (
    <main className="main">
      {/* HEADER */}
      <div className="header">
        <div>
          <div className="header-title">Buongiorno ☕</div>
          <div className="header-sub">
            {formatMonthLabel(month)} · panoramica operativa
          </div>
        </div>

        <div className="header-actions">
          <button className="btn-outline">📄 Export</button>
        </div>
      </div>

      {/* KPI */}
      <div className="kpi-grid">
        <div className="kpi-card accent">
          <div className="kpi-label">Margine</div>
          <div className="kpi-value">{formatEuro(pnl.profit)}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Ricavi</div>
          <div className="kpi-value">{formatEuro(pnl.revenue)}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Costi</div>
          <div className="kpi-value">{formatEuro(pnl.expenses)}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Da pagare</div>
          <div className="kpi-value">
            {formatEuro(pendingInvoicesAmount)}
          </div>
        </div>
      </div>

      {/* GRID PRINCIPALE */}
      <div className="main-grid">
        {/* GRAFICO */}
        <div className="card">
          <div className="card-title">Ricavi vs Costi</div>
          <div className="chart-area">
            <div className="chart-bars">
              {trend.map((item, i) => {
                const r = Number(item.revenue) || 0;
                const e = Number(item.expenses) || 0;

                return (
                  <div className="bar-group" key={item.month}>
                    <div className="bar-pair">
                      <div
                        className="bar ricavi"
                        style={{ height: `${(r / trendMax) * 100}%` }}
                      />
                      <div
                        className="bar costi"
                        style={{ height: `${(e / trendMax) * 100}%` }}
                      />
                    </div>
                    <div className="bar-month">
                      {formatMonthShort(item.month)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* TOP PRODOTTI */}
        <div className="card">
          <div className="card-title">Prodotti top</div>

          {topProductsList.slice(0, 3).map((p, i) => (
            <div key={i} className="product-item">
              <div className="product-rank">{i + 1}</div>

              <div className="product-info">
                <div className="product-name">{p.product}</div>
              </div>

              <div className="product-stat">
                {p.quantity}
              </div>
            </div>
          ))}
        </div>

        {/* PROMEMORIA */}
        <div className="card">
          <div className="card-title">Promemoria</div>

          <ul className="insights-list">
            {reminders.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* FATTURE CRITICHE */}
      <div className="card">
        <div className="card-title">Fatture da controllare</div>

        {criticalInvoices.length ? (
          criticalInvoices.slice(0, 5).map((inv) => (
            <div key={inv.id} className="invoice-item overdue">
              <div className="invoice-info">
                <div className="invoice-name">{inv.supplier}</div>
                <div className="invoice-date">
                  Scade: {inv.due_date}
                </div>
              </div>

              <div className="invoice-amount">
                {formatEuro(inv.total)}
              </div>
            </div>
          ))
        ) : (
          <p className="small-muted">Nessuna criticità</p>
        )}
      </div>
    </main>
  );
}