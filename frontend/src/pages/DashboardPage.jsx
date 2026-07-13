import { Link } from "react-router-dom";
import { useMemo } from "react";

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
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

function formatShortDate(value) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "long",
  }).format(date);
}

function daysAgoLabel(value) {
  if (!value) return "MANCANTE";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "MANCANTE";

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  date.setHours(0, 0, 0, 0);

  const diffDays = Math.floor((today - date) / (1000 * 60 * 60 * 24));

  if (diffDays <= 0) return "OGGI";
  if (diffDays === 1) return "IERI";

  return `${diffDays} GIORNI FA`;
}

function getReminderTone(value, fallbackTone = "danger") {
  if (!value) return fallbackTone;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallbackTone;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  date.setHours(0, 0, 0, 0);

  const diffDays = Math.floor((today - date) / (1000 * 60 * 60 * 24));

  if (diffDays <= 1) return "neutral";
  if (diffDays <= 3) return "warning";

  return "danger";
}

function isOverdue(invoice) {
  if (invoice.status === "paid") return false;
  if (!invoice.due_date) return false;
  return new Date(invoice.due_date) < new Date();
}

function isDue(invoice) {
  if (invoice.status === "paid") return false;
  if (!invoice.due_date) return true;
  return new Date(invoice.due_date) >= new Date();
}

function productIcon(name = "") {
  const lower = name.toLowerCase();

  if (lower.includes("caff")) return "☕";
  if (lower.includes("cappuccino")) return "🥛";
  if (lower.includes("cornetto") || lower.includes("croissant")) return "🥐";
  if (lower.includes("spritz") || lower.includes("drink")) return "🍹";

  return "🍽️";
}

