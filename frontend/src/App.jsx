import { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`/api/analytics/overview?month=2026-10`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json();
      })
      .then(setData)
      .catch((err) => {
        console.error(err);
        setError(err.message);
      });
  }, []);

  if (error) return <p>Errore: {error}</p>;
  if (!data) return <p>Loading...</p>;

  return (
    <div style={{ padding: 20 }}>
      <h1>Bar Margin Analyzer Dashboard</h1>

      <h2>Profit & Loss</h2>
      <p>Revenue: {data.pnl_summary.revenue}</p>
      <p>Expenses: {data.pnl_summary.expenses}</p>
      <p>Profit: {data.pnl_summary.profit}</p>

      <h2>Top Products</h2>
      <ul>
        {data.top_products_by_quantity.map((p, i) => (
          <li key={i}>
            {p.product} - {p.quantity} sold
          </li>
        ))}
      </ul>

      <h2>Top Expenses</h2>
      <ul>
        {data.top_expense_categories.map((c, i) => (
          <li key={i}>
            {c.category} - {c.expenses}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;