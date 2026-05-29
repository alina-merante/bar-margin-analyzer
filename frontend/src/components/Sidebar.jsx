import { NavLink } from "react-router-dom";

function formatMonthLabel(month) {
  if (!month) return "-";

  const [year, monthNum] = month.split("-").map(Number);

  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, monthNum - 1, 1));
}

function shiftMonth(month, delta) {
  const [year, monthNum] = month.split("-").map(Number);
  const date = new Date(year, monthNum - 1 + delta, 1);

  const nextMonth = String(date.getMonth() + 1).padStart(2, "0");

  return `${date.getFullYear()}-${nextMonth}`;
}

export default function Sidebar({ month, setMonth, pendingInvoices = 0 }) {
  return (
    <aside className="sidebar">
      {/* LOGO */}
      <div className="sidebar-logo">
        <div className="logo-icon">☕</div>
        <div className="logo-text">BarManager</div>
        <div className="logo-sub">Gestione margini</div>
      </div>

      {/* NAV */}
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

          {pendingInvoices > 0 && (
            <span className="nav-badge">{pendingInvoices}</span>
          )}
        </NavLink>

        <div className="nav-label">Documenti</div>

        <NavLink
          to="/upload"
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <span className="nav-icon">⬆️</span>
          Carica file
        </NavLink>
      </nav>

      {/* FOOTER MESE */}
      <div className="sidebar-bottom">
        <div className="month-selector">
          <button
            type="button"
            className="month-nav-btn"
            onClick={() => setMonth(shiftMonth(month, -1))}
          >
            ◀
          </button>

          <span className="month-label">
            {formatMonthLabel(month)}
          </span>

          <button
            type="button"
            className="month-nav-btn"
            onClick={() => setMonth(shiftMonth(month, 1))}
          >
            ▶
          </button>
        </div>
      </div>
    </aside>
  );
}