export default function DashboardPage({
  month,
  loading,
  error,
  onExportPdf,
  pnl = { revenue: 0, expenses: 0, profit: 0 },
  trend = [],
  topProductsList = [],
  pendingInvoices = [],
  pendingInvoicesAmount = 0,
  previousOverdueInvoices = [],
  previousOverdueInvoicesAmount = 0,
  invoices = [],
  latestPosUploadDate = null,
  latestBankUploadDate = null,
}) {
  const monthLabel = formatMonthLabel(month);
  const hasPreviousOverdueInvoices = previousOverdueInvoices.length > 0;

  const currentMonthInvoices = useMemo(() => {
    return invoices.filter((invoice) => invoice.due_date?.slice(0, 7) === month);
  }, [invoices, month]);

  const paidInvoices = currentMonthInvoices.filter((i) => i.status === "paid");
  const overdueInvoices = currentMonthInvoices.filter(isOverdue);
  const dueInvoices = currentMonthInvoices.filter(isDue);
  const overdueInvoicesAmount = overdueInvoices.reduce(
  (sum, invoice) => sum + (Number(invoice.total) || 0),
  0
);

  const criticalInvoices = [...overdueInvoices, ...dueInvoices].slice(0, 3);

  const marginPercent =
    Number(pnl.revenue) > 0
      ? Math.max(0, (Number(pnl.profit) / Number(pnl.revenue)) * 100)
      : 0;

  const trendMax = Math.max(
    ...trend.flatMap((item) => [
      Number(item.revenue) || 0,
      Number(item.expenses) || 0,
    ]),
    1
  );

  const maxProductQty = Math.max(
    ...topProductsList.map((p) => Number(p.quantity) || 0),
    1
  );

  const todayLabel = new Intl.DateTimeFormat("it-IT", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());

  const firstDueInvoice = dueInvoices[0];

  const reminders = [
    {
      icon: "🖨️",
      badge: daysAgoLabel(latestPosUploadDate),
      title: "Cassa",
      text: latestPosUploadDate
        ? `Ultimo export caricato il ${formatShortDate(latestPosUploadDate)}`
        : "Export POS non ancora caricato",
      action: latestPosUploadDate ? "Aggiorna" : "Carica ora",
      to: "/upload",
      tone: getReminderTone(latestPosUploadDate, "danger"),
    },
    {
      icon: "🏦",
      badge: daysAgoLabel(latestBankUploadDate),
      title: "Movimenti bancari",
      text: latestBankUploadDate
        ? `Ultimo aggiornamento il ${formatShortDate(latestBankUploadDate)}`
        : "Movimenti bancari non ancora caricati",
      action: latestBankUploadDate ? "Aggiorna" : "Carica ora",
      to: "/upload",
      tone: getReminderTone(latestBankUploadDate, "warning"),
    },
    {
  icon: "🧾",
  badge: overdueInvoices.length ? "SCADUTA" : "OK",
  title: "Fatture scadute",
  text: overdueInvoices.length
    ? `${overdueInvoices.length} ${
        overdueInvoices.length === 1
          ? "fattura scaduta"
          : "fatture scadute"
      } · totale ${formatEuro(overdueInvoicesAmount)}`
    : "Nessuna fattura scaduta.",
  action: overdueInvoices.length ? "Paga ora" : "Vedi dettagli",
  to: "/invoices",
  tone: overdueInvoices.length ? "danger" : "neutral",
},
    {
      icon: "⏰",
      badge: firstDueInvoice ? "TRA POCO" : "OK",
      title: firstDueInvoice?.supplier || "Prossime scadenze",
      text: firstDueInvoice
        ? `${formatEuro(firstDueInvoice.total)} · scade il ${formatShortDate(
            firstDueInvoice.due_date
          )}`
        : "Nessuna scadenza aperta.",
      action: "Vedi dettagli",
      to: "/invoices",
      tone: firstDueInvoice ? "warning" : "neutral",
    },
  ];

  if (loading) {
    return (
      <main className="main">
        <div className="card">
          <div className="card-title">Caricamento dashboard</div>
          <div className="card-sub">Sto recuperando i dati del mese selezionato.</div>
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
    <main className="main dashboard-page">
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Business Overview</h1>
          <p className="dashboard-subtitle">
            Panoramica {monthLabel}
          </p>
        </div>

        <div className="dashboard-actions">
          <button
            type="button"
            className="dashboard-export-btn"
            onClick={onExportPdf}
            disabled={!onExportPdf}
          >
            📄 Export PDF
          </button>

          <Link to="/upload" className="dashboard-upload-btn">
            ⬆️ Carica documento
          </Link>
        </div>
      </div>

      {hasPreviousOverdueInvoices ? (
  <div className="previous-overdue-alert">
    <div className="previous-overdue-icon">⚠️</div>

    <div>
      <strong>
        Hai {previousOverdueInvoices.length} fatture da pagare.
      </strong>
      <p>
        Totale arretrato: {formatEuro(previousOverdueInvoicesAmount)}. Controlla
        le scadenze delle fatture scadute di quest'anno nella sezione Fatture.
      </p>
    </div>

    <Link to="/invoices?tab=year-overdue" className="previous-overdue-link">
  Vai alle fatture →
</Link>
  </div>
) : null}

      <section className="dashboard-kpi-grid">
        <article className="dashboard-kpi-card dark">
          <div className="kpi-label">Margine netto</div>
          <div className="kpi-value">{formatEuro(pnl.profit)}</div>

          <div className="margin-meter">
            <div className="margin-bar-wrap">
              <div
                className="margin-bar-fill"
                style={{ width: `${Math.min(100, Math.max(8, marginPercent))}%` }}
              />
            </div>

            <div className="margin-labels">
              <span>0%</span>
              <span className="margin-highlight">{marginPercent.toFixed(0)}%</span>
              <span>100%</span>
            </div>
          </div>
        </article>

        <article className="dashboard-kpi-card">
          <div className="kpi-label">Ricavi totali</div>
          <div className="kpi-value">{formatEuro(pnl.revenue)}</div>
          <span className="kpi-pill green">↑ Ricavi registrati</span>
        </article>

        <article className="dashboard-kpi-card">
          <div className="kpi-label">Costi totali</div>
          <div className="kpi-value">{formatEuro(pnl.expenses)}</div>
          <span className="kpi-pill red">↑ Spese registrate</span>
        </article>

        <article className="dashboard-kpi-card">
          <div className="kpi-label">Da pagare</div>
          <div className="kpi-value">{formatEuro(pendingInvoicesAmount)}</div>
          <span className="kpi-pill yellow">⚠ {pendingInvoices.length} in sospeso</span>
        </article>
      </section>

      <section className="dashboard-content-grid">
        <article className="card dashboard-chart-card">
          <div className="card-title">Ricavi vs Costi</div>
          <div className="card-sub">Ultimi 6 mesi</div>

          <div className="chart-bars dashboard-chart-bars">
            {trend.map((item) => {
              const revenue = Number(item.revenue) || 0;
              const expenses = Number(item.expenses) || 0;
              const active = item.month === month;

              return (
                <div className="bar-group" key={item.month}>
                  <div className="bar-pair">
                    <div
                      className={`bar ricavi ${active ? "active-bar" : ""} ${
    revenue === 0 ? "zero-bar" : ""
  }`}
  style={{
    height: revenue > 0 ? `${Math.max(8, (revenue / trendMax) * 100)}%` : "4px",
  }}
       />
                    <div
                      className={`bar costi ${active ? "active-cost-bar" : ""} ${
    expenses === 0 ? "zero-bar" : ""
  }`}
  style={{
    height: expenses > 0 ? `${Math.max(8, (expenses / trendMax) * 100)}%` : "4px",
  }}                    />
                  </div>

                  <div className={`bar-month ${active ? "active-month" : ""}`}>
                    {formatMonthShort(item.month)}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="chart-legend">
            <div className="legend-item">
              <span className="legend-dot legend-ricavi" /> Ricavi
            </div>
            <div className="legend-item">
              <span className="legend-dot legend-costi" /> Costi
            </div>
          </div>
        </article>

        <div className="dashboard-right-column">
          <article className="card">
            <div className="card-title">Prodotti top</div>
            <div className="card-sub">Per quantità venduta · {monthLabel}</div>

            <div className="product-list">
              {topProductsList.slice(0, 3).map((product, index) => {
                const qty = Number(product.quantity) || 0;
                const width = (qty / maxProductQty) * 100;

                return (
                  <div className="product-item" key={product.product || index}>
                    <div className="product-rank">{index + 1}</div>

                    <div className="product-info">
                      <div className="product-name">
                        <span>{productIcon(product.product)}</span> {product.product}
                      </div>

                      <div className="product-bar-wrap">
                        <div
                          className="product-bar-fill"
                          style={{ width: `${Math.max(12, width)}%` }}
                        />
                      </div>
                    </div>

                    <div className="product-stat">
                      <div className="product-qty">{qty.toFixed(0)}</div>
                      <div className="product-rev">{formatEuro(product.revenue)}</div>
                    </div>
                  </div>
                );
              })}

              {!topProductsList.length ? (
                <p className="small-muted">Nessun prodotto disponibile.</p>
              ) : null}
            </div>
          </article>

          <article className="card dashboard-invoices-card">
            <div className="invoice-card-head">
              <div>
                <div className="card-title">Fatture</div>
              </div>

              <Link to="/invoices" className="see-all-btn">
                Vedi tutte →
              </Link>
            </div>

            <div className="invoice-mini-stats">
              <div className="invoice-mini-stat paid">
                <strong>{paidInvoices.length}</strong>
                <span>Pagate</span>
              </div>

              <div className="invoice-mini-stat due">
                <strong>{dueInvoices.length}</strong>
                <span>In scadenza</span>
              </div>

              <div className="invoice-mini-stat overdue">
                <strong>{overdueInvoices.length}</strong>
                <span>Scadute</span>
              </div>
            </div>

            <div className="invoice-critical-list">
              {criticalInvoices.length ? (
                criticalInvoices.map((invoice) => {
                  const overdue = isOverdue(invoice);

                  return (
                    <div
                      key={invoice.id}
                      className={`invoice-critical-item ${
                        overdue ? "overdue" : "due"
                      }`}
                    >
                      <div className="invoice-critical-icon">
                        {overdue ? "🧾" : "⏰"}
                      </div>

                      <div className="invoice-critical-info">
                        <strong>{invoice.supplier || "Fornitore"}</strong>
                        <span>
                          {overdue ? "scaduta il" : "scade il"}{" "}
                          {formatShortDate(invoice.due_date)}
                        </span>
                      </div>

                      <div className="invoice-critical-amount">
                        {formatEuro(invoice.total)}
                      </div>
                    </div>
                  );
                })
              ) : (
                <p className="small-muted">Nessuna fattura critica.</p>
              )}
            </div>
          </article>
        </div>
      </section>

      <section className="daily-reminder-card">
        <div className="daily-reminder-head">
          <div className="daily-reminder-icon">☀️</div>

          <div>
            <h2>Promemoria di oggi — {todayLabel}</h2>
            <p>Controlla questi punti prima di iniziare la giornata</p>
          </div>
        </div>

        <div className="daily-reminder-scroll">
          {reminders.map((item) => (
            <Link
              to={item.to}
              className={`daily-reminder-item ${item.tone}`}
              key={item.title}
            >
              <div className="daily-reminder-top">
                <span className="daily-reminder-big-icon">{item.icon}</span>
                <span className="daily-reminder-badge">{item.badge}</span>
              </div>

              <strong>{item.title}</strong>
              <p>{item.text}</p>

              <span className="daily-reminder-action">{item.action} →</span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}