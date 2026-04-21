import { NavLink } from "react-router-dom";

function formatMonthLabel(month) {
  if (!month) return "-";
  const [year, monthNum] = month.split("-").map(Number);
  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, monthNum - 1, 1));
}

export default function Sidebar({ month, setMonth, pendingInvoices = 0 }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">☕</div>
        <div className="logo-text">BarManager</div>
        <div className="logo-sub">Gestione margini</div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-label">Principale</div>

        <NavLink
          to="/dashboard"
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <span className="nav-icon">📊</span>
          Dashboard
        </NavLink>

        <NavLink
          to="/invoices"
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <span className="nav-icon">🧾</span>
          Fatture
          <span className="nav-badge">{pendingInvoices}</span>
        </NavLink>

        <a className="nav-item" href="#">
          <span className="nav-icon">📦</span>
          Fornitori
        </a>

        <a className="nav-item" href="#">
          <span className="nav-icon">🥐</span>
          Prodotti
        </a>

        <div className="nav-label">Documenti</div>

        <NavLink
          to="/upload"
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <span className="nav-icon">⬆️</span>
          Carica file
        </NavLink>

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
          <button
            type="button"
            className="month-nav-btn"
            onClick={() => {
              const [year, monthNum] = month.split("-").map(Number);
              const prev = new Date(year, monthNum - 2, 1);
              const prevMonth = `${prev.getFullYear()}-${String(
                prev.getMonth() + 1
              ).padStart(2, "0")}`;
              setMonth(prevMonth);
            }}
          >
            ◀
          </button>

          <span className="month-label">{formatMonthLabel(month)}</span>

          <button
            type="button"
            className="month-nav-btn"
            onClick={() => {
              const [year, monthNum] = month.split("-").map(Number);
              const next = new Date(year, monthNum, 1);
              const nextMonth = `${next.getFullYear()}-${String(
                next.getMonth() + 1
              ).padStart(2, "0")}`;
              setMonth(nextMonth);
            }}
          >
            ▶
          </button>
        </div>
      </div>
    </aside>
  );
}