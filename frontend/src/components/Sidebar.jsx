import { useState } from "react";
import { NavLink } from "react-router-dom";

const MONTHS = [
  "Gennaio",
  "Febbraio",
  "Marzo",
  "Aprile",
  "Maggio",
  "Giugno",
  "Luglio",
  "Agosto",
  "Settembre",
  "Ottobre",
  "Novembre",
  "Dicembre",
];

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
  const [monthPickerOpen, setMonthPickerOpen] = useState(false);

  const [selectedYear, selectedMonth] = month.split("-").map(Number);

  const years = Array.from({ length: 9 }, (_, index) => selectedYear - 4 + index);

  function selectMonth(year, monthIndex) {
    const nextMonth = String(monthIndex + 1).padStart(2, "0");
    setMonth(`${year}-${nextMonth}`);
    setMonthPickerOpen(false);
  }

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

      <div className="sidebar-bottom">
        <div className="month-selector">
          <button
            type="button"
            className="month-nav-btn"
            onClick={() => setMonth(shiftMonth(month, -1))}
          >
            ◀
          </button>

          <div className="month-picker-wrapper">
           <button
  type="button"
  className="month-label month-label-button"
  onClick={() => setMonthPickerOpen((value) => !value)}
>
  {formatMonthLabel(month)}
</button>

            {monthPickerOpen ? (
              <div className="month-picker-popover">
                <div className="month-picker-years">
                  {years.map((year) => (
                    <button
                      key={year}
                      type="button"
                      className={`month-picker-year ${
                        year === selectedYear ? "active" : ""
                      }`}
                      onClick={() => setMonth(`${year}-${String(selectedMonth).padStart(2, "0")}`)}
                    >
                      {year}
                    </button>
                  ))}
                </div>

                <div className="month-picker-grid">
                  {MONTHS.map((monthName, index) => (
                    <button
                      key={monthName}
                      type="button"
                      className={`month-picker-month ${
                        index + 1 === selectedMonth ? "active" : ""
                      }`}
                      onClick={() => selectMonth(selectedYear, index)}
                    >
                      {monthName.slice(0, 3)}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

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