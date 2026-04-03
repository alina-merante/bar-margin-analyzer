import { useEffect, useState } from "react";
import "./App.css";

function formatEuro(v) {
  return `${Number(v).toFixed(2)} €`;
}

function App() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(`/api/analytics/overview?month=2026-10`)
      .then((r) => r.json())
      .then(setData);
  }, []);

  if (!data) return <p style={{ padding: 20 }}>Caricamento...</p>;

  const profitto = data.pnl_summary.profit;

  return (
    <div style={{ padding: 30 }}>
      <h1>Bar Margin Analyzer</h1>

      <h2>📊 Panoramica</h2>
      <div style={{ display: "flex", gap: 20 }}>
        <div>💰 Ricavi: {formatEuro(data.pnl_summary.revenue)}</div>
        <div>💸 Costi: {formatEuro(data.pnl_summary.expenses)}</div>
        <div>
          📈 Profitto:{" "}
          <span style={{ color: profitto >= 0 ? "green" : "red" }}>
            {formatEuro(profitto)}
          </span>
        </div>
      </div>

      <h2>☕ Prodotti più venduti</h2>
      <ul>
        {data.top_products_by_quantity.map((p) => (
          <li key={p.product}>
            {p.product} — {p.quantity} unità ({formatEuro(p.revenue)})
          </li>
        ))}
      </ul>

      <h2>📦 Spese per categoria</h2>
      <ul>
        {data.top_expense_categories.map((c) => (
          <li key={c.category}>
            {c.category} — {formatEuro(c.expenses)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;
