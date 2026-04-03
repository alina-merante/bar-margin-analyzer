import { useEffect, useState } from "react";
import "./App.css";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

function formatEuro(v) {
  if (v === null || v === undefined) return "-";
  return `${Number(v).toFixed(2)} €`;
}

function CardMetrica({ titolo, valore, variante = "neutra" }) {
  return (
    <div className={`card-metrica ${variante}`}>
      <div className="card-metrica-titolo">{titolo}</div>
      <div className="card-metrica-valore">{valore}</div>
    </div>
  );
}

function CardSezione({ titolo, children, extra }) {
  return (
    <section className="card-sezione">
      <div className="card-sezione-header">
        <h3>{titolo}</h3>
        {extra}
      </div>
      {children}
    </section>
  );
}

function BadgeStato({ stato }) {
  const paid = stato === "paid";
  return (
    <span className={`badge ${paid ? "verde" : "giallo"}`}>
      {paid ? "Pagata" : "Da pagare"}
    </span>
  );
}

function TooltipGrafico({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;

  return (
    <div className="tooltip-grafico">
      <strong>{label}</strong>
      <div>Ricavi: {formatEuro(payload[0]?.value)}</div>
      <div>Costi: {formatEuro(payload[1]?.value)}</div>
      <div>Profitto: {formatEuro(payload[2]?.value)}</div>
    </div>
  );
}

function App() {
  const [mese, setMese] = useState("2026-10");
  const [overview, setOverview] = useState(null);
  const [insights, setInsights] = useState(null);
  const [fatture, setFatture] = useState([]);
  const [trend, setTrend] = useState([]);
  const [errore, setErrore] = useState("");
  const [caricamento, setCaricamento] = useState(true);

  useEffect(() => {
    async function carica() {
      try {
        setCaricamento(true);
        setErrore("");

        const [overviewRes, insightsRes, fattureRes, trendRes] = await Promise.all([
          fetch(`/api/analytics/overview?month=${mese}`),
          fetch(`/api/analytics/insights?month=${mese}`),
          fetch(`/api/invoices`),
          fetch(`/api/analytics/pnl/trend?months=6`),
        ]);

        if (!overviewRes.ok) throw new Error(`Overview HTTP ${overviewRes.status}`);
        if (!insightsRes.ok) throw new Error(`Insights HTTP ${insightsRes.status}`);
        if (!fattureRes.ok) throw new Error(`Fatture HTTP ${fattureRes.status}`);
        if (!trendRes.ok) throw new Error(`Trend HTTP ${trendRes.status}`);

        const overviewData = await overviewRes.json();
        const insightsData = await insightsRes.json();
        const fattureData = await fattureRes.json();
        const trendData = await trendRes.json();

        setOverview(overviewData);
        setInsights(insightsData);
        setFatture(fattureData);
        setTrend(trendData);
      } catch (e) {
        console.error(e);
        setErrore("Impossibile caricare i dati della dashboard.");
      } finally {
        setCaricamento(false);
      }
    }

    carica();
  }, [mese]);

  if (caricamento) {
    return <div className="stato-pagina">Caricamento dashboard...</div>;
  }

  if (errore) {
    return <div className="stato-pagina errore">{errore}</div>;
  }

  const profitto = overview?.pnl_summary?.profit ?? 0;
  const profittoVariante = profitto >= 0 ? "positivo" : "negativo";

  const fattureDaPagare = fatture.filter((f) => f.status !== "paid");
  const importoDaPagare = fattureDaPagare.reduce(
    (acc, item) => acc + Number(item.total || 0),
    0
  );

  return (
    <div className="layout">
      <aside className="sidebar">
        <div>
          <div className="brand">Bar Margin</div>
          <h1>Dashboard</h1>
          <p className="sidebar-sottotitolo">
            Analisi economica semplice e chiara
          </p>
        </div>

        <nav className="menu">
          <a className="menu-item attivo">Panoramica</a>
          <a className="menu-item">Prodotti</a>
          <a className="menu-item">Fornitori</a>
          <a className="menu-item">Fatture</a>
          <a className="menu-item">Insight</a>
          <a className="menu-item">Report</a>
        </nav>

        <div className="sidebar-box">
          <label>Seleziona mese</label>
          <input
            type="month"
            value={mese}
            onChange={(e) => setMese(e.target.value)}
          />
        </div>

        <div className="sidebar-info">
          <p>Ultimo aggiornamento</p>
          <strong>{mese}</strong>
        </div>
      </aside>

      <main className="contenuto">
        <header className="header">
          <div>
            <p className="eyebrow">Dashboard gestionale</p>
            <h2>Panoramica economica del bar</h2>
            <p className="header-text">
              Controlla ricavi, costi, margine, andamento mensile e fatture.
            </p>
          </div>

          <div className="azioni-header">
            <button className="bottone secondario">Esporta report</button>
            <button className="bottone primario">Carica documento</button>
          </div>
        </header>

        <section className="griglia-metriche">
          <CardMetrica
            titolo="Ricavi del mese"
            valore={formatEuro(overview.pnl_summary.revenue)}
            variante="ricavi"
          />
          <CardMetrica
            titolo="Costi del mese"
            valore={formatEuro(overview.pnl_summary.expenses)}
            variante="costi"
          />
          <CardMetrica
            titolo="Profitto del mese"
            valore={formatEuro(profitto)}
            variante={profittoVariante}
          />
          <CardMetrica
            titolo="Fatture da pagare"
            valore={formatEuro(importoDaPagare)}
            variante="neutra"
          />
        </section>

        <section className="griglia-principale grande">
          <CardSezione titolo="Andamento ricavi, costi e profitto" extra={<span className="badge neutro">Ultimi 6 mesi</span>}>
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trend}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis />
                  <Tooltip content={<TooltipGrafico />} />
                  <Legend />
                  <Line type="monotone" dataKey="revenue" name="Ricavi" stroke="#16a34a" strokeWidth={3} />
                  <Line type="monotone" dataKey="expenses" name="Costi" stroke="#f59e0b" strokeWidth={3} />
                  <Line type="monotone" dataKey="profit" name="Profitto" stroke="#2563eb" strokeWidth={3} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardSezione>

          <CardSezione titolo="Prodotti più venduti">
            <ul className="lista-dati">
              {overview.top_products_by_quantity.map((item) => (
                <li key={item.product}>
                  <div>
                    <strong>{item.product}</strong>
                    <span>Quantità venduta: {item.quantity} unità</span>
                  </div>
                  <div className="valore-destra">{formatEuro(item.revenue)}</div>
                </li>
              ))}
            </ul>
          </CardSezione>
        </section>

        <section className="griglia-principale">
          <CardSezione titolo="Fornitori principali">
            <ul className="lista-dati">
              {overview.top_suppliers.map((item) => (
                <li key={item.supplier}>
                  <div>
                    <strong>{item.supplier}</strong>
                    <span>Costo sostenuto nel mese</span>
                  </div>
                  <div className="valore-destra">{formatEuro(item.expenses)}</div>
                </li>
              ))}
            </ul>
          </CardSezione>

          <CardSezione titolo="Insight automatici">
            <ul className="lista-insight">
              {insights?.insights?.length ? (
                insights.insights.map((item, index) => (
                  <li key={index}>{item}</li>
                ))
              ) : (
                <li>Nessun insight disponibile.</li>
              )}
            </ul>
          </CardSezione>
        </section>

        <section className="griglia-principale">
          <CardSezione titolo="Categorie di spesa principali">
            <ul className="lista-dati">
              {overview.top_expense_categories.map((item) => (
                <li key={item.category}>
                  <div>
                    <strong>{item.category}</strong>
                    <span>Voce di costo del mese</span>
                  </div>
                  <div className="valore-destra">{formatEuro(item.expenses)}</div>
                </li>
              ))}
            </ul>
          </CardSezione>

          <CardSezione titolo="Fatture recenti">
            {fatture.length === 0 ? (
              <p>Nessuna fattura presente.</p>
            ) : (
              <table className="tabella">
                <thead>
                  <tr>
                    <th>Fornitore</th>
                    <th>Numero</th>
                    <th>Scadenza</th>
                    <th>Importo</th>
                    <th>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {fatture.slice(0, 5).map((fattura) => (
                    <tr key={fattura.id}>
                      <td>{fattura.supplier}</td>
                      <td>{fattura.invoice_number}</td>
                      <td>{fattura.due_date}</td>
                      <td>{formatEuro(fattura.total)}</td>
                      <td>
                        <BadgeStato stato={fattura.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardSezione>
        </section>
      </main>
    </div>
  );
}

export default App;